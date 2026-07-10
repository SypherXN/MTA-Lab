#!/usr/bin/env python3
"""Import agent plans from repo plans/*.json into the local API database."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.config import settings  # noqa: E402
from app.database import get_connection, init_db  # noqa: E402
from app.plan_service import sync_agent_plans_from_directory  # noqa: E402


def main() -> int:
    plans_dir = settings.resolved_plans_dir()
    init_db()
    conn = get_connection()
    try:
        result = sync_agent_plans_from_directory(conn, plans_dir)
        conn.commit()
    finally:
        conn.close()

    print(f"Plans directory: {plans_dir}")
    print(f"imported={result.imported} updated={result.updated} unchanged={result.unchanged}")
    for item in result.items:
        print(f"  [{item.status}] {item.version} {item.name}: {item.message}")
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
