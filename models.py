from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class Batch(db.Model):
    """A year-wise grouping of courses, e.g. '2024-2028 Batch' / Year 2."""
    __tablename__ = "batches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)          # e.g. "2024-2028"
    year = db.Column(db.Integer, nullable=False)               # e.g. 1, 2, 3, 4
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    courses = db.relationship("Course", backref="batch", lazy=True)

    @property
    def course_count(self):
        return len(self.courses)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")  # admin | student
    year = db.Column(db.String(20))            # student's academic year, e.g. "2nd Year"
    section = db.Column(db.String(20))

    # Self-registration + admin approval workflow (students only; admins are pre-approved)
    approval_status = db.Column(db.String(20), nullable=False, default="approved")  # pending | approved | rejected
    account_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship("Enrollment", backref="student", lazy=True,
                                   cascade="all, delete-orphan")
    progress_entries = db.relationship("Progress", backref="student", lazy=True,
                                        cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_active(self):
        # Overrides flask_login.UserMixin.is_active: blocks login for
        # deactivated accounts or students still awaiting admin approval.
        if not self.account_active:
            return False
        if self.role == "student" and self.approval_status != "approved":
            return False
        return True

    @property
    def login_identifier(self):
        return self.username or self.email


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    thumbnail = db.Column(db.String(255))  # filename or URL
    category = db.Column(db.String(80))
    instructor = db.Column(db.String(120))
    duration = db.Column(db.String(50))

    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"), nullable=True)
    published = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contents = db.relationship("CourseContent", backref="course", lazy=True,
                                cascade="all, delete-orphan",
                                order_by="CourseContent.order")
    enrollments = db.relationship("Enrollment", backref="course", lazy=True,
                                   cascade="all, delete-orphan")
    notifications = db.relationship("Notification", backref="course", lazy=True)

    @property
    def video_count(self):
        return sum(1 for c in self.contents if c.content_type == "video")

    @property
    def document_count(self):
        return sum(1 for c in self.contents if c.content_type in ("pdf", "word"))

    @property
    def total_lessons(self):
        return len(self.contents)


class CourseContent(db.Model):
    __tablename__ = "course_contents"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    content_type = db.Column(db.String(20), nullable=False)  # video | pdf | word
    youtube_url = db.Column(db.String(255))
    youtube_id = db.Column(db.String(50))
    file_path = db.Column(db.String(255))
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    progress_entries = db.relationship("Progress", backref="content", lazy=True,
                                        cascade="all, delete-orphan")


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("student_id", "course_id", name="uq_student_course"),)


class Progress(db.Model):
    __tablename__ = "progress"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("course_contents.id"), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)

    __table_args__ = (db.UniqueConstraint("student_id", "content_id", name="uq_student_content"),)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default="general")
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reads = db.relationship("NotificationRead", backref="notification", lazy=True,
                             cascade="all, delete-orphan")


class NotificationRead(db.Model):
    __tablename__ = "notification_reads"

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey("notifications.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("notification_id", "student_id", name="uq_notif_student"),)


class AdminActivityLog(db.Model):
    """Audit trail of admin actions — mirrors Ti10's admin activity log."""
    __tablename__ = "admin_activity_log"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    admin_name = db.Column(db.String(120))   # snapshot, survives admin deletion
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
