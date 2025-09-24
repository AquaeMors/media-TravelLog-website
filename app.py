from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, jsonify, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text, func
from sqlalchemy.orm import subqueryload
from datetime import datetime, timedelta
from functools import wraps
import os, uuid, pathlib, json, urllib.request, urllib.parse
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from PIL import Image, ImageOps  # thumbnails
from collections import Counter
from sqlalchemy import or_

# ---------------- App & Config ----------------
app = Flask(__name__)

# Base folder of this project (portable across OSes)
BASE_DIR = pathlib.Path(__file__).resolve().parent

# Build a cross-platform SQLite file URI for local dev
def _local_sqlite_uri(filename: str) -> str:
    p = (BASE_DIR / filename).resolve()
    return "sqlite:///" + str(p).replace("\\", "/")

# Choose DB URI:
# 1) honor env vars (DATABASE_URL or SQLALCHEMY_DATABASE_URI)
# 2) else if /opt/media exists, use server DB there
# 3) else fall back to local ./media.db
app.config["SQLALCHEMY_DATABASE_URI"] = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("SQLALCHEMY_DATABASE_URI")
    or ("sqlite:////opt/media/media.db" if os.path.isdir("/opt/media") else _local_sqlite_uri("media.db"))
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Sessions / cookies
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = not bool(os.environ.get("COOKIE_INSECURE"))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Uploads directory (env > /opt/media/uploads > ./uploads)
_upload_root_env = os.environ.get("UPLOAD_ROOT")
if _upload_root_env:
    upload_root = _upload_root_env
elif os.path.isdir("/opt/media"):
    upload_root = "/opt/media/uploads"
else:
    upload_root = str((BASE_DIR / "uploads").resolve())

app.config["UPLOAD_ROOT"] = upload_root
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB

# Thumbnails
app.config["THUMB_MAX_PX"] = int(os.environ.get("THUMB_MAX_PX", "512"))
app.config["THUMB_QUALITY"] = int(os.environ.get("THUMB_QUALITY", "82"))

db = SQLAlchemy(app)

MEDIA_TYPES = ["book", "movie", "show", "anime", "manga", "manhwa", "game", "other"]

DEFAULT_STATUSES = ["current", "waiting", "finished"]  # legacy (UI no longer uses)
SERIAL_TYPES = ["manga", "manhwa"]                     # legacy (UI no longer uses)
SERIAL_STATUSES = ["ongoing", "completed", "hiatus", "canceled"]  # legacy

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    can_travel_edit = db.Column(db.Boolean, nullable=False, default=False)
    can_approve_users = db.Column(db.Boolean, nullable=False, default=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

class HomeCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, index=True)  # "travel", "tracker", etc.
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    image_path = db.Column(db.String(600))  # relative path served via /u/<path>
    url = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

class Chapter(db.Model):
    __tablename__ = "item_chapter"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id", ondelete="CASCADE"), index=True, nullable=False)
    number = db.Column(db.Integer, nullable=False)  # 1-based chapter number
    title = db.Column(db.String(200))
    source_path = db.Column(db.String(600), nullable=False)  # relative path under UPLOAD_ROOT
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("item_id", "number", name="uq_item_chapter_number"),)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    media_type = db.Column(db.String(20), nullable=False, index=True)

    # legacy columns kept for compatibility (not shown in UI now)
    status = db.Column(db.String(20), nullable=False, index=True, default="info")
    score = db.Column(db.Integer)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    tags = db.Column(db.String(200))
    notes = db.Column(db.Text)

    chapter_current = db.Column(db.Integer)
    chapter_total   = db.Column(db.Integer)

    # new/non-personalized fields for display
    seasons = db.Column(db.Integer)              # shows/anime
    release_status = db.Column(db.String(20))    # Ongoing/Completed/Hiatus/Canceled
    year = db.Column(db.Integer)                 # movies/games optional
    runtime_mins = db.Column(db.Integer)         # movies optional
    platforms = db.Column(db.String(200))        # games optional

    # cover image
    cover_path = db.Column(db.String(600))       # original uploaded image path under /u
    cover_thumb_path = db.Column(db.String(600)) # jpg thumbnail for display

    source_path = db.Column(db.String(600))
    chapters = db.relationship(
        "Chapter",
        backref="item",
        lazy="joined",           
        order_by="Chapter.number",
        cascade="all, delete-orphan",
    )
    comments = db.relationship("ItemComment", backref="item", lazy=True, cascade="all, delete-orphan")

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    address = db.Column(db.String(500), nullable=False)
    comments = db.Column(db.Text)
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photos = db.relationship("Photo", backref="trip", lazy=True, cascade="all, delete-orphan")
    user_comments = db.relationship("Comment", backref="trip", lazy=True, cascade="all, delete-orphan")

class WeddingItem(db.Model):
    __tablename__ = "wedding_item"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)   # idea, link, ring, cake, photo, vendor, venue, task, ceremony, reception
    title = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    url = db.Column(db.String(1024))
    url_ts = db.Column(db.Integer)
    image_path = db.Column(db.String(1024))
    tags = db.Column(db.String(255))
    meta = db.Column(db.JSON, default=dict)           
    created_by_user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_starred = db.Column(db.Boolean, nullable=False, default=False)

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False, index=True)
    stored_path = db.Column(db.String(600), nullable=False)
    thumb_path = db.Column(db.String(600))
    original_name = db.Column(db.String(300))
    mime_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class SeatingTable(db.Model):
    __tablename__ = "seating_table"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)     # e.g., "Table 5"
    capacity = db.Column(db.Integer, default=8)
    img_tiny = db.Column(db.String(300))               # baby photo (Tiny)
    img_rosie = db.Column(db.String(300))              # baby photo (Rosie)

class Guest(db.Model):
    __tablename__ = "guest"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    side = db.Column(db.String(20))                    # 'Tiny' | 'Rosie' | 'Both' | None
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    rsvp = db.Column(db.String(20), default="unknown") # 'yes' | 'no' | 'unknown'
    notes = db.Column(db.Text)
    table_id = db.Column(db.Integer, db.ForeignKey("seating_table.id"))
    table = db.relationship("SeatingTable", lazy="joined")

class BudgetItem(db.Model):
    __tablename__ = "budget_item"
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(80), nullable=False) # e.g., 'Venue', 'Catering', 'Rings'
    item = db.Column(db.String(200), nullable=False)    # e.g., 'Deposit', 'Cake'
    estimate = db.Column(db.Integer, default=0)         # store cents to avoid float drift (later)
    actual = db.Column(db.Integer)                      # cents; nullable
    due_date = db.Column(db.Date)
    paid = db.Column(db.Boolean, default=False)
    vendor_url = db.Column(db.String(600))
    notes = db.Column(db.Text)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    author = db.Column(db.String(80), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ItemComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    author = db.Column(db.String(80), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Reactions for comments across both features.
# 'kind' is 'trip' or 'item' to avoid id collision between tables.
class CommentReaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False, index=True)       # 'trip' | 'item'
    comment_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    value = db.Column(db.Integer, nullable=False)                     # 1=like, -1=dislike
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("kind", "comment_id", "user_id", name="uq_reaction_one_per_user"),
    )

class RegistrationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)  # pending/approved/denied
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

