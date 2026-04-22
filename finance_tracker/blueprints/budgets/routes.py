from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from finance_tracker.extensions import db
from finance_tracker.forms import BudgetForm, DeleteForm
from finance_tracker.models import Budget, BudgetValidationError, Category
from finance_tracker.services import (
    get_budget_progress_rows,
    get_owned_or_404,
    normalize_month_start,
)

bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def _apply_budget_validation_error(form: BudgetForm, exc: BudgetValidationError) -> bool:
    field_errors = getattr(exc, "field_errors", {}) or {}
    attached_any = False
    for field_name, messages in field_errors.items():
        field = getattr(form, field_name, None)
        if field is None:
            continue
        attached_any = True
        if isinstance(messages, str):
            messages = [messages]
        for message in messages:
            if message not in field.errors:
                field.errors.append(message)
    return attached_any


def _apply_income_category_request_error(form: BudgetForm, user_id: int) -> None:
    category_id = form.category_id.data
    if not category_id:
        return
    category = Category.query.filter_by(id=category_id, user_id=user_id).first()
    if category and category.kind != "expense":
        message = "Budgets can only be assigned to expense categories."
        form.category_id.errors[:] = [message]


def _selected_month_start() -> tuple[date, bool]:
    raw = request.args.get("month")
    if not raw:
        return date.today().replace(day=1), False
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1), False
    except (TypeError, ValueError):
        return date.today().replace(day=1), True


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    create_form = BudgetForm(prefix="create")
    delete_form = DeleteForm()
    expense_categories = (
        Category.query.filter_by(user_id=current_user.id, kind="expense")
        .order_by(Category.name.asc())
        .all()
    )
    create_form.category_id.choices = [(c.id, c.name) for c in expense_categories]

    if create_form.validate_on_submit():
        normalized_month = normalize_month_start(create_form.month_start.data)
        budget = Budget.query.filter_by(
            user_id=current_user.id,
            category_id=create_form.category_id.data,
            month_start=normalized_month,
        ).first()
        if budget is None:
            budget = Budget(
                user_id=current_user.id,
                category_id=create_form.category_id.data,
                month_start=normalized_month,
            )
            db.session.add(budget)
        budget.amount_limit = create_form.amount_limit.data
        try:
            db.session.commit()
            flash("Budget saved.", "success")
            return redirect(url_for("budgets.index", month=normalized_month.strftime("%Y-%m")))
        except BudgetValidationError as exc:
            db.session.rollback()
            if not _apply_budget_validation_error(create_form, exc):
                flash(str(exc), "error")
        except IntegrityError:
            db.session.rollback()
            flash("A budget for that month and category already exists.", "error")
    elif create_form.is_submitted():
        _apply_income_category_request_error(create_form, current_user.id)

    month_start, month_invalid = _selected_month_start()
    if month_invalid:
        flash("Invalid month selected. Showing the current month instead.", "warning")
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    budget_rows = get_budget_progress_rows(current_user.id, month_start)

    return render_template(
        "budgets/index.html",
        form=create_form,
        delete_form=delete_form,
        month_start=month_start,
        month_end=month_end,
        budget_rows=budget_rows,
    )


@bp.route("/<int:budget_id>/edit", methods=["GET", "POST"])
@login_required
def edit(budget_id: int):
    budget = get_owned_or_404(Budget, budget_id, current_user.id)
    form = BudgetForm(prefix="edit", obj=budget)
    expense_categories = (
        Category.query.filter_by(user_id=current_user.id, kind="expense")
        .order_by(Category.name.asc())
        .all()
    )
    form.category_id.choices = [(c.id, c.name) for c in expense_categories]

    if request.method == "GET":
        form.month_start.data = budget.month_start

    if form.validate_on_submit():
        budget.category_id = form.category_id.data
        budget.month_start = normalize_month_start(form.month_start.data)
        budget.amount_limit = form.amount_limit.data
        try:
            db.session.commit()
            flash("Budget updated.", "success")
            return redirect(url_for("budgets.index", month=budget.month_start.strftime("%Y-%m")))
        except BudgetValidationError as exc:
            db.session.rollback()
            if not _apply_budget_validation_error(form, exc):
                flash(str(exc), "error")
            return render_template("budgets/edit.html", form=form, budget=budget), 409
        except IntegrityError:
            db.session.rollback()
            flash("A budget for that month and category already exists.", "error")
            return render_template("budgets/edit.html", form=form, budget=budget), 409
    elif form.is_submitted():
        _apply_income_category_request_error(form, current_user.id)

    return render_template("budgets/edit.html", form=form, budget=budget)


@bp.route("/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete(budget_id: int):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)
    budget = get_owned_or_404(Budget, budget_id, current_user.id)
    month_token = budget.month_start.strftime("%Y-%m")
    db.session.delete(budget)
    db.session.commit()
    flash("Budget deleted.", "info")
    return redirect(url_for("budgets.index", month=month_token))
