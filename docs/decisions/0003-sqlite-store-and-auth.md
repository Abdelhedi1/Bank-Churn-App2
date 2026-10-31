# 0003 — SQLite store, session auth, roles and audit
Status: accepted. SQLite (Repository in `app/db.py`) keeps setup simple for a course project; swap for PostgreSQL later by changing only `db.py`. Session login with hashed passwords, four roles, CSRF header, audit log for customer views/exports/logins.
