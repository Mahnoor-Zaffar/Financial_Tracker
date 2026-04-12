from flask import Blueprint, render_template
from flask_login import current_user, login_required

from finance_tracker.services import build_analytics_snapshot

bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@bp.route("/")
@login_required
def index():
    snapshot = build_analytics_snapshot(current_user.id, months=6)
    return render_template("analytics/index.html", snapshot=snapshot)
