from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from finance_tracker.extensions import db
from finance_tracker.forms import AccountForm, CategoryForm, DeleteForm, TagForm
from finance_tracker.models import Account, Budget, Category, Tag, Transaction
from finance_tracker.models.account import account_name_key
from finance_tracker.models.category import category_name_key
from finance_tracker.services import account_balance_projection, get_owned_or_404

bp = Blueprint("finance", __name__, url_prefix="/finance")


def _linked_account_transaction_count(user_id: int, account_id: int) -> int:
    return Transaction.query.filter(
        Transaction.user_id == user_id,
        or_(
            Transaction.account_id == account_id,
            Transaction.transfer_account_id == account_id,
        ),
    ).count()


def _account_name_exists(user_id: int, name: str, account_id: int | None = None) -> bool:
    query = Account.query.filter_by(user_id=user_id, name_key=account_name_key(name))
    if account_id is not None:
        query = query.filter(Account.id != account_id)
    return db.session.query(query.exists()).scalar()


def _category_name_exists(
    user_id: int, name: str, kind: str, category_id: int | None = None
) -> bool:
    query = Category.query.filter_by(
        user_id=user_id, name_key=category_name_key(name), kind=kind
    )
    if category_id is not None:
        query = query.filter(Category.id != category_id)
    return db.session.query(query.exists()).scalar()


@bp.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    create_form = AccountForm(prefix="create")

    if create_form.validate_on_submit():
        account_name = create_form.name.data.strip()
        if _account_name_exists(current_user.id, account_name):
            flash("An account with this name already exists.", "error")
        else:
            account = Account(
                user_id=current_user.id,
                name=account_name,
                account_type=create_form.account_type.data,
                institution=(create_form.institution.data or "").strip() or None,
                opening_balance=create_form.opening_balance.data,
            )
            db.session.add(account)
            try:
                db.session.commit()
                flash("Account created.", "success")
                return redirect(url_for("finance.accounts"))
            except IntegrityError:
                db.session.rollback()
                flash("An account with this name already exists.", "error")

    rows = (
        Account.query.filter_by(user_id=current_user.id)
        .order_by(Account.is_active.desc(), Account.name.asc())
        .all()
    )
    balances = account_balance_projection(current_user.id)
    account_rows = [{"account": row, "balance": balances.get(row.id, 0)} for row in rows]
    delete_form = DeleteForm()
    return render_template(
        "finance/accounts.html",
        form=create_form,
        delete_form=delete_form,
        account_rows=account_rows,
    )


@bp.route("/accounts/<int:account_id>/edit", methods=["GET", "POST"])
@login_required
def edit_account(account_id: int):
    account = get_owned_or_404(Account, account_id, current_user.id)
    form = AccountForm(prefix="edit", obj=account)
    linked_transaction_count = _linked_account_transaction_count(current_user.id, account.id)
    opening_balance_locked = linked_transaction_count > 0
    opening_balance_helper = (
        "Opening balance is locked after transactions exist to preserve historical balances."
        if opening_balance_locked
        else ""
    )
    if opening_balance_locked:
        form.opening_balance.render_kw = {
            **(form.opening_balance.render_kw or {}),
            "readonly": True,
            "aria-readonly": "true",
        }

    if form.validate_on_submit():
        proposed_opening_balance = form.opening_balance.data
        if opening_balance_locked and proposed_opening_balance != account.opening_balance:
            flash(
                "Opening balance cannot be changed after transactions exist. Create a new account or record a balancing transaction instead.",
                "warning",
            )
            return (
                render_template(
                    "finance/account_edit.html",
                    form=form,
                    account=account,
                    opening_balance_helper=opening_balance_helper,
                ),
                409,
            )

        account_name = form.name.data.strip()
        if _account_name_exists(current_user.id, account_name, account_id=account.id):
            flash("An account with this name already exists.", "error")
            return (
                render_template(
                    "finance/account_edit.html",
                    form=form,
                    account=account,
                    opening_balance_helper=opening_balance_helper,
                ),
                409,
            )

        account.name = account_name
        account.account_type = form.account_type.data
        account.institution = (form.institution.data or "").strip() or None
        account.opening_balance = proposed_opening_balance
        try:
            db.session.commit()
            flash("Account updated.", "success")
            return redirect(url_for("finance.accounts"))
        except IntegrityError:
            db.session.rollback()
            flash("An account with this name already exists.", "error")
            return (
                render_template(
                    "finance/account_edit.html",
                    form=form,
                    account=account,
                    opening_balance_helper=opening_balance_helper,
                ),
                409,
            )

    return render_template(
        "finance/account_edit.html",
        form=form,
        account=account,
        opening_balance_helper=opening_balance_helper,
    )


