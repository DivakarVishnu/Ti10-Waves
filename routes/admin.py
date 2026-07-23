import os
from flask import (Blueprint, render_template, redirect, url_for, request,
                    flash, current_app, send_from_directory, abort)
from flask_login import current_user

from extensions import db
from models import (User, Course, CourseContent, Enrollment, Progress, Notification,
                     Batch, AdminActivityLog)
from decorators import admin_required
from utils import (extract_youtube_id, save_upload, wipe_course_files, delete_upload_file,
                    folder_size_bytes, human_size, find_orphaned_files)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def log_activity(action, details=""):
    entry = AdminActivityLog(admin_id=current_user.id, admin_name=current_user.name,
                              action=action, details=details)
    db.session.add(entry)


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    stats = {
        "total_courses": Course.query.count(),
        "published_courses": Course.query.filter_by(published=True).count(),
        "total_students": User.query.filter_by(role="student").count(),
        "pending_students": User.query.filter_by(role="student", approval_status="pending").count(),
        "total_batches": Batch.query.count(),
        "total_videos": CourseContent.query.filter_by(content_type="video").count(),
        "total_documents": CourseContent.query.filter(CourseContent.content_type.in_(["pdf", "word"])).count(),
        "total_notifications": Notification.query.count(),
    }
    recent_courses = Course.query.order_by(Course.created_at.desc()).limit(5).all()
    recent_students = User.query.filter_by(role="student").order_by(User.created_at.desc()).limit(5).all()
    return render_template("admin/dashboard.html", stats=stats,
                            recent_courses=recent_courses, recent_students=recent_students)


# ---------- Batch management (year-wise course grouping) ----------

@admin_bp.route("/batches")
@admin_required
def batches():
    all_batches = Batch.query.order_by(Batch.year.desc(), Batch.created_at.desc()).all()
    return render_template("admin/batches.html", batches=all_batches)


@admin_bp.route("/batches/add", methods=["GET", "POST"])
@admin_required
def add_batch():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        year = request.form.get("year", type=int)
        description = request.form.get("description", "").strip()

        if not name or not year:
            flash("Batch name and year are required.", "danger")
            return render_template("admin/add_batch.html")

        batch = Batch(name=name, year=year, description=description)
        db.session.add(batch)
        log_activity("Batch created", f'"{name}" (Year {year})')
        db.session.commit()
        flash(f'Batch "{name}" created.', "success")
        return redirect(url_for("admin.batches"))

    return render_template("admin/add_batch.html")


