from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from finance_tracker.extensions import db
from finance_tracker.forms import LoginForm, RegisterForm
from finance_tracker.models import User
from finance_tracker.services.auth_throttling import (
    check_login_throttle,
    record_failed_login,
    reset_login_throttle,
)

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_redirect_target(target: str | None):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc and parsed.netloc != request.host:
        return None
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    return target


def _client_ip() -> str:
    if request.access_route:
        return request.access_route[0]
    return request.remote_addr or "unknown"


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("That email is already registered.", "error")
            return render_template("auth/register.html", form=form), 409

        user = User(email=email, full_name=form.full_name.data.strip())
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That email is already registered.", "error")
            return render_template("auth/register.html", form=form), 409
        login_user(user)
        flash("Your account is ready.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        client_ip = _client_ip()
        throttle = check_login_throttle(client_ip, email)
        if throttle.blocked:
            flash("Too many login attempts. Try again later.", "error")
            response = render_template("auth/login.html", form=form), 429
            return response
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("This account is disabled. Contact support.", "error")
                return render_template("auth/login.html", form=form), 403
            reset_login_throttle(client_ip, email)
            user.last_login_at = db.func.now()
            login_user(user, remember=form.remember.data)
            db.session.commit()
            flash("Welcome back.", "success")
            return redirect(
                _safe_redirect_target(request.args.get("next"))
                or url_for("dashboard.index")
            )
        throttle = record_failed_login(client_ip, email)
        db.session.commit()
        if throttle.blocked:
            flash("Too many login attempts. Try again later.", "error")
            return render_template("auth/login.html", form=form), 429
        flash("Invalid credentials.", "error")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You are logged out.", "info")
    return redirect(url_for("auth.login"))
