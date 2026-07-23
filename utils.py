import os
import re
import uuid
from urllib.parse import urlparse, parse_qs

from werkzeug.utils import secure_filename
from flask import current_app

import cloudinary
import cloudinary.uploader


def extract_youtube_id(url: str):
    """Extract the video ID from common YouTube URL formats."""
    if not url:
        return None
    url = url.strip()

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    if "youtu.be" in host:
        vid = parsed.path.lstrip("/")
        return vid.split("/")[0] if vid else None

    if "youtube.com" in host:
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        match = re.match(r"^/(embed|shorts|live)/([A-Za-z0-9_-]{6,})", parsed.path)
        if match:
            return match.group(2)

    # Fallback: try to find an 11-char id-looking token
    match = re.search(r"([A-Za-z0-9_-]{11})", url)
    return match.group(1) if match else None


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def save_upload(file_storage, subfolder: str = "", resource_type: str = "auto"):
    """Save an uploaded file and return (path_or_url, public_id).

    - If Cloudinary is configured (CLOUDINARY_URL set), the file goes to
      Cloudinary and this returns (secure_url, public_id) — public_id is
      needed later to actually delete the asset from Cloudinary.
    - Otherwise it falls back to local disk under UPLOAD_FOLDER and returns
      (relative_path, None). Local files are lost if the host's filesystem
      is wiped on redeploy (e.g. Render free tier) — Cloudinary avoids that.
    """
    if not file_storage or file_storage.filename == "":
        return None, None
    if not allowed_file(file_storage.filename):
        raise ValueError("File type not allowed")

    if current_app.config.get("USE_CLOUDINARY"):
        base_folder = current_app.config.get("CLOUDINARY_FOLDER", "ti10-waves")
        folder = f"{base_folder}/{subfolder}" if subfolder else base_folder
        original_name = secure_filename(file_storage.filename)
        name_no_ext = os.path.splitext(original_name)[0]
        public_id = f"{uuid.uuid4().hex}_{name_no_ext}"

        result = cloudinary.uploader.upload(
            file_storage,
            folder=folder,
            public_id=public_id,
            resource_type=resource_type,   # "image" for thumbnails, "raw" for pdf/doc
            use_filename=False,
            unique_filename=False,
            overwrite=False,
        )
        return result["secure_url"], result["public_id"]

    # ---- Local disk fallback (dev only, or if Cloudinary isn't set up) ----
    original_name = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{original_name}"

    folder = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        folder = os.path.join(folder, subfolder)
    os.makedirs(folder, exist_ok=True)

    filepath = os.path.join(folder, unique_name)
    file_storage.save(filepath)

    rel_path = os.path.join(subfolder, unique_name) if subfolder else unique_name
    return rel_path.replace("\\", "/"), None


def content_type_label(content_type: str) -> str:
    return {"video": "Video", "pdf": "PDF", "word": "Document"}.get(content_type, content_type.title())


# ---------- Storage maintenance helpers ----------

def delete_upload_file(rel_path: str, public_id: str = None, resource_type: str = "image") -> bool:
    """Delete an uploaded file — from Cloudinary if public_id is given, from
    local disk otherwise. Safe no-op if the file/asset is already gone."""
    if public_id:
        try:
            result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            return result.get("result") == "ok"
        except Exception:
            return False

    if not rel_path or rel_path.startswith("http"):
        # A Cloudinary URL with no public_id on record can't be deleted remotely —
        # this shouldn't happen for anything uploaded after this update.
        return False

    folder = current_app.config["UPLOAD_FOLDER"]
    full_path = os.path.normpath(os.path.join(folder, rel_path))
    # Guard against path traversal outside the uploads folder
    if not full_path.startswith(os.path.normpath(folder)):
        return False
    try:
        if os.path.isfile(full_path):
            os.remove(full_path)
            return True
    except OSError:
        pass
    return False


def wipe_course_files(course) -> int:
    """Delete a course's thumbnail and all of its content files — from
    Cloudinary or local disk, whichever they were stored on. Returns count removed."""
    removed = 0
    if course.thumbnail or course.thumbnail_public_id:
        if delete_upload_file(course.thumbnail, public_id=course.thumbnail_public_id,
                               resource_type="image"):
            removed += 1
    for content in course.contents:
        if content.file_path or content.file_public_id:
            rtype = "raw" if content.content_type in ("pdf", "word") else "image"
            if delete_upload_file(content.file_path, public_id=content.file_public_id,
                                   resource_type=rtype):
                removed += 1
    return removed


def folder_size_bytes(path: str) -> int:
    total = 0
    if not os.path.isdir(path):
        return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def list_referenced_upload_paths():
    """All *local* file paths currently referenced by Course.thumbnail /
    CourseContent.file_path. Cloudinary URLs are skipped — they're never
    local orphans since they don't live under UPLOAD_FOLDER at all."""
    from models import Course, CourseContent
    referenced = set()
    for c in Course.query.with_entities(Course.thumbnail).all():
        if c.thumbnail and not c.thumbnail.startswith("http"):
            referenced.add(os.path.normpath(c.thumbnail))
    for c in CourseContent.query.with_entities(CourseContent.file_path).all():
        if c.file_path and not c.file_path.startswith("http"):
            referenced.add(os.path.normpath(c.file_path))
    return referenced


def find_orphaned_files():
    """Files sitting under UPLOAD_FOLDER that no DB row points to anymore."""
    folder = current_app.config["UPLOAD_FOLDER"]
    referenced = list_referenced_upload_paths()
    orphans = []
    if not os.path.isdir(folder):
        return orphans
    for dirpath, _dirnames, filenames in os.walk(folder):
        for f in filenames:
            if f == ".gitkeep":
                continue
            full_path = os.path.join(dirpath, f)
            rel_path = os.path.normpath(os.path.relpath(full_path, folder))
            if rel_path not in referenced:
                orphans.append({
                    "rel_path": rel_path.replace("\\", "/"),
                    "size": os.path.getsize(full_path),
                })
    return orphans
