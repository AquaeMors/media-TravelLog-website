# TinyChuck — Media & Travel Log

A personal web app built with **Flask**, **SQLite**, and **Bootstrap** that provides:

- **Media Tracker** — Track books, anime, manga/manhwa, movies, shows, games, and more.  
- **Travel Log** — Map trips, upload photos, and add comments.  
- **Admin Features** — Approve/deny new account requests, edit dashboard cards, manage content.

---

## 🚀 Features

### 🔑 Authentication
- Login / logout with hashed passwords.
- Registration via request → admin approval/denial.
- Session security (HTTPOnly; secure cookies when HTTPS).

### 🎬 Media Tracker
- Types: `book`, `movie`, `show`, `anime`, `manga`, `manhwa`, `game`, `other`.
- Track **status**, **score (0–10)**, **tags**, and **chapters** (for book/manga/manhwa).
- Comments per item.
- Modals for add/edit; dynamic status + chapter fields.

### 🌍 Travel Log
- Leaflet + OpenStreetMap map with pins.
- Trips: title, address, notes, optional lat/lon.
- Auto‑geocoding fallback (Nominatim) when lat/lon missing.
- Photo uploads with server‑side thumbnailing (Pillow).
- Comments per trip and lazy‑loading photo gallery.

### 👨‍💻 Admin Tools
- Approve/deny account requests, see recent decisions.
- Edit homepage cards (title/description/image).
- Per‑user permissions:
  - `can_travel_edit` for trip edits/uploads.
  - `can_approve_users` for admin actions.

---

## 📂 Project Structure

```
/project-root
│
├── app.py                 # Flask app, models, routes, helpers
│
├── templates/             # Jinja2 templates
│   ├── home.html
│   ├── login.html
│   ├── register.html
│   ├── admin_requests.html
│   ├── tracker.html
│   └── travel.html
│
├── static/                # CSS/JS
│   ├── home.css
│   ├── tracker.css
│   ├── travel.css
│   ├── tracker.js
│   └── travel.js
│
├── uploads/               # (created at runtime) user uploads + thumbnails
└── README.md
```

---

## ⚙️ Setup

### Requirements
- Python 3.9+
- Virtualenv recommended
- Git (if pushing to GitHub)

### Installation

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

If you don’t yet have `requirements.txt`, create it with:

```
Flask
Flask-SQLAlchemy
Werkzeug
Pillow
```

### Environment Variables

| Variable          | Default                | Description                                  |
|-------------------|------------------------|----------------------------------------------|
| `SECRET_KEY`      | `dev-change-me`        | Flask session secret                          |
| `UPLOAD_ROOT`     | `/opt/media/uploads`   | Directory for uploaded files & thumbnails     |
| `THUMB_MAX_PX`    | `512`                  | Max thumbnail edge (px)                       |
| `THUMB_QUALITY`   | `82`                   | JPEG thumbnail quality                        |
| `COOKIE_INSECURE` | unset (secure cookies) | Set (any value) to allow non‑HTTPS cookies    |

### Database & Uploads

- SQLite auto‑creates at: `/opt/media/media.db`
- Tables and two homepage cards seed on first run.

Create media directories (if not present) and give your user write access:

```bash
sudo mkdir -p /opt/media/uploads
sudo chown -R "$USER":"$USER" /opt/media
```

---

## ▶️ Running (Development)

```bash
# Option 1: run the script directly
python app.py

# Option 2: flask run
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=8000
```

Open: `http://SERVER_IP:8000`

---

## 🔐 Admin & Accounts

1. Visit `/register` to submit an account request.  
2. An admin logs in and approves/denies at `/admin/requests`.  
3. Admins can grant permissions (e.g., `can_travel_edit`, `can_approve_users`) by editing the user row in the DB if needed.

---

## 🔧 Key Routes

| Route                | Method(s) | Purpose                                |
|----------------------|-----------|----------------------------------------|
| `/`                  | GET       | Redirects to `/home` or `/login`       |
| `/home`              | GET       | Dashboard cards                        |
| `/login`             | GET/POST  | Sign in                                |
| `/logout`            | POST      | Sign out                               |
| `/register`          | GET/POST  | Submit registration request            |
| `/admin/requests`    | GET       | Admin view of pending/decided requests |
| `/tracker`           | GET/POST  | Media tracker list/add                 |
| `/tracker/<id>/…`    | POST      | Update item / add comment / delete     |
| `/travel`            | GET       | Travel log page                        |
| `/travel/new`        | POST      | Create trip                            |
| `/travel/<id>/…`     | POST      | Update trip / comment / delete         |
| `/api/trips`         | GET       | JSON list of trips with pins           |
| `/u/<path>`          | GET       | Serve uploaded files (auth required)   |

---

## ☁️ Put This on Your Server & Push to GitHub

### A) Add the README (and requirements) on the server

```bash
# From your project folder on the server
nano README.md     # paste this file, save/exit
nano requirements.txt
# Paste:
# Flask
# Flask-SQLAlchemy
# Werkzeug
# Pillow
```

Install deps & run (once) to verify:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

### B) Connect your server repo to GitHub (SSH)

1) **Install Git & set identity (once):**
```bash
sudo apt-get update && sudo apt-get install -y git
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

2) **Generate an SSH key (server → GitHub):**
```bash
ssh-keygen -t ed25519 -C "server-github-key"
cat ~/.ssh/id_ed25519.pub
```
Copy the printed key into **GitHub → Settings → SSH and GPG keys → New SSH key**.  
Test:
```bash
ssh -T git@github.com
```

3) **Create an empty GitHub repo** (e.g., `tinychuck`). Do not add a README there.

4) **Initialize Git in your server project and push:**
```bash
cd /path/to/your/project
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:YOUR_USERNAME/tinychuck.git
git push -u origin main
```

### C) Work from another computer

```bash
# Set up an SSH key on that machine and add to GitHub (same steps as above)
git clone git@github.com:YOUR_USERNAME/tinychuck.git
cd tinychuck
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Make changes and push:

```bash
git checkout -b feature/my-change   # optional
git add -A
git commit -m "Implement X"
git push -u origin feature/my-change
```

Deploy updates **back on the server**:

```bash
cd /path/to/your/project
git pull
source venv/bin/activate
pip install -r requirements.txt      # if deps changed
# restart your app process (python app.py / gunicorn / systemd)
```

> Want a production setup later? Ask for a `gunicorn` + `systemd` unit file and an Nginx reverse‑proxy snippet.

---

## 📜 License

MIT — modify and self‑host freely.
<<<<<<< HEAD

=======
>>>>>>> 9f528e6 (Initial commit)