# ---------------- One-time setup & light migrations ----------------
os.makedirs(app.config["UPLOAD_ROOT"], exist_ok=True)
with app.app_context():
    
    db.create_all()
    # Add meta JSON column to wedding_item if missing
    cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(wedding_item)")).fetchall()]
    if "meta" not in cols:
        db.session.execute(text("ALTER TABLE wedding_item ADD COLUMN meta TEXT DEFAULT '{}'"))
        db.session.commit()

    cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(wedding_item)")).fetchall()]
    if "is_starred" not in cols:
        db.session.execute(text(
            "ALTER TABLE wedding_item ADD COLUMN is_starred INTEGER NOT NULL DEFAULT 0"
        ))
        db.session.commit()

    # user table
    cols_user = [r[1] for r in db.session.execute(text("PRAGMA table_info(user)")).fetchall()]
    if "can_travel_edit" not in cols_user:
        db.session.execute(text("ALTER TABLE user ADD COLUMN can_travel_edit INTEGER NOT NULL DEFAULT 0"))
    if "can_approve_users" not in cols_user:
        db.session.execute(text("ALTER TABLE user ADD COLUMN can_approve_users INTEGER NOT NULL DEFAULT 0"))
    if "is_admin" not in cols_user:
        db.session.execute(text("ALTER TABLE user ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"))
        db.session.commit()

    # trip table
    cols_trip = [r[1] for r in db.session.execute(text("PRAGMA table_info(trip)")).fetchall()]
    if "lat" not in cols_trip:
        db.session.execute(text("ALTER TABLE trip ADD COLUMN lat REAL"))
    if "lon" not in cols_trip:
        db.session.execute(text("ALTER TABLE trip ADD COLUMN lon REAL"))

    # photo table
    cols_photo = [r[1] for r in db.session.execute(text("PRAGMA table_info(photo)")).fetchall()]
    if "thumb_path" not in cols_photo:
        db.session.execute(text("ALTER TABLE photo ADD COLUMN thumb_path TEXT"))

    # item table (ensure new columns)
    cols_item = [r[1] for r in db.session.execute(text("PRAGMA table_info(item)")).fetchall()]
    if "chapter_current" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN chapter_current INTEGER"))
    if "chapter_total" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN chapter_total INTEGER"))
    if "seasons" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN seasons INTEGER"))
    if "release_status" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN release_status TEXT"))
    if "year" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN year INTEGER"))
    if "runtime_mins" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN runtime_mins INTEGER"))
    if "platforms" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN platforms TEXT"))
    if "cover_path" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN cover_path TEXT"))
    if "cover_thumb_path" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN cover_thumb_path TEXT"))
    if "status" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN status TEXT DEFAULT 'info'"))
    if "score" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN score INTEGER"))
    if "added_at" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN added_at DATETIME"))
    if "source_path" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN source_path TEXT"))

    # registration_request older versions
    cols_rr = [r[1] for r in db.session.execute(text("PRAGMA table_info(registration_request)")).fetchall()]
    if cols_rr:
        if "decided_at" not in cols_rr:
            db.session.execute(text("ALTER TABLE registration_request ADD COLUMN decided_at DATETIME"))
        if "decided_by_user_id" not in cols_rr:
            db.session.execute(text("ALTER TABLE registration_request ADD COLUMN decided_by_user_id INTEGER"))

    # Seed Home cards if none exist
    def ensure_card(key, title, description, url, sort_order):
        if not HomeCard.query.filter_by(key=key).first():
            db.session.add(HomeCard(
                key=key,
                title=title,
                description=description,
                url=url,
                sort_order=sort_order
            ))

    ensure_card("travel",  "T&R Travel Log",
                "Map our adventures, add photos, and notes.", "/travel", 10)
    ensure_card("tracker", "Media Tracker",
                "Track books, manga/manhwa, movies, shows, and more.", "/tracker", 20)
    ensure_card("fitness", "Fitness",
                "Section for keeping track of and looking at trends for personal fitness", "/fitness", 30)
    ensure_card("wedding", "Wedding",
            "Plan + brainstorm, all in one place (admins only).", "/wedding", 40)
    
    db.session.commit()

# ---------------- Template helpers ----------------
import os
from flask import send_from_directory
@app.get("/favicon.ico")
def favicon_root():
    return send_from_directory(
        os.path.join(app.static_folder, "icons"),
        "favicon.ico",
        max_age=31536000  # replaces cache_timeout
    )

@app.route("/assets/<path:filename>")
def assets(filename):
    folder = os.path.join(app.root_path, "assets")
    return send_from_directory(folder, filename)

@app.context_processor
def inject_user():
    u = None
    uid = session.get("user_id")
    if uid:
        u = User.query.get(uid)
    return {"current_user": u}

@app.context_processor
def override_url_for():
    import os
    def dated_url_for(endpoint, **values):
        if endpoint == 'static':
            filename = values.get('filename', '')
            if filename:
                filepath = os.path.join(app.root_path, 'static', filename)
                if os.path.exists(filepath):
                    values['v'] = int(os.path.getmtime(filepath))
        return url_for(endpoint, **values)
    return dict(url_for=dated_url_for)

