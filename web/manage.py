#!/usr/bin/env python
"""Django manage.py for DYNAMIS Human Surface (web/)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    web_dir = Path(__file__).resolve().parent
    repo_root = web_dir.parent
    for path in (str(web_dir), str(repo_root)):
        if path not in sys.path:
            sys.path.insert(0, path)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install it in the project .venv "
            "(see requirements.txt)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
