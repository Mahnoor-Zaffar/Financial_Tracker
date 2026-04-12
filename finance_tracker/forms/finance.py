from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp

from finance_tracker.forms.shared import not_blank


class AccountForm(FlaskForm):
    name = StringField("Account name", validators=[DataRequired(), not_blank, Length(max=120)])
    account_type = SelectField(
        "Type",
        choices=[
            ("checking", "Checking"),
            ("savings", "Savings"),
            ("cash", "Cash"),
            ("credit", "Credit"),
            ("investment", "Investment"),
        ],
        validators=[DataRequired()],
    )
    institution = StringField("Institution", validators=[Optional(), Length(max=120)])
    opening_balance = DecimalField(
        "Opening balance",
        validators=[DataRequired(), NumberRange(min=Decimal("0.00"))],
        places=2,
        default=Decimal("0.00"),
    )
    submit = SubmitField("Add account")


class CategoryForm(FlaskForm):
    name = StringField("Category name", validators=[DataRequired(), not_blank, Length(max=100)])
    kind = SelectField(
        "Category type",
        choices=[("expense", "Expense"), ("income", "Income")],
        validators=[DataRequired()],
    )
    color = StringField(
        "Color",
        validators=[
            DataRequired(),
            Regexp(r"^#[0-9A-Fa-f]{6}$", message="Use a hex color like #6a7286."),
        ],
        default="#6a7286",
    )
    submit = SubmitField("Add category")


class TagForm(FlaskForm):
    name = StringField("Tag name", validators=[DataRequired(), not_blank, Length(max=60)])
    color = StringField(
        "Color",
        validators=[
            DataRequired(),
            Regexp(r"^#[0-9A-Fa-f]{6}$", message="Use a hex color like #a4603e."),
        ],
        default="#a4603e",
    )
    submit = SubmitField("Add tag")