# ---------------- Auth/perm helpers ----------------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def travel_edit_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        user = User.query.get(uid) if uid else None
        if not user or not user.can_travel_edit:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        user = User.query.get(uid) if uid else None
        if not user or not user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def approve_users_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        user = User.query.get(uid) if uid else None
        if not user or not user.can_approve_users:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def parse_score(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        n = int(v)
        return max(0, min(10, n))
    except ValueError:
        return None

def parse_coord(s):
    try:
        return float(s)
    except Exception:
        return None

def valid_lat_lon(lat, lon):
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

def _looks_like_image(first_bytes: bytes, ext: str) -> bool:
    if ext not in ALLOWED_EXTS:
        return False
    b = first_bytes
    if b[:3] == b"\xFF\xD8\xFF": return True   # JPEG
    if b[:8] == b"\x89PNG\r\n\x1a\n": return True
    if b[:6] in (b"GIF87a", b"GIF89a"): return True
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP": return True
    return False

# --- Geocoding ---
def geocode_address(addr: str):
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "format": "json", "q": addr, "limit": 1
        })
        req = urllib.request.Request(url, headers={"User-Agent": "TR-TravelLog/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None

# --- Thumbnails ---
def make_thumbnail(src_path: pathlib.Path, thumb_path: pathlib.Path, max_px: int, quality: int):
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((max_px, max_px), Image.LANCZOS)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        elif im.mode == "RGBA":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        im.save(thumb_path, "JPEG", quality=quality, optimize=True, progressive=True)

# ---------- Reactions: helpers ----------
def hydrate_comment_reactions(comments, user_id, kind: str):
    """Attach likes/dislikes and current user's reaction to each comment."""
    if not comments:
        return
    ids = [c.id for c in comments]
    # all reactions for these comments
    all_rows = (CommentReaction.query
                .filter(CommentReaction.kind == kind,
                        CommentReaction.comment_id.in_(ids))
                .all())
    counts = {}
    for r in all_rows:
        likes, dislikes = counts.get(r.comment_id, (0, 0))
        if r.value == 1: likes += 1
        elif r.value == -1: dislikes += 1
        counts[r.comment_id] = (likes, dislikes)

    mine_rows = []
    if user_id:
        mine_rows = (CommentReaction.query
                     .filter(CommentReaction.kind == kind,
                             CommentReaction.user_id == user_id,
                             CommentReaction.comment_id.in_(ids))
                     .all())
    mine = {r.comment_id: ("like" if r.value == 1 else "dislike") for r in mine_rows}

    for c in comments:
        c.likes, c.dislikes = counts.get(c.id, (0, 0))
        c.user_reaction = mine.get(c.id)

def collect_tag_counts(query):
    """
    Given a SQLAlchemy query of Item rows, return a dict {tag: count}
    Tags are read from the comma-separated Item.tags field.
    """
    counts = Counter()
    for it in query:
        if not it.tags:
            continue
        for raw in it.tags.split(','):
            t = (raw or '').strip().lower()
            if t:
                counts[t] += 1
    # return in alpha order (you can sort by count desc in the view if you prefer)
    return dict(sorted(counts.items()))

def save_item_cover(file_storage, item_id) -> tuple[str, str] | tuple[None, None]:
    """Save original cover + a jpeg thumb, return (rel_original, rel_thumb) or (None,None)."""
    if not file_storage or not file_storage.filename:
        return None, None
    original = secure_filename(file_storage.filename)
    ext = pathlib.Path(original).suffix.lower()
    head = file_storage.stream.read(16); file_storage.stream.seek(0)
    if not _looks_like_image(head, ext):
        return None, None

    base_dir = pathlib.Path(app.config["UPLOAD_ROOT"]) / "tracker" / str(item_id)
    thumbs_dir = base_dir / "thumbs"
    base_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    uniq = f"cover{ext if ext in ALLOWED_EXTS else '.bin'}"
    dest = base_dir / uniq
    file_storage.save(dest)

    thumb_name = "cover.jpg"
    thumb_path = thumbs_dir / thumb_name
    make_thumbnail(dest, thumb_path, app.config["THUMB_MAX_PX"], app.config["THUMB_QUALITY"])

    rel_original = str(pathlib.Path("tracker") / str(item_id) / uniq)
    rel_thumb = str(pathlib.Path("tracker") / str(item_id) / "thumbs" / thumb_name)
    return rel_original, rel_thumb

def _looks_like_pdf(first_bytes: bytes) -> bool:
    # Most PDFs start with %PDF-
    return first_bytes.startswith(b"%PDF-")

def save_item_source(file_storage, item_id) -> str | None:
    """Save a single 'source' file (PDF for now). Returns relative path or None."""
    if not file_storage or not file_storage.filename:
        return None

    original = secure_filename(file_storage.filename)
    ext = pathlib.Path(original).suffix.lower()

    head = file_storage.stream.read(8); file_storage.stream.seek(0)
    if ext != ".pdf" and not _looks_like_pdf(head):
        return None

    base_dir = pathlib.Path(app.config["UPLOAD_ROOT"]) / "tracker" / str(item_id) / "source"
    base_dir.mkdir(parents=True, exist_ok=True)

    # keep it predictable so re-uploads overwrite instead of piling up
    dest = base_dir / "source.pdf"
    file_storage.save(dest)

    return str(pathlib.Path("tracker") / str(item_id) / "source" / "source.pdf")

CHAPTER_DIRNAME = "chapters"

def _infer_chapter_number(filename: str) -> int | None:
    """
    Try to pull a chapter number from a filename:
    Picks the last integer group (e.g., 'MySeries_ch_012_extra.pdf' -> 12)
    """
    import re, os
    base = os.path.splitext(os.path.basename(filename))[0].lower()
    nums = re.findall(r"(\d+)", base)
    if not nums:
        return None
    return int(nums[-1])

def save_chapter_pdf(file_storage, item_id: int, chap_num: int) -> str:
    """
    Save chapter PDF to UPLOAD_ROOT/tracker/<item_id>/chapters/ch-XXX.pdf
    Returns a relative path like 'tracker/42/chapters/ch-001.pdf'
    """
    original = secure_filename(file_storage.filename or "")
    # verify it's a PDF by extension or header
    head = file_storage.stream.read(5); file_storage.stream.seek(0)
    if not (original.lower().endswith(".pdf") or head.startswith(b"%PDF-")):
        raise ValueError("Not a PDF")
    base = pathlib.Path(app.config["UPLOAD_ROOT"]) / "tracker" / str(item_id) / CHAPTER_DIRNAME
    base.mkdir(parents=True, exist_ok=True)
    dest = base / f"ch-{chap_num:03d}.pdf"
    file_storage.save(dest)
    rel = pathlib.Path("tracker") / str(item_id) / CHAPTER_DIRNAME / dest.name
    return str(rel)


def save_wedding_image(file_storage, bucket: str, item_id: int):
    """
    bucket: one of 'rings','cakes','photos'
    returns (rel_original, rel_thumb) or (None, None)
    """
    if not file_storage or not file_storage.filename:
        return None, None

    original = secure_filename(file_storage.filename)
    ext = pathlib.Path(original).suffix.lower()

    head = file_storage.stream.read(16); file_storage.stream.seek(0)
    if not _looks_like_image(head, ext):
        return None, None

    base_dir = pathlib.Path(app.config["UPLOAD_ROOT"]) / "wedding" / bucket / str(item_id)
    thumbs_dir = base_dir / "thumbs"
    base_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    unique = f"{uuid.uuid4().hex}{ext if ext in ALLOWED_EXTS else '.bin'}"
    dest = base_dir / unique
    file_storage.save(dest)

    thumb_name = f"{pathlib.Path(unique).stem}.jpg"
    thumb_path = thumbs_dir / thumb_name
    make_thumbnail(dest, thumb_path, app.config["THUMB_MAX_PX"], app.config["THUMB_QUALITY"])

    rel_original = str(pathlib.Path("wedding") / bucket / str(item_id) / unique)
    rel_thumb = str(pathlib.Path("wedding") / bucket / str(item_id) / "thumbs" / thumb_name)
    return rel_original, rel_thumb

# ---------------- Routes ----------------
@app.get("/")
def root():
    if session.get("user_id"):
        return redirect(url_for("home"))
    return redirect(url_for("login"))

# ----- Home (cards) -----
@app.get("/home")
@login_required
def home():
    cards = HomeCard.query.order_by(HomeCard.sort_order.asc(), HomeCard.id.asc()).all()
    return render_template("home.html", cards=cards)

@app.post("/home/card/<int:card_id>/update")
@login_required
def home_card_update(card_id):
    # auth: admin OR approver
    uid = session.get("user_id")
    me = User.query.get(uid) if uid else None
    if not me or not (me.is_admin or me.can_approve_users):
        abort(403)

    card = HomeCard.query.get_or_404(card_id)
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not title:
        flash("Title is required.", "warning")
        return redirect(url_for("home"))

    f = request.files.get("image")
    if f and f.filename:
        original = secure_filename(f.filename)
        ext = pathlib.Path(original).suffix.lower()
        try:
            head = f.stream.read(16); f.stream.seek(0)
            if _looks_like_image(head, ext):
                dest_dir = pathlib.Path(app.config["UPLOAD_ROOT"]) / "homecards" / str(card.id)
                thumbs_dir = dest_dir / "thumbs"
                dest_dir.mkdir(parents=True, exist_ok=True)
                thumbs_dir.mkdir(parents=True, exist_ok=True)

                unique = f"{uuid.uuid4().hex}{ext if ext in ALLOWED_EXTS else '.jpg'}"
                dest = dest_dir / unique
                f.save(dest)

                preview_name = f"{pathlib.Path(unique).stem}.jpg"
                preview_path = thumbs_dir / preview_name
                make_thumbnail(dest, preview_path, max_px=1200, quality=max(82, app.config["THUMB_QUALITY"]))
                card.image_path = str(pathlib.Path("homecards") / str(card.id) / "thumbs" / preview_name)
            else:
                flash("That file doesn't look like an image.", "warning")
        except Exception:
            flash("Failed to process the image.", "danger")

    card.title = title
    card.description = description
    db.session.commit()
    flash("Card updated.", "success")
    return redirect(url_for("home"))

# ----- Login / Logout -----
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid credentials", "danger")
            return render_template("login.html"), 401
        session.clear()
        session.permanent = True
        session["user_id"] = user.id
        return redirect(request.args.get("next") or url_for("home"))
    return render_template("login.html")

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----- Registration requests -----
@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("home"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")
        confirm  = (request.form.get("confirm") or "")
        reason   = (request.form.get("reason") or "").strip()

        if not username or not password or not confirm:
            flash("All fields are required.", "warning")
            return render_template("register.html"), 400
        if password != confirm:
            flash("Passwords do not match.", "warning")
            return render_template("register.html"), 400
        if len(password) < 8:
            flash("Use at least 8 characters for the password.", "warning")
            return render_template("register.html"), 400
        if User.query.filter_by(username=username).first():
            flash("Username is taken. Pick another.", "danger")
            return render_template("register.html"), 400
        if RegistrationRequest.query.filter_by(username=username).first():
            flash("There is already a pending/decided request for that username.", "danger")
            return render_template("register.html"), 400

        rr = RegistrationRequest(
            username=username,
            password_hash=generate_password_hash(password),
            reason=reason,
            status="pending",
        )
        db.session.add(rr)
        db.session.commit()
        flash("Request submitted. An admin will approve or deny it.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# ----- Admin Creation - 404 once created -----

from werkzeug.security import generate_password_hash

def _any_admin_exists() -> bool:
    return bool(User.query.filter_by(is_admin=True).first())

@app.route("/setup", methods=["GET", "POST"])
def setup_admin():
    # Only usable if there is no admin yet
    if _any_admin_exists():
        # Hide this endpoint once an admin exists
        abort(404)

    if request.method == "POST":
        mode = (request.form.get("mode") or "").strip()

        if mode == "promote":
            username = (request.form.get("username") or "").strip()
            u = User.query.filter_by(username=username).first()
            if not u:
                flash("User not found.", "danger")
                return redirect(url_for("setup_admin"))
            u.is_admin = True
            # (optional) grant your other perms so the admin sees all controls:
            u.can_travel_edit = True
            u.can_approve_users = True
            db.session.commit()
            flash(f"Promoted {u.username} to admin.", "success")
            return redirect(url_for("login"))

        elif mode == "create":
            new_username = (request.form.get("new_username") or "").strip()
            new_password = request.form.get("new_password") or ""
            if not new_username or not new_password:
                flash("Username and password are required.", "warning")
                return redirect(url_for("setup_admin"))
            if User.query.filter_by(username=new_username).first():
                flash("That username already exists.", "warning")
                return redirect(url_for("setup_admin"))

            u = User(
                username=new_username,
                password_hash=generate_password_hash(new_password),
                is_admin=True,
                can_travel_edit=True,
                can_approve_users=True,
            )
            db.session.add(u)
            db.session.commit()
            flash(f"Created admin user {u.username}.", "success")
            return redirect(url_for("login"))

        else:
            flash("Invalid request.", "danger")
            return redirect(url_for("setup_admin"))

    # GET: render the setup page with current users to pick from
    users = User.query.order_by(User.username.asc()).all()
    return render_template("setup_admin.html", users=users)

@app.get("/admin/requests")
@login_required
@approve_users_required
def admin_user_requests():
    pending = (RegistrationRequest.query
               .filter_by(status="pending")
               .order_by(RegistrationRequest.created_at.asc())
               .all())
    recent = (RegistrationRequest.query
              .filter(RegistrationRequest.status != "pending")
              .order_by(RegistrationRequest.decided_at.desc().nullslast())
              .limit(50).all())
    return render_template("admin_requests.html", pending=pending, recent=recent)

@app.get("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_users.html", users=users)

@app.post("/admin/users/<int:user_id>/update")
@login_required
@admin_required
def admin_users_update(user_id):
    u = User.query.get_or_404(user_id)
    # checkboxes are present → "on" when checked
    u.is_admin = bool(request.form.get("is_admin"))
    u.can_travel_edit = bool(request.form.get("can_travel_edit"))
    u.can_approve_users = bool(request.form.get("can_approve_users"))
    db.session.commit()
    flash(f"Updated permissions for {u.username}.", "success")
    return redirect(url_for("admin_users"))

@app.post("/admin/requests/<int:req_id>/approve")
@login_required
@approve_users_required
def admin_user_request_approve(req_id):
    rr = RegistrationRequest.query.get_or_404(req_id)
    if rr.status != "pending":
        flash("This request has already been decided.", "warning")
        return redirect(url_for("admin_user_requests"))
    if User.query.filter_by(username=rr.username).first():
        rr.status = "denied"; rr.decided_at = datetime.utcnow(); rr.decided_by_user_id = session.get("user_id")
        db.session.commit()
        flash(f"Username '{rr.username}' already exists. Request auto-denied.", "danger")
        return redirect(url_for("admin_user_requests"))
    new_user = User(
        username=rr.username,
        password_hash=rr.password_hash,
        can_travel_edit=False,
        can_approve_users=False
    )
    db.session.add(new_user)
    rr.status = "approved"
    rr.decided_at = datetime.utcnow()
    rr.decided_by_user_id = session.get("user_id")
    db.session.commit()
    flash(f"Approved and created user '{rr.username}'.", "success")
    return redirect(url_for("admin_user_requests"))

@app.get("/tracker/tags")
@login_required
def tracker_tags():
    """
    Tags directory for the Media Tracker.
    Supports optional ?type=<media_type> and ?q=<search>.
    """
    # inputs
    type_filter = (request.args.get("type") or "").strip().lower()
    q = (request.args.get("q") or "").strip().lower()

    # base query
    qry = Item.query
    if type_filter in MEDIA_TYPES:
        qry = qry.filter(Item.media_type == type_filter)

    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Item.tags.ilike(like),
                             Item.title.ilike(like),
                             Item.notes.ilike(like)))

    items = qry.all()

    # counts for the type pills (same as tracker list/menu)
    type_counts = {
        t: db.session.query(func.count(Item.id)).filter(Item.media_type == t).scalar() or 0
        for t in MEDIA_TYPES
    }

    # build tag counts from the items we just pulled
    counts = Counter()
    for it in items:
        if not it.tags:
            continue
        for raw in it.tags.split(","):
            tag = (raw or "").strip().lower()
            if not tag:
                continue
            counts[tag] += 1

    # if user typed q=, also filter the tag list itself
    if q:
        counts = Counter({tag: n for tag, n in counts.items() if q in tag})

    # group by first letter for headings (A, B, …, #)
    grouped = {}
    for tag, n in counts.items():
        letter = tag[:1].upper() if tag else "#"
        if not letter.isalpha():
            letter = "#"
        grouped.setdefault(letter, []).append((tag, n))

    # sort groups and entries
    letters = sorted(grouped.keys())
    for L in letters:
        grouped[L].sort(key=lambda x: x[0])

    return render_template(
        "tracker_tags.html",
        MEDIA_TYPES=MEDIA_TYPES,
        type_filter=(type_filter if type_filter in MEDIA_TYPES else ""),
        type_counts=type_counts,
        q=(request.args.get("q") or ""),
        # both a flat dict and a grouped view (use whichever you like in the template)
        tag_counts=dict(sorted(counts.items())),  # {'action': 12, ...}
        letters=letters,                          # ['#','A','B',...]
        grouped=grouped                           # {'A': [('action',12),...], ...}
    )


@app.post("/admin/requests/<int:req_id>/deny")
@login_required
@approve_users_required
def admin_user_request_deny(req_id):
    rr = RegistrationRequest.query.get_or_404(req_id)
    if rr.status != "pending":
        flash("This request has already been decided.", "warning")
        return redirect(url_for("admin_user_requests"))
    rr.status = "denied"
    rr.decided_at = datetime.utcnow()
    rr.decided_by_user_id = session.get("user_id")
    db.session.commit()
    flash(f"Denied request for '{rr.username}'.", "info")
    return redirect(url_for("admin_user_requests"))

# ----- Serve uploaded files (auth required) -----
@app.get("/u/<path:subpath>")
@login_required
def serve_upload(subpath):
    resp = send_from_directory(app.config["UPLOAD_ROOT"], subpath)
    resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
    return resp

# --- Dynamic rows fragment for AJAX (no full reload) ---
@app.route("/tracker/rows")
@login_required
def tracker_rows():
    # inputs
    type_filter = (request.args.get("type") or "book").lower()
    q = (request.args.get("q") or "").strip()
    tags = [t.strip().lower() for t in request.args.getlist("tag") if t.strip()]

    # build the query exactly like /tracker
    query = Item.query.filter(Item.media_type == type_filter)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Item.title.ilike(like),
                Item.tags.ilike(like),
                Item.notes.ilike(like),
            )
        )
    for t in tags:
        query = query.filter(Item.tags.ilike(f"%{t}%"))

    rows = query.order_by(Item.title.asc()).all()

    # keep comment reaction counts in sync (same as /tracker)
    uid = session.get("user_id")
    for r in rows:
        hydrate_comment_reactions(r.comments, uid, "item")

    # return just the tbody fragment
    return render_template(
        "_tracker_rows.html",
        rows=rows,
        type_filter=type_filter,
        tags=tags,
        q=q,
    )

# ----- Tracker (menu-first + create/list + comments) -----
@app.route("/tracker", methods=["GET", "POST"])
@login_required
def tracker():
    # Create on POST (handles type-specific fields + optional cover)
    if request.method == "POST":
        media_type = (request.form.get("media_type") or "").strip().lower()
        title = (request.form.get("title") or "").strip()
        # status/rating removed from UI; set a neutral legacy value
        status = "info"
        tags = (request.form.get("tags") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        release_status = (request.form.get("release_status") or "").strip() or None

        def to_int(v):
            try:
                return int(v)
            except Exception:
                return None

        # type-specific
        chapter_total = None
        seasons = None
        # rating removed (per user later)
        year = to_int(request.form.get("year"))
        runtime_mins = to_int(request.form.get("runtime_mins"))
        platforms = (request.form.get("platforms") or "").strip() or None

        if media_type in ("book", "manga", "manhwa"):
            chapter_total = to_int(request.form.get("chapter_total"))

        if media_type in ("show", "anime"):
            seasons = to_int(request.form.get("seasons"))

        if not title or not media_type:
            flash("Title and Type are required.", "danger")
            return redirect(url_for("tracker"))

        itm = Item(
            title=title,
            media_type=media_type,
            status=status,          # keep legacy column satisfied
            score=None,             # rating removed from item-level UI
            tags=tags,
            notes=notes,
            chapter_total=chapter_total,
            seasons=seasons,
            release_status=release_status,
            year=year,
            runtime_mins=runtime_mins,
            platforms=platforms,
        )
        db.session.add(itm)
        db.session.flush()  # need id for cover path

        # optional cover upload
        cover = request.files.get("cover")
        chapter_files = request.files.getlist("chapters")
        if chapter_files:
            existing_max = db.session.query(func.coalesce(func.max(Chapter.number), 0)).filter_by(item_id=itm.id).scalar() or 0
            next_num = existing_max + 1

            for f in chapter_files:
                if not f or not f.filename:
                    continue
                n = _infer_chapter_number(f.filename) or next_num
                if n == next_num:
                    next_num += 1

                rel = save_chapter_pdf(f, itm.id, n)
                ch = Chapter.query.filter_by(item_id=itm.id, number=n).first()
                if ch:
                    ch.source_path = rel  # replace existing chapter n
                else:
                    db.session.add(Chapter(item_id=itm.id, number=n, source_path=rel))
        if cover and cover.filename:
            rel, rel_thumb = save_item_cover(cover, itm.id)
            if rel and rel_thumb:
                itm.cover_path = rel
                itm.cover_thumb_path = rel_thumb
        
        source = request.files.get("source")
        if source and source.filename:
            rel_src = save_item_source(source, itm.id)
            if rel_src:
                itm.source_path = rel_src


        db.session.commit()
        return redirect(url_for("tracker", type=media_type) if media_type in MEDIA_TYPES else url_for("tracker"))

    # ---- List/menu screens on GET ----
    type_filter = (request.args.get("type") or "").lower()
    valid_type = type_filter in MEDIA_TYPES

    # counts for menu badges
    type_counts = {
        t: db.session.query(func.count(Item.id)).filter(Item.media_type == t).scalar() or 0
        for t in MEDIA_TYPES
    }

    if not valid_type:
        return render_template(
            "tracker.html",
            mode="menu",
            MEDIA_TYPES=MEDIA_TYPES,
            type_counts=type_counts,
            type_filter=None,
            rows=[],
            q="",
            tag=""
        )

    # List screen for chosen type (no status/rating filters; alpha sort)
    q = (request.args.get("q") or "").strip()
    tags = [t.strip().lower() for t in request.args.getlist("tag") if t.strip()]

    query = Item.query.filter(Item.media_type == type_filter)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Item.title.ilike(like), Item.tags.ilike(like), Item.notes.ilike(like)))

    for t in tags:
        query = query.filter(Item.tags.ilike(f"%{t}%"))

    rows = query.order_by(Item.title.asc()).all()

    # hydrate reactions for each item's comments
    uid = session.get("user_id")
    for r in rows:
        hydrate_comment_reactions(r.comments, uid, "item")

    return render_template(
        "tracker.html",
        mode="list",
        MEDIA_TYPES=MEDIA_TYPES,
        type_filter=type_filter,
        type_counts=type_counts,
        q=q,
        tags=tags,
        rows=rows
    )


@app.post("/tracker/<int:item_id>/update")
@login_required
def tracker_update(item_id):
    item = Item.query.get_or_404(item_id)

    title = (request.form.get("title") or "").strip()
    media_type = (request.form.get("media_type") or "").strip().lower()
    # status removed from UI — keep existing item.status (legacy)
    tags = (request.form.get("tags") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    release_status = (request.form.get("release_status") or "").strip() or None

    def to_int(v):
        try:
            return int(v)
        except Exception:
            return None

    if not title or not media_type:
        flash("Title and Type are required.", "danger")
        return redirect(url_for("tracker") + f"#item{item.id}")

    # reset type-specific fields
    item.chapter_total = None
    item.seasons = None
    item.score = None  # rating removed at item-level
    item.year = to_int(request.form.get("year"))
    item.runtime_mins = to_int(request.form.get("runtime_mins"))
    item.platforms = (request.form.get("platforms") or "").strip() or None

    if media_type in ("book", "manga", "manhwa"):
        item.chapter_total = to_int(request.form.get("chapter_total"))

    if media_type in ("show", "anime"):
        item.seasons = to_int(request.form.get("seasons"))

    # assign common fields
    item.title = title
    item.media_type = media_type
    # keep item.status as-is (legacy)
    item.tags = tags
    item.notes = notes
    item.release_status = release_status

    # optional cover re-upload
    cover = request.files.get("cover")
    # Multiple chapter PDFs (optional)
    chapter_files = request.files.getlist("chapters")
    if chapter_files:
        existing_max = db.session.query(func.coalesce(func.max(Chapter.number), 0)).filter_by(item_id=item.id).scalar() or 0
        next_num = existing_max + 1

        for f in chapter_files:
            if not f or not f.filename:
                continue
            n = _infer_chapter_number(f.filename) or next_num
            if n == next_num:
                next_num += 1

            rel = save_chapter_pdf(f, item.id, n)
            ch = Chapter.query.filter_by(item_id=item.id, number=n).first()
            if ch:
                ch.source_path = rel
            else:
                db.session.add(Chapter(item_id=item.id, number=n, source_path=rel))

    if cover and cover.filename:
        rel, rel_thumb = save_item_cover(cover, item.id)
        if rel and rel_thumb:
            item.cover_path = rel
            item.cover_thumb_path = rel_thumb

    source = request.files.get("source")
    if source and source.filename:
        rel_src = save_item_source(source, item.id)
        if rel_src:
            item.source_path = rel_src

    chapter_files = request.files.getlist("chapters")
    if chapter_files:
        existing_max = db.session.query(func.coalesce(func.max(Chapter.number), 0)).filter_by(item_id=item.id).scalar() or 0
        next_num = existing_max + 1

        for f in chapter_files:
            if not f or not f.filename:
                continue
            n = _infer_chapter_number(f.filename) or next_num
            if n == next_num:
                next_num += 1

            rel = save_chapter_pdf(f, item.id, n)
            ch = Chapter.query.filter_by(item_id=item.id, number=n).first()
            if ch:
                ch.source_path = rel
            else:
                db.session.add(Chapter(item_id=item.id, number=n, source_path=rel))


    db.session.commit()
    flash(f"Updated '{item.title}'.", "success")
    return redirect(url_for("tracker", type=item.media_type) + f"#item{item.id}")

@app.post("/tracker/<int:item_id>/chapter/<int:number>/delete")
@login_required
def delete_chapter(item_id, number):
    ch = Chapter.query.filter_by(item_id=item_id, number=number).first_or_404()
    db.session.delete(ch)
    db.session.commit()
    # keep modal open if called from inside it
    if request.headers.get("X-Requested-With") == "fetch" or request.form.get("ajax"):
        return ("", 204)
    return redirect(url_for("tracker", type=request.args.get("type", "book")))

@app.get("/tracker/<int:item_id>/chapters.json")
@login_required
def list_chapters(item_id):
    q = Chapter.query.filter_by(item_id=item_id).order_by(Chapter.number).all()
    return jsonify([{"n": c.number, "url": f"/u/{c.source_path}", "title": c.title or f"Chapter {c.number}"} for c in q])

# Item comments
@app.post("/tracker/<int:item_id>/comment")
@login_required
def tracker_comment_add(item_id):
    item = Item.query.get_or_404(item_id)
    uid = session.get("user_id")
    user = User.query.get(uid)
    if not user:
        abort(403)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Comment cannot be empty.", "warning")
        return redirect(url_for("tracker", type=item.media_type) + f"#item{item.id}")
    if len(body) > 2000:
        flash("Comment too long (max 2000 chars).", "warning")
        return redirect(url_for("tracker", type=item.media_type) + f"#item{item.id}")
    c = ItemComment(item_id=item.id, user_id=user.id, author=user.username, body=body)
    db.session.add(c)
    db.session.commit()
    flash("Comment added.", "success")
    return redirect(url_for("tracker", type=item.media_type) + f"#item{item.id}")

@app.post("/tracker/comment/<int:comment_id>/delete")
@login_required
def tracker_comment_delete(comment_id):
    c = ItemComment.query.get_or_404(comment_id)
    user = User.query.get(session.get("user_id"))
    if not user or (c.user_id != user.id and not user.can_approve_users):
        abort(403)
    item = Item.query.get(c.item_id)
    db.session.delete(c)
    db.session.commit()
    flash("Comment deleted.", "success")
    return redirect(url_for("tracker", type=item.media_type) + f"#item{item.id}")

# ----- Travel -----
@app.get("/travel")
@login_required
def travel():
    trips = (
        Trip.query
        .options(subqueryload(Trip.photos), subqueryload(Trip.user_comments))
        .order_by(Trip.created_at.desc())
        .all()
    )
    # hydrate reactions on comments
    uid = session.get("user_id")
    for t in trips:
        hydrate_comment_reactions(t.user_comments, uid, "trip")
    return render_template("travel.html", trips=trips)

@app.get("/api/trips")
@login_required
def api_trips():
    trips = Trip.query.filter(Trip.lat.isnot(None), Trip.lon.isnot(None)).order_by(Trip.created_at.desc()).all()
    return jsonify([{"id": t.id, "title": t.title, "lat": t.lat, "lon": t.lon} for t in trips])

@app.get("/fitness")
@login_required
def fitness():
    return render_template("fitness.html")

@app.post("/travel/new")
@login_required
@travel_edit_required
def travel_new():
    title = (request.form.get("title") or "").strip()
    address = (request.form.get("address") or "").strip()
    comments = (request.form.get("comments") or "").strip()
    lat_in = parse_coord(request.form.get("lat"))
    lon_in = parse_coord(request.form.get("lon"))
    if not title or not address:
        flash("Title and Address are required.", "danger")
        return redirect(url_for("travel"))

    trip = Trip(title=title, address=address, comments=comments)
    db.session.add(trip)
    db.session.flush()

    if valid_lat_lon(lat_in, lon_in):
        trip.lat, trip.lon = lat_in, lon_in
    else:
        trip.lat, trip.lon = geocode_address(address)

    saved_count, skipped = 0, 0
    files = request.files.getlist("photos")
    trip_dir = pathlib.Path(app.config["UPLOAD_ROOT"]) / "travel" / str(trip.id)
    thumbs_dir = trip_dir / "thumbs"
    trip_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    for f in files or []:
        if not f or not f.filename:
            continue
        original = secure_filename(f.filename)
        ext = pathlib.Path(original).suffix.lower()
        try:
            head = f.stream.read(16); f.stream.seek(0)
            if not _looks_like_image(head, ext):
                skipped += 1; continue
            unique = f"{uuid.uuid4().hex}{ext if ext in ALLOWED_EXTS else '.bin'}"
            dest = trip_dir / unique
            f.save(dest)
            thumb_name = f"{pathlib.Path(unique).stem}.jpg"
            thumb_path = thumbs_dir / thumb_name
            make_thumbnail(dest, thumb_path, app.config["THUMB_MAX_PX"], app.config["THUMB_QUALITY"])
            rel_path = str(pathlib.Path("travel") / str(trip.id) / unique)
            rel_thumb = str(pathlib.Path("travel") / str(trip.id) / "thumbs" / thumb_name)
            db.session.add(Photo(
                trip_id=trip.id,
                stored_path=rel_path,
                thumb_path=rel_thumb,
                original_name=original,
                mime_type=f.mimetype or "",
                size_bytes=dest.stat().st_size
            ))
            saved_count += 1
        except Exception:
            skipped += 1

    db.session.commit()
    msg = f"Saved trip '{trip.title}'."
    if trip.lat is None or trip.lon is None: msg += " (No map pin.)"
    msg += f" Photos: {saved_count} saved"
    if skipped: msg += f", {skipped} skipped"
    flash(msg + ".", "success")
    return redirect(url_for("travel"))

@app.post("/travel/<int:trip_id>/update")
@login_required
@travel_edit_required
def travel_update(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    title = (request.form.get("title") or "").strip()
    address = (request.form.get("address") or "").strip()
    comments = (request.form.get("comments") or "").strip()
    lat_in = parse_coord(request.form.get("lat"))
    lon_in = parse_coord(request.form.get("lon"))

    if not title or not address:
        flash("Title and Address are required.", "danger")
        return redirect(url_for("travel"))

    trip.title, trip.address, trip.comments = title, address, comments

    if valid_lat_lon(lat_in, lon_in):
        trip.lat, trip.lon = lat_in, lon_in
    else:
        lat, lon = geocode_address(address)
        trip.lat, trip.lon = lat, lon

    saved_count, skipped = 0, 0
    files = request.files.getlist("photos")
    if files:
        trip_dir = pathlib.Path(app.config["UPLOAD_ROOT"]) / "travel" / str(trip.id)
        thumbs_dir = trip_dir / "thumbs"
        trip_dir.mkdir(parents=True, exist_ok=True)
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if not f or not f.filename: continue
            original = secure_filename(f.filename)
            ext = pathlib.Path(original).suffix.lower()
            try:
                head = f.stream.read(16); f.stream.seek(0)
                if not _looks_like_image(head, ext): skipped += 1; continue
                unique = f"{uuid.uuid4().hex}{ext if ext in ALLOWED_EXTS else '.bin'}"
                dest = trip_dir / unique
                f.save(dest)
                thumb_name = f"{pathlib.Path(unique).stem}.jpg"
                thumb_path = thumbs_dir / thumb_name
                make_thumbnail(dest, thumb_path, app.config["THUMB_MAX_PX"], app.config["THUMB_QUALITY"])
                rel_path = str(pathlib.Path("travel") / str(trip.id) / unique)
                rel_thumb = str(pathlib.Path("travel") / str(trip.id) / "thumbs" / thumb_name)
                db.session.add(Photo(
                    trip_id=trip.id,
                    stored_path=rel_path,
                    thumb_path=rel_thumb,
                    original_name=original,
                    mime_type=f.mimetype or "",
                    size_bytes=dest.stat().st_size
                ))
                saved_count += 1
            except Exception:
                skipped += 1

    db.session.commit()
    msg = f"Updated trip '{trip.title}'."
    if saved_count or skipped:
        msg += f" Photos added: {saved_count}" + (f", {skipped} skipped" if skipped else "")
    flash(msg, "success")
    return redirect(url_for("travel"))

# ----- Comments on trips -----
@app.post("/travel/<int:trip_id>/comment")
@login_required
def travel_comment_add(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    uid = session.get("user_id")
    user = User.query.get(uid)
    if not user:
        abort(403)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Comment cannot be empty.", "warning")
        return redirect(url_for("travel") + f"#trip{trip.id}")
    if len(body) > 2000:
        flash("Comment too long (max 2000 chars).", "warning")
        return redirect(url_for("travel") + f"#trip{trip.id}")
    c = Comment(trip_id=trip.id, user_id=user.id, author=user.username, body=body)
    db.session.add(c)
    db.session.commit()
    flash("Comment added.", "success")
    return redirect(url_for("travel") + f"#trip{trip.id}")

@app.post("/travel/comment/<int:comment_id>/delete")
@login_required
def travel_comment_delete(comment_id):
    c = Comment.query.get_or_404(comment_id)
    user = User.query.get(session.get("user_id"))
    if not user or (c.user_id != user.id and not user.can_travel_edit):
        abort(403)
    trip_id = c.trip_id
    db.session.delete(c)
    db.session.commit()
    flash("Comment deleted.", "success")
    return redirect(url_for("travel") + f"#trip{trip_id}")

# ----- Reactions API (like/dislike) -----
@app.post("/api/comments/<kind>/<int:comment_id>/react")
@login_required
def api_comment_react(kind, comment_id):
    kind = (kind or "").lower()
    if kind not in ("trip", "item"):
        return jsonify(ok=False, error="bad kind"), 400

    # must exist
    target = Comment if kind == "trip" else ItemComment
    if not target.query.get(comment_id):
        return jsonify(ok=False, error="not found"), 404

    uid = session.get("user_id")
    if not uid:
        return jsonify(ok=False, error="auth"), 401

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").lower()
    if action not in ("like", "dislike"):
        return jsonify(ok=False, error="bad action"), 400
    val = 1 if action == "like" else -1

    rec = (CommentReaction.query
           .filter_by(kind=kind, comment_id=comment_id, user_id=uid)
           .first())

    if rec is None:
        rec = CommentReaction(kind=kind, comment_id=comment_id, user_id=uid, value=val)
        db.session.add(rec)
        user_reaction = val
    elif rec.value == val:
        db.session.delete(rec)
        user_reaction = 0
    else:
        rec.value = val
        user_reaction = val

    db.session.commit()

    likes = (db.session.query(func.count(CommentReaction.id))
             .filter_by(kind=kind, comment_id=comment_id, value=1).scalar()) or 0
    dislikes = (db.session.query(func.count(CommentReaction.id))
                .filter_by(kind=kind, comment_id=comment_id, value=-1).scalar()) or 0

    return jsonify(
        ok=True,
        likes=int(likes),
        dislikes=int(dislikes),
        user_reaction=("like" if user_reaction == 1 else "dislike" if user_reaction == -1 else None)
    )

# ----- 413 handler -----
@app.errorhandler(RequestEntityTooLarge)
def handle_413(e):
    flash("That upload was too large. Try fewer/smaller photos or upload in batches.", "danger")
    return redirect(url_for("travel"))

@app.get("/wedding")
@login_required
@admin_required
def wedding_index():
    # latest first so new stuff floats up
    ideas = (WeddingItem.query.filter_by(kind="idea")
             .order_by(WeddingItem.created_at.desc()).limit(20).all())
    links = (WeddingItem.query.filter_by(kind="link")
             .order_by(WeddingItem.created_at.desc()).limit(20).all())
    rings = (WeddingItem.query.filter_by(kind="ring")
             .order_by(WeddingItem.created_at.desc()).limit(24).all())
    cakes = (WeddingItem.query.filter_by(kind="cake")
             .order_by(WeddingItem.created_at.desc()).limit(24).all())
    photos = (WeddingItem.query.filter_by(kind="photo")
              .order_by(WeddingItem.created_at.desc()).limit(24).all())
    vendors = (WeddingItem.query.filter(WeddingItem.kind.in_(("vendor","venue")))
               .order_by(WeddingItem.title.asc()).all())
    return render_template("wedding/index.html", ideas=ideas, links=links,
                           rings=rings, cakes=cakes, photos=photos, vendors=vendors)

@app.post("/wedding/idea")
@login_required
@admin_required
def wedding_add_idea():
    title = (request.form.get("title") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    if not title:
        flash("Idea needs at least a short title.", "warning")
        return redirect(url_for("wedding_index"))
    item = WeddingItem(kind="idea", title=title, notes=notes,
                       created_by_user_id=session.get("user_id"))
    db.session.add(item); db.session.commit()
    flash("Idea saved.", "success")
    return redirect(url_for("wedding_index"))

@app.get("/wedding/panel")
@login_required
@admin_required
def wedding_panel():
    kind = (request.args.get("kind") or "").strip().lower()
    if kind == "ideas":
        items = WeddingItem.query.filter_by(kind="idea").order_by(WeddingItem.created_at.desc()).limit(50).all()
        return render_template("wedding/panel_ideas.html", items=items)

    if kind == "links":
        items = WeddingItem.query.filter_by(kind="link").order_by(WeddingItem.created_at.desc()).limit(50).all()
        return render_template("wedding/panel_links.html", items=items)

    if kind == "boards":
        # which sub-board and whether to show only favorites
        sub = request.args.get("sub") or "rings"
        starred_only = (request.args.get("starred") in ("1", "true", "on"))

        kind_map = {
            "rings": "ring",
            "cakes": "cake",
            "photos": "photo",
            "bridesmaids": "bridesmaid",
            "groomsmen": "groomsman",
            "aesthetic": "aesthetic",
        }

        q = WeddingItem.query.filter_by(
            kind=kind_map.get(sub, "ring")
        ).order_by(WeddingItem.id.desc())

        if starred_only:
            q = q.filter(WeddingItem.is_starred.is_(True))

        items = q.all()

        return render_template(
            "wedding/panel_boards.html",
            sub=sub,
            items=items,
            starred=starred_only,
        )



    if kind == "venues":
        venues = WeddingItem.query.filter_by(kind="venue").order_by(WeddingItem.title.asc()).all()
        vendors = WeddingItem.query.filter_by(kind="vendor").order_by(WeddingItem.title.asc()).all()
        return render_template("wedding/panel_venues.html", venues=venues, vendors=vendors)

    if kind == "ceremony":
        steps = WeddingItem.query.filter_by(kind="ceremony").order_by(WeddingItem.meta["order"].as_integer()).all()
        return render_template("wedding/panel_ceremony.html", steps=steps)

    if kind == "reception":
        events = WeddingItem.query.filter_by(kind="reception").order_by(WeddingItem.meta["order"].as_integer()).all()
        return render_template("wedding/panel_reception.html", events=events)

    if kind == "tasks":
        tasks = WeddingItem.query.filter_by(kind="task").order_by(WeddingItem.meta["due"].desc().nullslast()).all()
        return render_template("wedding/panel_tasks.html", tasks=tasks)
    
    if kind == "seating":
        tables = SeatingTable.query.order_by(SeatingTable.name.asc()).all()
        guests = Guest.query.order_by(Guest.name.asc()).all()
        return render_template("wedding/panel_seating.html", tables=tables, guests=guests)

    if kind == "budget":
        items = BudgetItem.query.order_by(BudgetItem.category.asc(), BudgetItem.item.asc()).all()
        total_est = sum(i.estimate or 0 for i in items)
        total_act = sum(i.actual or 0 for i in items if i.actual is not None)
        return render_template("wedding/panel_budget.html", items=items,
                               total_est=total_est, total_act=total_act)

    return ("Unknown panel", 400)

@app.post("/wedding/item/<int:item_id>/title")
@login_required
@admin_required
def wedding_item_title(item_id):
    it = WeddingItem.query.get_or_404(item_id)
    title = (request.form.get("title") or "").strip()
    it.title = title or it.title
    db.session.commit()
    return ("", 204)

@app.post("/wedding/seating/table/add")
@login_required
@admin_required
def seating_table_add():
    name = (request.form.get("name") or "").strip() or "Table"
    capacity = int(request.form.get("capacity") or 8)
    t = SeatingTable(name=name, capacity=capacity)
    db.session.add(t); db.session.commit()
    flash("Table added.", "success")
    return redirect(url_for("wedding_index"))

@app.post("/wedding/item/<int:item_id>/star")
@login_required
@admin_required
def wedding_item_star(item_id):
    it = WeddingItem.query.get_or_404(item_id)
    # Toggle unless explicit "on" is provided
    raw = (request.form.get("on") or request.args.get("on") or "").lower()
    if raw in ("1","true","on","yes"):
        it.is_starred = True
    elif raw in ("0","false","off","no"):
        it.is_starred = False
    else:
        it.is_starred = not bool(it.is_starred)
    db.session.commit()
    return jsonify(ok=True, starred=bool(it.is_starred))

@app.post("/wedding/seating/guest/add")
@login_required
@admin_required
def seating_guest_add():
    name = (request.form.get("name") or "").strip()
    side = (request.form.get("side") or "").strip() or None
    email = (request.form.get("email") or "").strip() or None
    phone = (request.form.get("phone") or "").strip() or None
    rsvp = (request.form.get("rsvp") or "unknown").strip()
    table_id = request.form.get("table_id")
    g = Guest(name=name, side=side, email=email, phone=phone, rsvp=rsvp,
              table_id=int(table_id) if table_id else None)
    db.session.add(g); db.session.commit()
    flash("Guest added.", "success")
    return redirect(url_for("wedding_index"))

@app.post("/wedding/seating/guest/assign")
@login_required
@admin_required
def seating_guest_assign():
    gid = int(request.form["guest_id"])
    table_id = request.form.get("table_id")
    g = Guest.query.get_or_404(gid)
    g.table_id = int(table_id) if table_id else None
    db.session.commit()
    return redirect(url_for("wedding_index"))

@app.post("/wedding/seating/table/photo/<int:table_id>")
@login_required
@admin_required
def seating_table_photo(table_id):
    table = SeatingTable.query.get_or_404(table_id)
    which = request.form.get("which")  # 'tiny' or 'rosie'
    f = request.files.get("image")
    if which not in ("tiny", "rosie") or not f or not f.filename:
        abort(400)
    rel, thumb = save_wedding_image(f, "tables", table_id)
    if which == "tiny": table.img_tiny = rel or table.img_tiny
    else: table.img_rosie = rel or table.img_rosie
    db.session.commit()
    flash("Table photo saved.", "success")
    return redirect(url_for("wedding_index"))

# CEREMONY: add step (order defaults to next)
@app.post("/wedding/ceremony/step")
@login_required
@admin_required
def wedding_add_ceremony_step():
    title = (request.form.get("title") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    order = request.form.get("order")
    try:
        order = int(order) if order is not None and order != "" else None
    except:
        order = None
    if order is None:
        last = db.session.execute(text("SELECT MAX(json_extract(meta,'$.order')) FROM wedding_item WHERE kind='ceremony'")).scalar()
        order = int(last) + 1 if last is not None else 1
    it = WeddingItem(kind="ceremony", title=title or f"Step {order}", notes=notes,
                     meta={"order": order}, created_by_user_id=session.get("user_id"))
    db.session.add(it); db.session.commit()
    flash("Ceremony step added.", "success")
    return redirect(url_for("wedding_index"))

# RECEPTION: add event (order + type)
@app.post("/wedding/reception/event")
@login_required
@admin_required
def wedding_add_reception_event():
    title = (request.form.get("title") or "").strip()
    etype = (request.form.get("etype") or "event").strip()   # e.g., 'speech','dance','announcement'
    order = request.form.get("order")
    try:
        order = int(order) if order else None
    except:
        order = None
    if order is None:
        last = db.session.execute(text("SELECT MAX(json_extract(meta,'$.order')) FROM wedding_item WHERE kind='reception'")).scalar()
        order = int(last) + 1 if last is not None else 1
    it = WeddingItem(kind="reception", title=title or f"Event {order}",
                     meta={"order": order, "type": etype}, created_by_user_id=session.get("user_id"))
    db.session.add(it); db.session.commit()
    flash("Reception event added.", "success")
    return redirect(url_for("wedding_index"))

# TASKS: add task with owner/due/status
@app.post("/wedding/tasks/add")
@login_required
@admin_required
def wedding_tasks_add():
    title = (request.form.get("title") or "").strip()
    owner = (request.form.get("owner") or "Tiny").strip()
    due   = (request.form.get("due") or "").strip()
    status = (request.form.get("status") or "todo").strip()
    meta = {"owner": owner, "status": status}
    if due:
        meta["due"] = due   # ISO yyyy-mm-dd string is fine
    it = WeddingItem(kind="task", title=title or "Untitled task",
                     meta=meta, created_by_user_id=session.get("user_id"))
    db.session.add(it); db.session.commit()
    flash("Task added.", "success")
    return redirect(url_for("wedding_index"))

@app.post("/wedding/link")
@login_required
@admin_required
def wedding_add_link():
    title = (request.form.get("title") or "").strip()
    url   = (request.form.get("url") or "").strip()
    ts    = (request.form.get("url_ts") or "").strip()
    def to_seconds(s):
        # supports "90", "1:30", "01:02:03"
        if not s: return None
        parts = [int(p) for p in s.split(":")]
        if len(parts) == 1: return parts[0]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        return None
    if not title or not url:
        flash("Link needs a title and a URL.", "warning")
        return redirect(url_for("wedding_index"))
    item = WeddingItem(kind="link", title=title, url=url, url_ts=to_seconds(ts),
                       created_by_user_id=session.get("user_id"))
    db.session.add(item); db.session.commit()
    flash("Link saved.", "success")
    return redirect(url_for("wedding_index"))

@app.get("/wedding/export/ceremony")
@login_required
@admin_required
def export_ceremony_html():
    steps = WeddingItem.query.filter_by(kind="ceremony").all()
    steps.sort(key=lambda i: (i.meta or {}).get("order", 10**9))
    return render_template("wedding/export_ceremony.html", steps=steps)

@app.post("/wedding/budget/add")
@login_required
@admin_required
def budget_add():
    cat = (request.form.get("category") or "General").strip()
    item = (request.form.get("item") or "Item").strip()
    est = int(float(request.form.get("estimate") or 0) * 100)  # dollars -> cents
    act_raw = request.form.get("actual")
    act = int(float(act_raw) * 100) if act_raw else None
    paid = bool(request.form.get("paid"))
    url  = (request.form.get("vendor_url") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    due = request.form.get("due_date") or None
    bi = BudgetItem(category=cat, item=item, estimate=est, actual=act, paid=paid,
                    vendor_url=url, notes=notes, due_date=due)
    db.session.add(bi); db.session.commit()
    flash("Budget item added.", "success")
    return redirect(url_for("wedding_index"))

@app.post("/wedding/upload/<bucket>")
@login_required
@admin_required
def wedding_upload(bucket):
    # allow all Boards buckets
    allowed = {"rings", "cakes", "photos", "bridesmaids", "groomsmen", "aesthetic"}
    if bucket not in allowed:
        abort(400)

    # map bucket -> WeddingItem.kind (DB)
    kind_map = {
        "rings": "ring",
        "cakes": "cake",
        "photos": "photo",
        "bridesmaids": "bridesmaid",
        "groomsmen": "groomsman",
        "aesthetic": "aesthetic",
    }
    default_title = {
        "rings": "Ring",
        "cakes": "Cake",
        "photos": "Photo",
        "bridesmaids": "Bridesmaid fit",
        "groomsmen": "Groomsman fit",
        "aesthetic": "Aesthetic",
    }

    files = request.files.getlist("images") or []
    saved = 0

    for f in files:
        if not f or not f.filename:
            continue

        it = WeddingItem(
            kind=kind_map[bucket],
            title=(request.form.get("title") or "").strip() or default_title[bucket],
            created_by_user_id=session.get("user_id"),
        )
        db.session.add(it)
        db.session.flush()  # need id for file path

        rel, thumb = save_wedding_image(f, bucket, it.id)
        if rel and thumb:
            # store the thumb path for grid display
            it.image_path = thumb
            saved += 1
        else:
            # clean up if the file wasn’t a valid image
            db.session.delete(it)

    db.session.commit()
    # flash(f"Uploaded {saved} image(s) to {bucket}.", "success" if saved else "warning")
    # fetch() in the panel ignores the response body; redirect is fine
    # return redirect(url_for("wedding_index"))
    return ("", 204)

@app.post("/wedding/item/<int:item_id>/delete")
@login_required
@admin_required
def wedding_item_delete(item_id):
    it = WeddingItem.query.get_or_404(item_id)
    db.session.delete(it)
    db.session.commit()
    return ("", 204)

@app.post("/wedding/vendor")
@login_required
@admin_required
def wedding_add_vendor():
    title = (request.form.get("title") or "").strip()
    url   = (request.form.get("url") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    kind  = (request.form.get("kind") or "vendor").strip().lower()  # 'vendor' or 'venue'
    if kind not in ("vendor","venue"): kind = "vendor"
    if not title:
        flash("Please give it a name.", "warning")
        return redirect(url_for("wedding_index"))
    item = WeddingItem(kind=kind, title=title, url=url, notes=notes,
                       created_by_user_id=session.get("user_id"))
    db.session.add(item); db.session.commit()
    flash("Saved.", "success")
    return redirect(url_for("wedding_index"))

@app.post("/wedding/<int:item_id>/delete")
@login_required
@admin_required
def wedding_delete(item_id):
    it = WeddingItem.query.get_or_404(item_id)
    db.session.delete(it); db.session.commit()
    flash("Deleted.", "info")
    return redirect(url_for("wedding_index"))


@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