@bp.route("/accounts/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_account(account_id: int):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)

    account = get_owned_or_404(Account, account_id, current_user.id)
    linked_transaction_count = _linked_account_transaction_count(current_user.id, account.id)

    if linked_transaction_count > 0:
        if account.is_active:
            account.is_active = False
            db.session.commit()
            flash(
                "Account has historical transactions and was archived instead of deleted.",
                "warning",
            )
        else:
            flash("Account is already archived.", "info")
        return redirect(url_for("finance.accounts"))

    db.session.delete(account)
    db.session.commit()
    flash("Account deleted.", "info")
    return redirect(url_for("finance.accounts"))


@bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    create_form = CategoryForm(prefix="create")
    if create_form.validate_on_submit():
        category_name = create_form.name.data.strip()
        category_kind = create_form.kind.data
        if _category_name_exists(current_user.id, category_name, category_kind):
            flash("That category already exists for this type.", "error")
        else:
            category = Category(
                user_id=current_user.id,
                name=category_name,
                kind=category_kind,
                color=create_form.color.data.strip(),
            )
            db.session.add(category)
            try:
                db.session.commit()
                flash("Category created.", "success")
                return redirect(url_for("finance.categories"))
            except IntegrityError:
                db.session.rollback()
                flash("That category already exists for this type.", "error")

    categories_list = (
        Category.query.filter_by(user_id=current_user.id)
        .order_by(Category.kind.asc(), Category.name.asc())
        .all()
    )
    delete_form = DeleteForm()
    return render_template(
        "finance/categories.html",
        form=create_form,
        delete_form=delete_form,
        categories=categories_list,
    )


@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def edit_category(category_id: int):
    category = get_owned_or_404(Category, category_id, current_user.id)
    form = CategoryForm(prefix="edit", obj=category)

    if form.validate_on_submit():
        proposed_kind = form.kind.data
        if proposed_kind != category.kind:
            linked_transaction_count = Transaction.query.filter_by(
                user_id=current_user.id, category_id=category.id
            ).count()
            linked_budget_count = Budget.query.filter_by(
                user_id=current_user.id, category_id=category.id
            ).count()
            if linked_transaction_count > 0 or linked_budget_count > 0:
                flash(
                    "Category type cannot be changed after it is used by budgets or transactions.",
                    "warning",
                )
                return render_template(
                    "finance/category_edit.html", form=form, category=category
                ), 409

        category_name = form.name.data.strip()
        if _category_name_exists(
            current_user.id, category_name, proposed_kind, category_id=category.id
        ):
            flash("That category already exists for this type.", "error")
            return render_template(
                "finance/category_edit.html", form=form, category=category
            ), 409

        category.name = category_name
        category.kind = proposed_kind
        category.color = form.color.data.strip()
        try:
            db.session.commit()
            flash("Category updated.", "success")
            return redirect(url_for("finance.categories"))
        except IntegrityError:
            db.session.rollback()
            flash("That category already exists for this type.", "error")
            return render_template(
                "finance/category_edit.html", form=form, category=category
            ), 409

    return render_template("finance/category_edit.html", form=form, category=category)


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id: int):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)

    category = get_owned_or_404(Category, category_id, current_user.id)
    transaction_count = Transaction.query.filter_by(
        user_id=current_user.id, category_id=category.id
    ).count()
    if transaction_count > 0:
        flash(
            "Category has historical transactions and cannot be deleted.",
            "warning",
        )
        return redirect(url_for("finance.categories"))

    budget_count = Budget.query.filter_by(user_id=current_user.id, category_id=category.id).count()
    if budget_count > 0:
        flash("Category has budgets and cannot be deleted. Remove the budgets first.", "warning")
        return redirect(url_for("finance.categories"))

    db.session.delete(category)
    db.session.commit()
    flash("Category deleted.", "info")
    return redirect(url_for("finance.categories"))


@bp.route("/tags", methods=["GET", "POST"])
@login_required
def tags():
    create_form = TagForm(prefix="create")
    if create_form.validate_on_submit():
        tag = Tag(
            user_id=current_user.id,
            name=create_form.name.data.strip().lower(),
            color=create_form.color.data.strip(),
        )
        db.session.add(tag)
        try:
            db.session.commit()
            flash("Tag created.", "success")
            return redirect(url_for("finance.tags"))
        except IntegrityError:
            db.session.rollback()
            flash("That tag already exists.", "error")

    tags_list = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()
    delete_form = DeleteForm()
    return render_template(
        "finance/tags.html", form=create_form, delete_form=delete_form, tags=tags_list
    )


@bp.route("/tags/<int:tag_id>/edit", methods=["GET", "POST"])
@login_required
def edit_tag(tag_id: int):
    tag = get_owned_or_404(Tag, tag_id, current_user.id)
    form = TagForm(prefix="edit", obj=tag)
    if form.validate_on_submit():
        tag.name = form.name.data.strip().lower()
        tag.color = form.color.data.strip()
        try:
            db.session.commit()
            flash("Tag updated.", "success")
            return redirect(url_for("finance.tags"))
        except IntegrityError:
            db.session.rollback()
            flash("That tag already exists.", "error")
            return render_template("finance/tag_edit.html", form=form, tag=tag), 409
    return render_template("finance/tag_edit.html", form=form, tag=tag)


@bp.route("/tags/<int:tag_id>/delete", methods=["POST"])
@login_required
def delete_tag(tag_id: int):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)

    tag = get_owned_or_404(Tag, tag_id, current_user.id)
    db.session.delete(tag)
    db.session.commit()
    flash("Tag deleted.", "info")
    return redirect(url_for("finance.tags"))
