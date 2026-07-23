# Ti10-Waves — Course Learning Platform

A clean, responsive course learning platform built with **Python Flask**, **Flask-SQLAlchemy**,
and **Flask-Login**. Admins organize courses by year-wise **Batches**, release them to students
via a Draft/Published toggle, and upload YouTube videos, PDFs, and Word documents; students
self-register (pending admin approval), enroll, learn, and track progress. UI theme: yellow & green.

## Features

- Role-based auth (Admin / Student) with hashed passwords
- **Admin logs in with a username** (`KITCSE` by default) — no email required
- **Batches**: group courses by academic year (e.g. "2024-2028 · Year 2"); filter courses by batch
- **Draft / Published release control** per course — students only ever see Published courses
- **Student self-registration with admin approval** — new accounts start `pending` and can't log
  in until an admin approves them; admins can also reject, deactivate/reactivate, or delete
  student accounts (deleting cascades their enrollments and progress)
- **Storage & Cleanup page**: total upload storage used, orphaned-file detection + one-click
  cleanup, and per-batch "Clear data" to wipe a whole year's courses/content/files at once
- **Admin activity log**: audit trail of course/batch/student actions (who did what, when — shown
  in IST)
- Course CRUD, YouTube video embedding, PDF/Word uploads, notifications, student roster & progress
- Student: browse/enroll in published courses, in-platform video/PDF viewer, lesson-by-lesson
  progress tracking, notifications with unread badge
- SQLite by default; switches to Postgres automatically if `DATABASE_URL` is set (e.g. Neon)

## Local setup

```bash
python -m venv venv
venv\Scripts\activate            REM Windows (cmd)
# source venv/bin/activate       # macOS/Linux

pip install -r requirements.txt

python app.py
```

The app auto-creates its database tables and a default admin account on first run:

- **Username:** `KITCSE`
- **Password:** `CSE4321`

(Override via `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD` env vars — see `.env.example`.)
Log in at the same **Login** page students use — the "Email / Username" field accepts either.

Then open **http://localhost:5000**.

## Project structure

```
course_platform/
├── app.py                # App factory, blueprint registration, seed-admin, IST filter
├── config.py              # SQLite (dev) / Postgres (prod) config, Ti10-style env vars
├── extensions.py          # db, login_manager instances
├── models.py               # User, Batch, Course, CourseContent, Enrollment, Progress,
│                            # Notification, AdminActivityLog
├── decorators.py          # admin_required / student_required
├── utils.py                # YouTube ID extraction, secure file upload, storage/cleanup helpers
├── routes/
│   ├── main.py             # Public home + course catalog (published courses only)
│   ├── auth.py              # Login (username or email) / Register (pending approval) / Logout
│   ├── admin.py              # Dashboard, batches, courses, content, students, notifications,
│   │                          # storage/cleanup, activity log
│   └── student.py           # Student dashboard, learning page, progress, notifications
├── templates/
│   ├── admin/                # Admin views (sidebar layout)
│   └── student/              # Student views
└── static/
    ├── css/style.css         # Yellow & green theme
    ├── js/script.js
    └── uploads/               # Thumbnails, PDFs, Word docs (per-course subfolders)
```

## Deployment (Render + Neon Postgres — same setup as Ti10)

1. Push this project to a GitHub repo.
2. Create a Neon Postgres database, copy its connection string.
3. Create a free Cloudinary account at cloudinary.com, copy the "API Environment variable"
   string from your dashboard (looks like `cloudinary://<key>:<secret>@<cloud_name>`).
4. Create a new Render Web Service pointing at the repo.
5. Build command: `pip install -r requirements-deploy.txt`
6. Start command: `gunicorn app:app` (already in `Procfile`)
7. Set environment variables on Render (see `.env.example` for the full list):
   - `SECRET_KEY` — a random string
   - `DATABASE_URL` — your Neon Postgres connection string (the app auto-converts
     `postgres://` to `postgresql://` for SQLAlchemy)
   - `CLOUDINARY_URL` — your Cloudinary connection string (see step 3) — **set this or
     uploaded files will be lost on every redeploy**
   - `DEFAULT_ADMIN_USERNAME` — defaults to `KITCSE` if unset
   - `DEFAULT_ADMIN_PASSWORD` — defaults to `CSE4321` if unset (change this for production!)
   - `DEFAULT_ADMIN_EMAIL` — optional, can be left blank

> **File storage:** with `CLOUDINARY_URL` set, every thumbnail/PDF/Word upload goes straight to
> Cloudinary and survives redeploys, restarts, and Render's ephemeral filesystem. Without it,
> uploads fall back to local disk under `static/uploads/` — fine for local development, but those
> files **will be wiped** the next time Render redeploys or restarts the service. Existing local
> files aren't auto-migrated to Cloudinary when you add the env var later — only new uploads
> after that point go to Cloudinary.

## Storage & data maintenance

Go to **Admin → Storage & Cleanup** to:
- See total local-disk usage of `static/uploads` (a banner tells you whether Cloudinary is
  active — once it is, new uploads no longer count against this local figure)
- Find and delete orphaned local files (uploads no longer referenced by any course/lesson)
- Clear an entire batch's courses, content, enrollments, and progress in one action (keeps the
  batch itself so it can be reused next year)

Deleting a course, a piece of content, or a batch (with "wipe" checked) also removes its files
automatically — from Cloudinary if that's where they live, or from local disk otherwise. Nothing
is ever silently orphaned by these delete actions.

## Notes

- Allowed upload extensions: `pdf`, `doc`, `docx`, `png`, `jpg`, `jpeg` (max 25 MB)
- YouTube videos are never downloaded — only the video ID is stored and embedded via iframe
- Timestamps are stored in UTC and displayed in IST throughout the admin panel
- Course "modules" aren't implemented as a separate concept yet; content is a flat ordered
  list per course — the schema (`order` column) allows grouping into modules later without a
  migration headache
