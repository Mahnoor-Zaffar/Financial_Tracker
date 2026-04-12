from datetime import date
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class BudgetForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    month_start = DateField("Month", validators=[DataRequired()], default=date.today)
    amount_limit = DecimalField(
        "Budget limit",
        validators=[DataRequired(), NumberRange(min=Decimal("0.01"))],
        places=2,
    )
    submit = SubmitField("Save budget")