@admin_bp.route("/batches/<int:batch_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_batch(batch_id):
    batch = Batch.query.get_or_404(batch_id)
    if request.method == "POST":
        batch.name = request.form.get("name", "").strip()
        batch.year = request.form.get("year", type=int)
        batch.description = request.form.get("description", "").strip()
        log_activity("Batch updated", f'"{batch.name}" (Year {batch.year})')
        db.session.commit()
        flash("Batch updated.", "success")
        return redirect(url_for("admin.batches"))
    return render_template("admin/edit_batch.html", batch=batch)


@admin_bp.route("/batches/<int:batch_id>/delete", methods=["POST"])
@admin_required
def delete_batch(batch_id):
    """Deletes the batch. Courses in it are NOT auto-deleted — they're just unassigned,
    unless wipe=1 is passed, in which case courses (and their files) are wiped too."""
    batch = Batch.query.get_or_404(batch_id)
    wipe = request.form.get("wipe") == "1"
    name = batch.name

    if wipe:
        files_removed = 0
        courses_removed = 0
        for course in list(batch.courses):
            files_removed += wipe_course_files(course)
            db.session.delete(course)
            courses_removed += 1
        db.session.delete(batch)
        log_activity("Batch wiped & deleted",
                      f'"{name}" — {courses_removed} course(s), {files_removed} file(s) removed')
        db.session.commit()
        flash(f'Batch "{name}" and all its courses/files were deleted.', "info")
    else:
        for course in batch.courses:
            course.batch_id = None
        db.session.delete(batch)
        log_activity("Batch deleted", f'"{name}" (courses kept, unassigned)')
        db.session.commit()
        flash(f'Batch "{name}" deleted. Its courses were kept but unassigned.', "info")

    return redirect(url_for("admin.batches"))


# ---------- Course management ----------

@admin_bp.route("/courses")
@admin_required
def courses():
    batch_id = request.args.get("batch_id", type=int)
    query = Course.query
    if batch_id:
        query = query.filter_by(batch_id=batch_id)
    all_courses = query.order_by(Course.created_at.desc()).all()
    all_batches = Batch.query.order_by(Batch.year.desc()).all()
    return render_template("admin/courses.html", courses=all_courses, batches=all_batches,
                            selected_batch_id=batch_id)


@admin_bp.route("/courses/add", methods=["GET", "POST"])
@admin_required
def add_course():
    all_batches = Batch.query.order_by(Batch.year.desc()).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        instructor = request.form.get("instructor", "").strip()
        duration = request.form.get("duration", "").strip()
        batch_id = request.form.get("batch_id", type=int) or None
        published = request.form.get("published") == "on"

        if not title:
            flash("Course title is required.", "danger")
            return render_template("admin/add_course.html", batches=all_batches)

        thumbnail_path = None
        thumbnail_public_id = None
        thumb_file = request.files.get("thumbnail")
        if thumb_file and thumb_file.filename:
            try:
                thumbnail_path, thumbnail_public_id = save_upload(
                    thumb_file, subfolder="thumbnails", resource_type="image")
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("admin/add_course.html", batches=all_batches)

        course = Course(title=title, description=description, category=category,
                        instructor=instructor, duration=duration, thumbnail=thumbnail_path,
                        thumbnail_public_id=thumbnail_public_id,
                        batch_id=batch_id, published=published)
        db.session.add(course)
        log_activity("Course created", f'"{title}"')
        db.session.commit()

        flash(f'Course "{title}" created. Now add videos and materials.', "success")
        return redirect(url_for("admin.manage_content", course_id=course.id))

    return render_template("admin/add_course.html", batches=all_batches)


@admin_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    all_batches = Batch.query.order_by(Batch.year.desc()).all()

    if request.method == "POST":
        course.title = request.form.get("title", "").strip()
        course.description = request.form.get("description", "").strip()
        course.category = request.form.get("category", "").strip()
        course.instructor = request.form.get("instructor", "").strip()
        course.duration = request.form.get("duration", "").strip()
        course.batch_id = request.form.get("batch_id", type=int) or None
        course.published = request.form.get("published") == "on"

        thumb_file = request.files.get("thumbnail")
        if thumb_file and thumb_file.filename:
            try:
                old_thumbnail, old_public_id = course.thumbnail, course.thumbnail_public_id
                course.thumbnail, course.thumbnail_public_id = save_upload(
                    thumb_file, subfolder="thumbnails", resource_type="image")
                if old_thumbnail or old_public_id:
                    delete_upload_file(old_thumbnail, public_id=old_public_id, resource_type="image")
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("admin/edit_course.html", course=course, batches=all_batches)

        log_activity("Course updated", f'"{course.title}"')
        db.session.commit()
        flash("Course updated.", "success")
        return redirect(url_for("admin.courses"))

    return render_template("admin/edit_course.html", course=course, batches=all_batches)


@admin_bp.route("/courses/<int:course_id>/publish", methods=["POST"])
@admin_required
def toggle_publish(course_id):
    course = Course.query.get_or_404(course_id)
    course.published = not course.published
    log_activity("Course " + ("published" if course.published else "unpublished"), f'"{course.title}"')
    db.session.commit()
    flash(f'Course "{course.title}" is now {"Published" if course.published else "Draft"}.', "success")
    return redirect(request.referrer or url_for("admin.courses"))


@admin_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@admin_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    title = course.title
    files_removed = wipe_course_files(course)
    db.session.delete(course)
    log_activity("Course deleted", f'"{title}" — {files_removed} file(s) removed from disk')
    db.session.commit()
    flash(f'Course "{title}" and its files were deleted.', "info")
    return redirect(url_for("admin.courses"))


# ---------- Content management ----------

@admin_bp.route("/courses/<int:course_id>/content")
@admin_required
def manage_content(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template("admin/manage_content.html", course=course)


@admin_bp.route("/courses/<int:course_id>/content/add-video", methods=["POST"])
@admin_required
def add_video(course_id):
    course = Course.query.get_or_404(course_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    youtube_url = request.form.get("youtube_url", "").strip()
    order = request.form.get("order", type=int) or (len(course.contents) + 1)

    youtube_id = extract_youtube_id(youtube_url)
    if not title or not youtube_id:
        flash("Please provide a title and a valid YouTube URL.", "danger")
        return redirect(url_for("admin.manage_content", course_id=course.id))

    content = CourseContent(course_id=course.id, title=title, description=description,
                             content_type="video", youtube_url=youtube_url,
                             youtube_id=youtube_id, order=order)
    db.session.add(content)
    db.session.commit()
    flash(f'Video "{title}" added.', "success")
    return redirect(url_for("admin.manage_content", course_id=course.id))


@admin_bp.route("/courses/<int:course_id>/content/upload", methods=["POST"])
@admin_required
def upload_material(course_id):
    course = Course.query.get_or_404(course_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    order = request.form.get("order", type=int) or (len(course.contents) + 1)
    file = request.files.get("file")

    if not title or not file or not file.filename:
        flash("Please provide a title and choose a file.", "danger")
        return redirect(url_for("admin.manage_content", course_id=course.id))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    content_type = "pdf" if ext == "pdf" else ("word" if ext in ("doc", "docx") else None)
    if not content_type:
        flash("Only PDF and Word documents are supported here.", "danger")
        return redirect(url_for("admin.manage_content", course_id=course.id))

    try:
        file_path, file_public_id = save_upload(file, subfolder=f"course_{course.id}",
                                                  resource_type="raw")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("admin.manage_content", course_id=course.id))

    content = CourseContent(course_id=course.id, title=title, description=description,
                             content_type=content_type, file_path=file_path,
                             file_public_id=file_public_id, order=order)
    db.session.add(content)
    db.session.commit()
    flash(f'"{title}" uploaded.', "success")
    return redirect(url_for("admin.manage_content", course_id=course.id))


@admin_bp.route("/content/<int:content_id>/delete", methods=["POST"])
@admin_required
def delete_content(content_id):
    content = CourseContent.query.get_or_404(content_id)
    course_id = content.course_id
    title = content.title
    if content.file_path or content.file_public_id:
        rtype = "raw" if content.content_type in ("pdf", "word") else "image"
        delete_upload_file(content.file_path, public_id=content.file_public_id, resource_type=rtype)
    db.session.delete(content)
    log_activity("Content removed", f'"{title}"')
    db.session.commit()
    flash("Content removed.", "info")
    return redirect(url_for("admin.manage_content", course_id=course_id))


# ---------- Students ----------

@admin_bp.route("/students")
@admin_required
def students():
    status_filter = request.args.get("status", "all")
    query = User.query.filter_by(role="student")
    if status_filter == "pending":
        query = query.filter_by(approval_status="pending")
    elif status_filter == "approved":
        query = query.filter_by(approval_status="approved")
    elif status_filter == "rejected":
        query = query.filter_by(approval_status="rejected")
    elif status_filter == "inactive":
        query = query.filter_by(account_active=False)

    all_students = query.order_by(User.created_at.desc()).all()
    enrollment_counts = {
        s.id: Enrollment.query.filter_by(student_id=s.id).count() for s in all_students
    }
    pending_count = User.query.filter_by(role="student", approval_status="pending").count()
    return render_template("admin/students.html", students=all_students,
                            enrollment_counts=enrollment_counts, status_filter=status_filter,
                            pending_count=pending_count)


@admin_bp.route("/students/<int:student_id>")
@admin_required
def student_detail(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    enrollments = Enrollment.query.filter_by(student_id=student.id).all()
    progress_by_course = {}
    for e in enrollments:
        total = e.course.total_lessons
        completed = Progress.query.filter_by(student_id=student.id, course_id=e.course_id,
                                               completed=True).count()
        pct = int((completed / total) * 100) if total else 0
        progress_by_course[e.course_id] = {"course": e.course, "completed": completed,
                                            "total": total, "pct": pct}
    return render_template("admin/student_detail.html", student=student,
                            progress_by_course=progress_by_course)


@admin_bp.route("/students/<int:student_id>/approve", methods=["POST"])
@admin_required
def approve_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.approval_status = "approved"
    log_activity("Student approved", student.name)
    db.session.commit()
    flash(f"{student.name} approved.", "success")
    return redirect(request.referrer or url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/reject", methods=["POST"])
@admin_required
def reject_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.approval_status = "rejected"
    log_activity("Student rejected", student.name)
    db.session.commit()
    flash(f"{student.name} rejected.", "info")
    return redirect(request.referrer or url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_student_active(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.account_active = not student.account_active
    log_activity("Student " + ("reactivated" if student.account_active else "deactivated"), student.name)
    db.session.commit()
    flash(f"{student.name} is now {'active' if student.account_active else 'deactivated'}.", "success")
    return redirect(request.referrer or url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@admin_required
def delete_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    name = student.name
    db.session.delete(student)  # cascades enrollments + progress
    log_activity("Student deleted", name)
    db.session.commit()
    flash(f"{name} and their enrollment/progress data were deleted.", "info")
    return redirect(url_for("admin.students"))


# ---------- Notifications ----------

@admin_bp.route("/notifications")
@admin_required
def notifications():
    all_notifications = Notification.query.order_by(Notification.created_at.desc()).all()
    all_courses = Course.query.order_by(Course.title).all()
    return render_template("admin/notifications.html", notifications=all_notifications,
                            courses=all_courses)


@admin_bp.route("/notifications/add", methods=["POST"])
@admin_required
def add_notification():
    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    notification_type = request.form.get("notification_type", "general")
    course_id = request.form.get("course_id", type=int) or None

    if not title or not message:
        flash("Title and message are required.", "danger")
        return redirect(url_for("admin.notifications"))

    notif = Notification(title=title, message=message, notification_type=notification_type,
                          course_id=course_id)
    db.session.add(notif)
    db.session.commit()
    flash("Notification published.", "success")
    return redirect(url_for("admin.notifications"))


@admin_bp.route("/notifications/<int:notif_id>/edit", methods=["POST"])
@admin_required
def edit_notification(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    notif.title = request.form.get("title", "").strip()
    notif.message = request.form.get("message", "").strip()
    notif.notification_type = request.form.get("notification_type", "general")
    course_id = request.form.get("course_id", type=int) or None
    notif.course_id = course_id
    db.session.commit()
    flash("Notification updated.", "success")
    return redirect(url_for("admin.notifications"))


@admin_bp.route("/notifications/<int:notif_id>/delete", methods=["POST"])
@admin_required
def delete_notification(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    db.session.delete(notif)
    db.session.commit()
    flash("Notification deleted.", "info")
    return redirect(url_for("admin.notifications"))


# ---------- Storage / maintenance ----------

@admin_bp.route("/storage")
@admin_required
def storage():
    folder = current_app.config["UPLOAD_FOLDER"]
    total_size = folder_size_bytes(folder)
    orphans = find_orphaned_files()
    orphan_total = sum(o["size"] for o in orphans)

    batch_breakdown = []
    for batch in Batch.query.order_by(Batch.year.desc()).all():
        size = 0
        for course in batch.courses:
            if course.thumbnail:
                size += _safe_size(os.path.join(folder, course.thumbnail))
            for c in course.contents:
                if c.file_path:
                    size += _safe_size(os.path.join(folder, c.file_path))
        batch_breakdown.append({"batch": batch, "size": size, "size_human": human_size(size)})

    unassigned_courses = Course.query.filter_by(batch_id=None).all()
    unassigned_size = 0
    for course in unassigned_courses:
        if course.thumbnail:
            unassigned_size += _safe_size(os.path.join(folder, course.thumbnail))
        for c in course.contents:
            if c.file_path:
                unassigned_size += _safe_size(os.path.join(folder, c.file_path))

    return render_template("admin/storage.html", total_size=total_size,
                            total_size_human=human_size(total_size),
                            orphans=orphans, orphan_total_human=human_size(orphan_total),
                            batch_breakdown=batch_breakdown,
                            unassigned_size_human=human_size(unassigned_size),
                            unassigned_count=len(unassigned_courses),
                            cloudinary_enabled=current_app.config.get("USE_CLOUDINARY", False))


def _safe_size(path):
    try:
        return os.path.getsize(path) if os.path.isfile(path) else 0
    except OSError:
        return 0


@admin_bp.route("/storage/clean-orphans", methods=["POST"])
@admin_required
def clean_orphans():
    orphans = find_orphaned_files()
    removed = 0
    for o in orphans:
        if delete_upload_file(o["rel_path"]):
            removed += 1
    log_activity("Orphaned files cleaned", f"{removed} file(s) removed")
    db.session.commit()
    flash(f"Removed {removed} orphaned file(s) not linked to any course.", "success")
    return redirect(url_for("admin.storage"))


@admin_bp.route("/storage/clear-batch/<int:batch_id>", methods=["POST"])
@admin_required
def clear_batch_data(batch_id):
    """Wipes all courses, content, enrollments/progress, and files for a batch — keeps the batch itself."""
    batch = Batch.query.get_or_404(batch_id)
    files_removed = 0
    courses_removed = 0
    for course in list(batch.courses):
        files_removed += wipe_course_files(course)
        db.session.delete(course)
        courses_removed += 1
    log_activity("Batch data cleared", f'"{batch.name}" — {courses_removed} course(s), '
                                        f'{files_removed} file(s) removed')
    db.session.commit()
    flash(f'Cleared {courses_removed} course(s) and {files_removed} file(s) from "{batch.name}".', "info")
    return redirect(url_for("admin.storage"))


# ---------- Activity log ----------

@admin_bp.route("/activity-log")
@admin_required
def activity_log():
    page = request.args.get("page", 1, type=int)
    pagination = AdminActivityLog.query.order_by(AdminActivityLog.created_at.desc()) \
        .paginate(page=page, per_page=50, error_out=False)
    return render_template("admin/activity_log.html", pagination=pagination)


# ---------- Serving uploaded files ----------

@admin_bp.route("/uploads/<path:filename>")
@admin_required
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
