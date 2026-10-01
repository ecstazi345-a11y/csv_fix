"""Minimal Django development settings for DYNAMIS Human Surface v0.1."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

WEB_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = WEB_DIR.parent

load_dotenv(REPO_ROOT / ".env")

# DEV ONLY — replace via DJANGO_SECRET_KEY in real environments.
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-DEV-ONLY-dynamis-human-surface-v01-do-not-use-in-prod",
)

DEBUG = os.getenv("DJANGO_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dynamis.apps.DynamisConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# No Django ORM models for labor_norm_decisions — Supabase remains source of truth.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": WEB_DIR / "db.sqlite3",
    }
}

# Avoid DB-backed sessions for this thin Human Surface (no ORM domain models).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [WEB_DIR / "dynamis" / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow importing services.* from repo root and web apps from web/.
import sys  # noqa: E402

for path in (str(WEB_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
