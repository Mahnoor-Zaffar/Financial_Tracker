from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from finance_tracker.extensions import db
from finance_tracker.forms import BudgetForm, DeleteForm
from finance_tracker.models import Budget, Category
from finance_tracker.services import (
    get_budget_progress_rows,
    get_owned_or_404,
    normalize_month_start,
)

bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def _selected_month_start() -> date:
    raw = request.args.get("month")
    if not raw:
        return date.today().replace(day=1)
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1)
    except (TypeError, ValueError):
        return date.today().replace(day=1)


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
        except IntegrityError:
            db.session.rollback()
            flash("A budget for that month and category already exists.", "error")

    month_start = _selected_month_start()
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
        except IntegrityError:
            db.session.rollback()
            flash("A budget for that month and category already exists.", "error")
            return render_template("budgets/edit.html", form=form, budget=budget), 409

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
