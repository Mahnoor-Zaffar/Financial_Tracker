from decimal import Decimal
from datetime import date
import logging
from logging.config import dictConfig
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from finance_tracker.blueprints.analytics.routes import bp as analytics_bp
from finance_tracker.blueprints.auth.routes import bp as auth_bp
from finance_tracker.blueprints.budgets.routes import bp as budgets_bp
from finance_tracker.blueprints.dashboard.routes import bp as dashboard_bp
from finance_tracker.blueprints.finance.routes import bp as finance_bp
from finance_tracker.blueprints.settings.routes import bp as settings_bp
from finance_tracker.blueprints.transactions.routes import bp as transactions_bp
from finance_tracker.cli import register_cli
from finance_tracker.config import get_config
from finance_tracker.extensions import csrf, db, login_manager, migrate
from finance_tracker.services import as_decimal


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    _validate_production_config(app)
    configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    register_blueprints(app)
    register_template_helpers(app)
    register_error_handlers(app)
    register_security_headers(app)
    register_cli(app)

    return app


def _validate_production_config(app: Flask) -> None:
    if app.config.get("DEBUG") or app.config.get("TESTING"):
        return
    secret = app.config.get("SECRET_KEY") or ""
    if secret == "dev-change-this-secret-key":
        raise RuntimeError("SECRET_KEY must be set in production.")


def configure_logging(app: Flask) -> None:
    if app.config.get("TESTING"):
        return

    level_name = app.config.get("LOG_LEVEL", "INFO")
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"
                }
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                    "formatter": "default",
                }
            },
            "root": {"level": level, "handlers": ["wsgi"]},
        }
    )


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(settings_bp)


def register_template_helpers(app: Flask) -> None:
    @app.template_filter("money")
    def money(value, currency_code: str | None = None) -> str:
        amount = as_decimal(value or Decimal("0.00"))
        code = currency_code
        if code is None and current_user.is_authenticated:
            code = current_user.currency_code
        code = code or "USD"
        symbol = {"USD": "$", "EUR": "€", "GBP": "£", "PKR": "Rs"}.get(code, f"{code} ")
        return f"{symbol}{amount.quantize(Decimal('0.01')):,.2f}"

    @app.context_processor
    def inject_globals() -> dict:
        return {"nav_year": date.today().year}


def register_error_handlers(app: Flask) -> None:
    def _safe_referrer() -> str | None:
        referrer = request.referrer
        if not referrer:
            return None
        parsed = urlparse(referrer)
        if parsed.netloc and parsed.netloc != request.host:
            return None
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return None
        return referrer

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        flash("Your session expired. Please retry the action.", "error")
        fallback = url_for("dashboard.index") if current_user.is_authenticated else url_for("auth.login")
        return redirect(_safe_referrer() or fallback)

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        return render_template("errors/500.html"), 500


def register_security_headers(app: Flask) -> None:
    csp = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        if not app.config.get("DEBUG") and not app.config.get("TESTING"):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


from finance_tracker import models  # noqa: E402,F401
