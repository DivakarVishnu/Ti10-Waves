from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user, login_required, logout_user


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapped


def student_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.is_admin:
            abort(403)
        # Re-check in case the account was deactivated/un-approved after this session started
        if not current_user.is_active:
            logout_user()
            flash("Your account is no longer active. Please contact your administrator.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapped
