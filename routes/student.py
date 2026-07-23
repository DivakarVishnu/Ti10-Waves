from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, request,
                    flash, current_app, send_from_directory, jsonify)
from flask_login import current_user

from extensions import db
from models import Course, CourseContent, Enrollment, Progress, Notification, NotificationRead
from decorators import student_required

student_bp = Blueprint("student", __name__, url_prefix="/student")


def _course_progress(student_id, course):
    total = course.total_lessons
    completed = Progress.query.filter_by(student_id=student_id, course_id=course.id,
                                          completed=True).count()
    pct = int((completed / total) * 100) if total else 0
    return completed, total, pct


@student_bp.route("/dashboard")
@student_required
def dashboard():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()

    my_courses = []
    completed_count = 0
    in_progress_count = 0
    for e in enrollments:
        completed, total, pct = _course_progress(current_user.id, e.course)
        if total and completed == total:
            completed_count += 1
        elif completed > 0:
            in_progress_count += 1
        my_courses.append({"course": e.course, "completed": completed, "total": total, "pct": pct})

    unread_count = _unread_notification_count(current_user.id)
    recent_notifications = Notification.query.order_by(Notification.created_at.desc()).limit(5).all()

    return render_template("student/dashboard.html", my_courses=my_courses,
                            completed_count=completed_count, in_progress_count=in_progress_count,
                            unread_count=unread_count, recent_notifications=recent_notifications)


@student_bp.route("/courses")
@student_required
def courses():
    all_courses = Course.query.filter_by(published=True).order_by(Course.created_at.desc()).all()
    enrolled_ids = {e.course_id for e in Enrollment.query.filter_by(student_id=current_user.id).all()}
    return render_template("student/courses.html", courses=all_courses, enrolled_ids=enrolled_ids)


@student_bp.route("/courses/<int:course_id>/enroll", methods=["POST"])
@student_required
def enroll(course_id):
    course = Course.query.get_or_404(course_id)
    if not course.published:
        flash("This course isn't released yet.", "warning")
        return redirect(url_for("student.courses"))
    existing = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
    if not existing:
        db.session.add(Enrollment(student_id=current_user.id, course_id=course.id))
        db.session.commit()
        flash(f'Enrolled in "{course.title}".', "success")
    return redirect(url_for("student.course_detail", course_id=course.id))


@student_bp.route("/courses/<int:course_id>")
@student_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    enrolled = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
    if not course.published and not enrolled:
        flash("This course isn't released yet.", "warning")
        return redirect(url_for("student.courses"))
    completed, total, pct = _course_progress(current_user.id, course)
    return render_template("student/course_detail.html", course=course, enrolled=enrolled,
                            completed=completed, total=total, pct=pct)


@student_bp.route("/courses/<int:course_id>/learn")
@student_bp.route("/courses/<int:course_id>/learn/<int:content_id>")
@student_required
def learning(course_id, content_id=None):
    course = Course.query.get_or_404(course_id)
    enrolled = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
    if not enrolled:
        flash("Please enroll in this course first.", "warning")
        return redirect(url_for("student.course_detail", course_id=course.id))

    if not course.contents:
        flash("This course has no learning content yet.", "info")
        return redirect(url_for("student.course_detail", course_id=course.id))

    if content_id:
        current_content = CourseContent.query.filter_by(id=content_id, course_id=course.id).first_or_404()
    else:
        # continue from last incomplete lesson
        completed_ids = {p.content_id for p in Progress.query.filter_by(
            student_id=current_user.id, course_id=course.id, completed=True).all()}
        current_content = next((c for c in course.contents if c.id not in completed_ids),
                                course.contents[0])

    completed_ids = {p.content_id for p in Progress.query.filter_by(
        student_id=current_user.id, course_id=course.id, completed=True).all()}

    completed, total, pct = _course_progress(current_user.id, course)

    return render_template("student/learning.html", course=course, current_content=current_content,
                            completed_ids=completed_ids, completed=completed, total=total, pct=pct)


@student_bp.route("/content/<int:content_id>/complete", methods=["POST"])
@student_required
def mark_complete(content_id):
    content = CourseContent.query.get_or_404(content_id)
    progress = Progress.query.filter_by(student_id=current_user.id, content_id=content.id).first()
    if not progress:
        progress = Progress(student_id=current_user.id, course_id=content.course_id,
                             content_id=content.id)
        db.session.add(progress)
    progress.completed = True
    progress.completed_at = datetime.utcnow()
    db.session.commit()

    completed, total, pct = _course_progress(current_user.id, content.course)
    return jsonify({"success": True, "completed": completed, "total": total, "pct": pct})


@student_bp.route("/notifications")
@student_required
def notifications():
    all_notifications = Notification.query.order_by(Notification.created_at.desc()).all()
    read_ids = {r.notification_id for r in NotificationRead.query.filter_by(
        student_id=current_user.id).all()}
    return render_template("student/notifications.html", notifications=all_notifications,
                            read_ids=read_ids)


@student_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@student_required
def mark_notification_read(notif_id):
    existing = NotificationRead.query.filter_by(notification_id=notif_id,
                                                  student_id=current_user.id).first()
    if not existing:
        db.session.add(NotificationRead(notification_id=notif_id, student_id=current_user.id))
        db.session.commit()
    return jsonify({"success": True})


def _unread_notification_count(student_id):
    total = Notification.query.count()
    read = NotificationRead.query.filter_by(student_id=student_id).count()
    return max(total - read, 0)


@student_bp.route("/files/<path:filename>")
@student_required
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
