import os
from datetime import timedelta

import click
from flask import Flask
from flask_login import current_user

from config import Config
from extensions import db, login_manager
from models import User


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if db_uri.startswith("sqlite:///"):
        db_path = db_uri.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.student import student_bp
    from routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_globals():
        pending_count = 0
        if current_user.is_authenticated and current_user.is_admin:
            pending_count = User.query.filter_by(role="student", approval_status="pending").count()
        unread = 0
        if current_user.is_authenticated and not current_user.is_admin:
            from routes.student import _unread_notification_count
            unread = _unread_notification_count(current_user.id)
        return {
            "unread_notification_count": unread,
            "pending_approval_count": pending_count,
            "app_name": app.config["APP_NAME"],
        }

    # ---- IST display filter (Ti10 convention: everything stored in UTC, shown in IST) ----
    ist_delta = timedelta(hours=app.config["DISPLAY_TZ_OFFSET_HOURS"],
                          minutes=app.config["DISPLAY_TZ_OFFSET_MINUTES"])

    @app.template_filter("ist")
    def to_ist(dt, fmt="%d %b %Y, %I:%M %p"):
        if not dt:
            return "—"
        return (dt + ist_delta).strftime(fmt)

    def _seed_admin_if_missing():
        email = app.config["DEFAULT_ADMIN_EMAIL"]
        username = app.config["DEFAULT_ADMIN_USERNAME"]
        existing = User.query.filter(
            (User.username == username) | (User.role == "admin")
        ).first()
        if existing:
            return existing
        admin = User(name=app.config["DEFAULT_ADMIN_NAME"], email=email, username=username,
                     role="admin", approval_status="approved", account_active=True)
        admin.set_password(app.config["DEFAULT_ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()
        return admin

    @app.cli.command("seed-admin")
    def seed_admin():
        """Create the default admin account if it doesn't already exist."""
        with app.app_context():
            existing_before = User.query.filter_by(role="admin").first()
            admin = _seed_admin_if_missing()
            if existing_before:
                click.echo(f"Admin already exists: {existing_before.login_identifier}")
            else:
                click.echo(f"Admin created: {admin.username} / {app.config['DEFAULT_ADMIN_PASSWORD']}")

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        with app.app_context():
            db.create_all()
            click.echo("Database tables created.")

    with app.app_context():
        db.create_all()
        # Auto-create a default admin on first run so the app is usable immediately
        _seed_admin_if_missing()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
