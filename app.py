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

DEFAULT_STATUSES = ["current", "waiting", "finished"]
SERIAL_TYPES = ["manga", "manhwa"]
SERIAL_STATUSES = ["ongoing", "completed", "hiatus", "canceled"]

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    can_travel_edit = db.Column(db.Boolean, nullable=False, default=False)
    can_approve_users = db.Column(db.Boolean, nullable=False, default=False)

class HomeCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, index=True)  # "travel", "tracker", etc.
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    image_path = db.Column(db.String(600))  # relative path served via /u/<path>
    url = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    media_type = db.Column(db.String(20), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    score = db.Column(db.Integer)
    tags = db.Column(db.String(200))
    notes = db.Column(db.Text)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    chapter_current = db.Column(db.Integer)
    chapter_total   = db.Column(db.Integer)
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

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False, index=True)
    stored_path = db.Column(db.String(600), nullable=False)
    thumb_path = db.Column(db.String(600))
    original_name = db.Column(db.String(300))
    mime_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    # user table
    cols_user = [r[1] for r in db.session.execute(text("PRAGMA table_info(user)")).fetchall()]
    if "can_travel_edit" not in cols_user:
        db.session.execute(text("ALTER TABLE user ADD COLUMN can_travel_edit INTEGER NOT NULL DEFAULT 0"))
    if "can_approve_users" not in cols_user:
        db.session.execute(text("ALTER TABLE user ADD COLUMN can_approve_users INTEGER NOT NULL DEFAULT 0"))

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

    # item table (chapters)
    cols_item = [r[1] for r in db.session.execute(text("PRAGMA table_info(item)")).fetchall()]
    if "chapter_current" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN chapter_current INTEGER"))
    if "chapter_total" not in cols_item:
        db.session.execute(text("ALTER TABLE item ADD COLUMN chapter_total INTEGER"))

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
    
    db.session.commit()

    # db.session.commit()
    # if db.session.query(HomeCard).count() == 0:
    #     db.session.add(HomeCard(
    #         key="travel",
    #         title="T&R Travel Log",
    #         description="Map our adventures, add photos, and notes.",
    #         url="/travel",
    #         sort_order=10
    #     ))
    #     db.session.add(HomeCard(
    #         key="tracker",
    #         title="Media Tracker",
    #         description="Track books, manga/manhwa, movies, shows, and more.",
    #         url="/tracker",
    #         sort_order=20
    #     ))
    #     db.session.add(HomeCard(
    #         key="fitness",
    #         title="Fitness",
    #         description="Section for keeping track of and looking at trends for personal fitness",
    #         url="/fitness",
    #         sort_order=30
    #     ))
    #     db.session.commit()

    # db.session.commit()

# ---------------- Template helpers ----------------
@app.get("/favicon.ico")
def favicon_root():
    return send_from_directory(
        os.path.join(app.root_path, "static", "icons"), "favicon.ico",
        cache_timeout=60*60*24*30
    )

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
@approve_users_required
def home_card_update(card_id):
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
        password = request.form.get("password") or ""
        confirm  = request.form.get("confirm") or ""
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

# ----- Tracker (menu-first + create/list + comments) -----
@app.route("/tracker", methods=["GET", "POST"])
@login_required
def tracker():
    # Create on POST
    if request.method == "POST":
        media_type = request.form["media_type"]

        def to_int(v):
            try:
                return int(v)
            except Exception:
                return None

        if media_type.lower() in ("book", "manga", "manhwa"):
            ch_cur = to_int(request.form.get("chapter_current"))
            ch_tot = to_int(request.form.get("chapter_total"))
        else:
            ch_cur = None
            ch_tot = None

        itm = Item(
            title=request.form["title"].strip(),
            media_type=media_type,
            status=request.form["status"],
            score=parse_score(request.form.get("score")),
            tags=request.form.get("tags", "").strip(),
            notes=request.form.get("notes", "").strip(),
            chapter_current=ch_cur,
            chapter_total=ch_tot,
        )
        db.session.add(itm)
        db.session.commit()
        return redirect(url_for("tracker", type=media_type) if media_type in MEDIA_TYPES else url_for("tracker"))

    # Menu-first UX
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
            STATUS_OPTIONS=[],
            status_filter="",
            q=""
        )

    # List screen for chosen type
    q = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "all").lower()

    if type_filter in ("manga", "manhwa"):
        status_options = SERIAL_STATUSES[:]
    else:
        status_options = DEFAULT_STATUSES[:]

    if status_filter not in status_options and status_filter != "all":
        status_filter = "all"

    query = Item.query.filter(Item.media_type == type_filter)
    if status_filter != "all":
        query = query.filter(Item.status == status_filter)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Item.title.ilike(like), Item.tags.ilike(like), Item.notes.ilike(like)))

    rows = (query
            .order_by(Item.added_at.desc())
            .options(subqueryload(Item.comments))
            .all())

    # hydrate reactions for each item's comments
    uid = session.get("user_id")
    for r in rows:
        hydrate_comment_reactions(r.comments, uid, "item")

    return render_template(
        "tracker.html",
        mode="list",
        MEDIA_TYPES=MEDIA_TYPES,
        STATUS_OPTIONS=status_options,
        status_filter=status_filter,
        type_filter=type_filter,
        type_counts=type_counts,
        q=q,
        rows=rows
    )

# ----- Tracker update (EDIT) -----
@app.post("/tracker/<int:item_id>/update")
@login_required
def tracker_update(item_id):
    item = Item.query.get_or_404(item_id)

    title = (request.form.get("title") or "").strip()
    media_type = (request.form.get("media_type") or "").strip().lower()
    status = (request.form.get("status") or "").strip().lower()
    score = parse_score(request.form.get("score"))
    tags = (request.form.get("tags") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    def to_int(v):
        try: return int(v)
        except Exception: return None

    if media_type in ("book", "manga", "manhwa"):
        ch_cur = to_int(request.form.get("chapter_current"))
        ch_tot = to_int(request.form.get("chapter_total"))
    else:
        ch_cur = None
        ch_tot = None

    if not title or not media_type or not status:
        flash("Title, Type and Status are required.", "danger")
        return redirect(url_for("tracker") + f"#item{item.id}")

    item.title = title
    item.media_type = media_type
    item.status = status
    item.score = score
    item.tags = tags
    item.notes = notes
    item.chapter_current = ch_cur
    item.chapter_total = ch_tot

    db.session.commit()
    flash(f"Updated '{item.title}'.", "success")
    return redirect(url_for("tracker", type=item.media_type) + f"#item{item.id}")

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

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
