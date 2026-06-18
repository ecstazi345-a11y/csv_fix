"""Supabase client for shift form only (server-side key, not exposed in UI)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")


def get_form_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    secret = os.getenv("SUPABASE_SECRET_KEY")
    anon = os.getenv("SUPABASE_KEY")
    key = secret or anon

    if not url or not key:
        raise ValueError(
            "В .env нужны SUPABASE_URL и SUPABASE_SECRET_KEY (или SUPABASE_KEY)."
        )

    return create_client(url, key)
