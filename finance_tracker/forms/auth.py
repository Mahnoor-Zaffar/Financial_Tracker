from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp

from finance_tracker.forms.shared import not_blank


class RegisterForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), not_blank, Length(max=120)])
    email = EmailField("Email", validators=[DataRequired(), not_blank, Email(), Length(max=255)])
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            not_blank,
            Length(min=8, max=128),
            Regexp(
                r"^(?=.*[A-Za-z])(?=.*\d).+$",
                message="Password must include at least one letter and one number.",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), not_blank, Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), not_blank, Length(max=128)])
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")
