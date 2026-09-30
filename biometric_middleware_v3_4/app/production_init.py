import argparse
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from .config import BASE_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--go-live-at", required=True)
    args = parser.parse_args()

    datetime.fromisoformat(args.go_live_at)

    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        raise SystemExit("config.yaml not found")

    cfg = yaml.safe_load(
        config_path.read_text(encoding="utf-8")
    ) or {}

    db_path = Path(
        cfg.get("app", {}).get(
            "database_path",
            "data/middleware.db",
        )
    )
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    archive_dir = BASE_DIR / "data" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    candidates = (
        db_path,
        Path(str(db_path) + "-wal"),
        Path(str(db_path) + "-shm"),
        BASE_DIR / "data" / "last_daily_success.txt",
    )
    for candidate in candidates:
        if candidate.exists():
            destination = (
                archive_dir
                / f"{candidate.name}.{stamp}.bak"
            )
            shutil.move(str(candidate), str(destination))
            print(f"Archived: {candidate} -> {destination}")

    cfg.setdefault("sync", {})["go_live_at"] = args.go_live_at
    cfg["sync"]["historical_backfill_enabled"] = False

    config_path.write_text(
        yaml.safe_dump(
            cfg,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    print(
        "Production baseline ready. "
        f"Go-live cutoff: {args.go_live_at}"
    )
    print(
        "Historical data before this cutoff "
        "is excluded from Phase 1."
    )


if __name__ == "__main__":
    main()
