from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "student.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user and user.check_password(password):
            if login_user(user):
                flash(f"Welcome back, {user.name}!", "success")
                next_page = request.args.get("next")
                if next_page:
                    return redirect(next_page)
                return redirect(url_for("admin.dashboard" if user.is_admin else "student.dashboard"))

            # Password was correct but the account is blocked from logging in
            if user.role == "student" and user.approval_status == "pending":
                flash("Your account is awaiting admin approval. Please check back later.", "warning")
            elif user.role == "student" and user.approval_status == "rejected":
                flash("Your registration was not approved. Contact your administrator.", "danger")
            elif not user.account_active:
                flash("This account has been deactivated. Contact your administrator.", "danger")
            else:
                flash("Unable to log in with this account.", "danger")
            return render_template("login.html")

        flash("Invalid username/email or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "student.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        year = request.form.get("year", "").strip()
        section = request.form.get("section", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not name or not email or not password:
            errors.append("Please fill in all required fields.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if password and len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", name=name, email=email, phone=phone,
                                    year=year, section=section)

        student = User(name=name, email=email, phone=phone, role="student",
                        year=year or None, section=section or None,
                        approval_status="pending", account_active=True)
        student.set_password(password)
        db.session.add(student)
        db.session.commit()

        flash("Registration submitted! An admin will review and approve your account before you can log in.",
              "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
