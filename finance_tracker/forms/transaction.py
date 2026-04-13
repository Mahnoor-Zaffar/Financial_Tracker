from datetime import date
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from finance_tracker.forms.shared import not_blank


class TransactionForm(FlaskForm):
    transaction_type = SelectField(
        "Type",
        choices=[("expense", "Expense"), ("income", "Income"), ("transfer", "Transfer")],
        validators=[DataRequired()],
    )
    account_id = SelectField(
        "Account",
        coerce=int,
        validators=[DataRequired()],
        validate_choice=False,
    )
    to_account_id = SelectField(
        "To account",
        coerce=int,
        validators=[Optional()],
        default=0,
        validate_choice=False,
    )
    category_id = SelectField(
        "Category",
        coerce=int,
        validators=[Optional()],
        default=0,
        validate_choice=False,
    )
    amount = DecimalField(
        "Amount",
        validators=[DataRequired(), NumberRange(min=Decimal("0.01"))],
        places=2,
    )
    occurred_on = DateField("Date", validators=[DataRequired()], default=date.today)
    description = StringField(
        "Description",
        validators=[DataRequired(), not_blank, Length(max=180)],
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=500)])
    tag_names = StringField(
        "Tags",
        validators=[Optional(), Length(max=200)],
        description="Comma-separated tags",
    )
    submit = SubmitField("Save transaction")

    def validate_category_id(self, field):
        if self.transaction_type.data == "transfer":
            return

        if field.data:
            return

        if len(field.choices) <= 1:
            raise ValidationError(
                "Create at least one category before saving income or expense transactions."
            )

        raise ValidationError("Select a category for income and expense transactions.")


class TransactionFilterForm(FlaskForm):
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    transaction_type = SelectField(
        "Type",
        choices=[("", "All types"), ("expense", "Expense"), ("income", "Income"), ("transfer", "Transfer")],
        validators=[Optional()],
    )
    account_id = SelectField("Account", coerce=int, validators=[Optional()], default=0)
    category_id = SelectField("Category", coerce=int, validators=[Optional()], default=0)
    tag_id = SelectField("Tag", coerce=int, validators=[Optional()], default=0)
    sort = SelectField(
        "Sort",
        choices=[
            ("date_desc", "Newest first"),
            ("date_asc", "Oldest first"),
            ("amount_desc", "Amount high to low"),
            ("amount_asc", "Amount low to high"),
        ],
        validators=[Optional()],
        default="date_desc",
    )
    submit = SubmitField("Apply filters")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False

        if self.start_date.data and self.end_date.data and self.end_date.data < self.start_date.data:
            self.end_date.errors.append("End date must be on or after start date.")
            return False

        return True
