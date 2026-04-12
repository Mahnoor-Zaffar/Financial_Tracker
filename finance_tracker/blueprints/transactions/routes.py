from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from finance_tracker.extensions import db
from finance_tracker.forms import DeleteForm, TransactionFilterForm, TransactionForm
from finance_tracker.models import Transaction
from finance_tracker.services import (
    TransactionValidationError,
    account_choices,
    apply_sorting,
    build_transaction_query,
    category_choices,
    create_transaction,
    get_owned_or_404,
    pagination_from_request,
    summarize_transactions,
    tag_choices,
    update_transaction,
)

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


def _bind_transaction_form_choices(form: TransactionForm, user_id: int):
    account_opts = account_choices(user_id=user_id, include_inactive=False)
    category_opts = category_choices(user_id=user_id)

    form.account_id.choices = account_opts
    form.to_account_id.choices = [(0, "Select destination")] + account_opts
    form.category_id.choices = [(0, "Select category")] + category_opts


def _bind_filter_choices(form: TransactionFilterForm, user_id: int):
    form.account_id.choices = [(0, "All accounts")] + account_choices(
        user_id=user_id, include_inactive=True
    )
    form.category_id.choices = [(0, "All categories")] + category_choices(user_id=user_id)
    form.tag_id.choices = [(0, "All tags")] + tag_choices(user_id=user_id)


@bp.route("/", methods=["GET"])
@login_required
def index():
    filter_form = TransactionFilterForm(request.args, meta={"csrf": False})
    _bind_filter_choices(filter_form, current_user.id)

    filter_is_valid = filter_form.validate()
    if not filter_is_valid and request.args:
        flash("Some filters were invalid and were ignored.", "warning")

    query = build_transaction_query(
        user_id=current_user.id,
        start_date=filter_form.start_date.data,
        end_date=filter_form.end_date.data,
        transaction_type=filter_form.transaction_type.data or None,
        account_id=filter_form.account_id.data or None,
        category_id=filter_form.category_id.data or None,
        tag_id=filter_form.tag_id.data or None,
    )
    summary = summarize_transactions(query)
    query = apply_sorting(query, filter_form.sort.data or "date_desc")

    page, per_page = pagination_from_request(
        default_per_page=current_app.config.get("TRANSACTIONS_PER_PAGE", 20),
        max_per_page=current_app.config.get("MAX_TRANSACTIONS_PER_PAGE", 100),
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    query_args = request.args.to_dict(flat=True)
    query_args.pop("page", None)
    delete_form = DeleteForm()

    return render_template(
        "transactions/index.html",
        filter_form=filter_form,
        delete_form=delete_form,
        transactions=pagination.items,
        pagination=pagination,
        query_args=query_args,
        summary=summary,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = TransactionForm(prefix="new")
    _bind_transaction_form_choices(form, current_user.id)

    if form.validate_on_submit():
        try:
            create_transaction(
                user_id=current_user.id,
                transaction_type=form.transaction_type.data,
                amount=form.amount.data,
                description=form.description.data,
                occurred_on=form.occurred_on.data,
                account_id=form.account_id.data,
                to_account_id=form.to_account_id.data or None,
                category_id=form.category_id.data or None,
                notes=form.notes.data,
                raw_tags=form.tag_names.data,
            )
            db.session.commit()
            flash("Transaction saved.", "success")
            return redirect(url_for("transactions.index"))
        except TransactionValidationError as exc:
            db.session.rollback()
            flash(str(exc), "error")

    return render_template("transactions/new.html", form=form)


@bp.route("/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
def edit(transaction_id: int):
    transaction = get_owned_or_404(Transaction, transaction_id, current_user.id)

    form = TransactionForm(prefix="edit", obj=transaction)
    _bind_transaction_form_choices(form, current_user.id)

    if request.method == "GET":
        form.to_account_id.data = transaction.transfer_account_id or 0
        form.category_id.data = transaction.category_id or 0
        form.tag_names.data = ", ".join(tag.name for tag in transaction.tags)

    if form.validate_on_submit():
        try:
            update_transaction(
                transaction,
                user_id=current_user.id,
                transaction_type=form.transaction_type.data,
                amount=form.amount.data,
                description=form.description.data,
                occurred_on=form.occurred_on.data,
                account_id=form.account_id.data,
                to_account_id=form.to_account_id.data or None,
                category_id=form.category_id.data or None,
                notes=form.notes.data,
                raw_tags=form.tag_names.data,
            )
            db.session.commit()
            flash("Transaction updated.", "success")
            return redirect(url_for("transactions.index"))
        except TransactionValidationError as exc:
            db.session.rollback()
            flash(str(exc), "error")

    return render_template("transactions/edit.html", form=form, transaction=transaction)


@bp.route("/<int:transaction_id>/delete", methods=["POST"])
@login_required
def delete(transaction_id: int):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)
    transaction = get_owned_or_404(Transaction, transaction_id, current_user.id)
    db.session.delete(transaction)
    db.session.commit()
    flash("Transaction deleted.", "info")
    return redirect(url_for("transactions.index"))
