#!/usr/bin/env bash
# Build step for a platform that runs a script before starting the web process
# (Render, Railway, and similar). Fails the deploy on any error.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py compilemessages || echo "gettext unavailable; shipping existing .mo files"
python manage.py migrate --noinput

# Platform-level configuration (plans and default settings) is idempotent.
python manage.py seed_system
