from flask import Blueprint, render_template
from flask_login import current_user, login_required

from finance_tracker.services import build_analytics_snapshot, build_dashboard_snapshot

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def home():
    if not current_user.is_authenticated:
        return render_template("landing.html")
    return index()


@bp.route("/dashboard")
@login_required
def index():
    snapshot = build_dashboard_snapshot(current_user.id)
    charts = build_analytics_snapshot(current_user.id, months=6)
    return render_template("dashboard/index.html", snapshot=snapshot, charts=charts)
