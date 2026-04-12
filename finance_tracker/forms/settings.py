from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp

from finance_tracker.forms.shared import not_blank


class ProfileForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), not_blank, Length(max=120)])
    currency_code = StringField(
        "Currency",
        validators=[
            DataRequired(),
            not_blank,
            Regexp(r"^[A-Za-z]{3}$", message="Use ISO code, e.g. USD."),
        ],
    )
    timezone = SelectField(
        "Timezone",
        choices=[
            ("UTC", "UTC"),
            ("Asia/Karachi", "Asia/Karachi"),
            ("Europe/London", "Europe/London"),
            ("America/New_York", "America/New_York"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Update profile")
