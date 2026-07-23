from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

from models import Course

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "student.dashboard"))
    courses = Course.query.filter_by(published=True).order_by(Course.created_at.desc()).limit(6).all()
    return render_template("index.html", courses=courses)


@main_bp.route("/courses")
def courses():
    all_courses = Course.query.filter_by(published=True).order_by(Course.created_at.desc()).all()
    return render_template("courses.html", courses=all_courses)
