#!/usr/bin/env python3
import sys
from getpass import getpass
from werkzeug.security import generate_password_hash
from app import app, db, User

USAGE = """Usage:
  manage.py create <username>
  manage.py set-password <username>
  manage.py travel_edit <username> on|off
"""

def create_user(username: str) -> int:
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print("User already exists.")
            return 1
        pw1 = getpass("Password: "); pw2 = getpass("Confirm: ")
        if pw1 != pw2:
            print("Passwords do not match."); return 1
        u = User(username=username, password_hash=generate_password_hash(pw1))
        db.session.add(u); db.session.commit()
        print(f"Created user '{username}'"); return 0

def set_password(username: str) -> int:
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u: print("User not found."); return 1
        pw1 = getpass("New password: "); pw2 = getpass("Confirm: ")
        if pw1 != pw2: print("Passwords do not match."); return 1
        u.password_hash = generate_password_hash(pw1); db.session.commit()
        print("Password updated."); return 0

def travel_edit(username: str, onoff: str) -> int:
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u: print("User not found."); return 1
        u.can_travel_edit = (onoff.lower() == "on")
        db.session.commit()
        print(f"can_travel_edit for '{username}': {u.can_travel_edit}")
        return 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(USAGE); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "create" and len(sys.argv) == 3:
        sys.exit(create_user(sys.argv[2]))
    if cmd == "set-password" and len(sys.argv) == 3:
        sys.exit(set_password(sys.argv[2]))
    if cmd == "travel_edit" and len(sys.argv) == 4 and sys.argv[3].lower() in ("on","off"):
        sys.exit(travel_edit(sys.argv[2], sys.argv[3]))
    print(USAGE); sys.exit(1)

