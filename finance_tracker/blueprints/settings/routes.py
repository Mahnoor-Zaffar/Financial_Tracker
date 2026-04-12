from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from finance_tracker.extensions import db
from finance_tracker.forms import ProfileForm

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.full_name = form.full_name.data.strip()
        current_user.currency_code = form.currency_code.data.strip().upper()
        current_user.timezone = form.timezone.data
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("settings.profile"))
    return render_template("settings/profile.html", form=form)
