from flask_wtf import FlaskForm
from wtforms import SubmitField
from wtforms.validators import ValidationError


class DeleteForm(FlaskForm):
    submit = SubmitField("Delete")


def not_blank(_form, field):
    if field.data is None:
        return
    if isinstance(field.data, str) and not field.data.strip():
        raise ValidationError("This field cannot be empty.")
