"""
FinSpark Database Migration Script
====================================
One-shot script to import all existing file-based clients into PostgreSQL.

Run once after setting up the database:
    python -m backend.database.migrate_existing

What it does:
  1. Scans all clients/ folders
  2. For each client: inserts project, all config versions, audit log entries, credentials
  3. Skips clients that already exist in the DB (idempotent)
  4. Does NOT delete any files — the old data remains as a backup
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is on path when running as script
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import CLIENTS_DIR
from backend.database.connection import get_db, init_db


def migrate_all_clients():
    print("\n" + "=" * 60)
    print("  FinSpark DB Migration - Importing existing clients")
    print("=" * 60)

    # Ensure tables exist
    init_db()

    if not CLIENTS_DIR.exists():
        print(f"  No clients directory found at {CLIENTS_DIR}. Nothing to migrate.")
        return

    client_dirs = [d for d in sorted(CLIENTS_DIR.iterdir())
                   if d.is_dir() and d.name.startswith("client_")]

    print(f"  Found {len(client_dirs)} client folders to migrate.\n")

    success = 0
    skipped = 0
    failed  = 0

    for client_dir in client_dirs:
        client_id = client_dir.name
        try:
            result = migrate_client(client_dir)
            if result == "skipped":
                skipped += 1
                print(f"  [SKIP] {client_id} - already in DB")
            else:
                success += 1
                print(f"  [OK]   {client_id} - migrated ({result})")
        except Exception as e:
            failed += 1
            print(f"  [ERR]  {client_id} - FAILED: {e}")

    print(f"\n{'=' * 60}")
    print(f"  Migration complete: {success} migrated, {skipped} skipped, {failed} failed")
    print("=" * 60)


def migrate_client(client_dir: Path) -> str:
    """
    Migrate a single client from disk to PostgreSQL.
    Returns 'skipped' if client already exists, otherwise a summary string.
    """
    client_id = client_dir.name

    # Read the earliest config for metadata
    config_dir = client_dir / "configs"
    if not config_dir.exists():
        raise FileNotFoundError(f"No configs/ dir in {client_dir}")

    config_files = sorted(config_dir.glob("config_v*.json"))
    if not config_files:
        raise FileNotFoundError(f"No config_v*.json files in {config_dir}")

    # Read first config for project metadata
    first_config = json.loads(config_files[0].read_text(encoding="utf-8"))
    meta = first_config.get("metadata", {})
    client_info = meta.get("client", {})
    pipeline_info = meta.get("pipeline_run", {})

    client_name = client_info.get("client_name", client_id)
    created_at_str = meta.get("created_at", datetime.now(timezone.utc).isoformat())
    try:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    except Exception:
        created_at = datetime.now(timezone.utc)

    run_id = pipeline_info.get("run_id") or f"run_{client_id.split('_')[-1]}_migrated"

    with get_db() as conn:
        with conn.cursor() as cur:
            # Check if client already exists
            cur.execute("SELECT 1 FROM projects WHERE client_id = %s", (client_id,))
            if cur.fetchone():
                return "skipped"

            # 1. Insert project
            cur.execute(
                """
                INSERT INTO projects (client_id, client_name, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (client_id) DO NOTHING
                """,
                (client_id, client_name, created_at),
            )

            # 2. Insert all config versions
            configs_inserted = 0
            for config_file in config_files:
                try:
                    config_data = json.loads(config_file.read_text(encoding="utf-8"))
                    ver_str = config_file.stem  # config_v1 → "config_v1"
                    try:
                        version_num = int(ver_str.split("_v")[1])
                    except (IndexError, ValueError):
                        version_num = 1
                    version_label = f"v{version_num}"
                    status = config_data.get("metadata", {}).get("status", "draft")
                    file_created = datetime.fromtimestamp(
                        config_file.stat().st_mtime, tz=timezone.utc
                    )

                    cur.execute(
                        """
                        INSERT INTO config_versions
                            (client_id, version_number, version_label, config_data, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (client_id, version_number) DO NOTHING
                        """,
                        (client_id, version_num, version_label,
                         json.dumps(config_data), status, file_created),
                    )
                    configs_inserted += 1
                except Exception as e:
                    print(f"    [WARN] Skipping {config_file.name}: {e}")

            # 3. Insert pipeline_run from latest config metadata
            latest_config = json.loads(config_files[-1].read_text(encoding="utf-8"))
            latest_meta = latest_config.get("metadata", {})
            latest_pipeline = latest_meta.get("pipeline_run", {})
            overall_status = latest_pipeline.get("overall_status", "pending")
            correction_iters = latest_pipeline.get("correction_iterations", 0)

            cur.execute(
                """
                INSERT INTO pipeline_runs
                    (client_id, run_id, triggered_by, triggered_at, overall_status,
                     current_stage, progress_percent, progress_message, correction_iterations)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    client_id, run_id,
                    latest_pipeline.get("triggered_by", "migration"),
                    created_at,
                    overall_status,
                    latest_pipeline.get("current_stage", "idle"),
                    100 if overall_status in ("production-ready", "completed", "approved") else 90,
                    f"Migrated from file system - status: {overall_status}",
                    correction_iters,
                ),
            )

            # 4. Import reasoning report if it exists
            reasoning_path = client_dir / "reasoning_report.md"
            if reasoning_path.exists():
                reasoning_content = reasoning_path.read_text(encoding="utf-8")
                cur.execute(
                    """
                    UPDATE pipeline_runs SET reasoning_report = %s
                    WHERE client_id = %s AND run_id = %s
                    """,
                    (reasoning_content, client_id, run_id),
                )

            # 5. Import audit log
            audit_file = client_dir / "audit" / "audit_log.json"
            audit_count = 0
            if audit_file.exists():
                try:
                    audit_data = json.loads(audit_file.read_text(encoding="utf-8"))
                    for entry in audit_data.get("entries", []):
                        ts_str = entry.get("timestamp", datetime.now(timezone.utc).isoformat())
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except Exception:
                            ts = datetime.now(timezone.utc)

                        cur.execute(
                            """
                            INSERT INTO audit_events
                                (client_id, timestamp, stage, action, agent, responsible,
                                 input_hash, output_hash, details)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                client_id, ts,
                                entry.get("stage", "unknown"),
                                entry.get("action", ""),
                                entry.get("agent", "system"),
                                entry.get("responsible", "system"),
                                entry.get("input_hash"),
                                entry.get("output_hash"),
                                entry.get("details"),
                            ),
                        )
                        audit_count += 1
                except Exception as e:
                    print(f"    [WARN] Audit import error: {e}")

            # 6. Import credentials from .env file
            env_path = client_dir / ".env"
            cred_count = 0
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        var_name, _, var_value = line.partition("=")
                        var_name = var_name.strip()
                        var_value = var_value.strip()
                        if var_name:
                            cur.execute(
                                """
                                INSERT INTO credentials (client_id, var_name, var_value)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (client_id, var_name) DO NOTHING
                                """,
                                (client_id, var_name, var_value),
                            )
                            cred_count += 1

            # 7. Register existing documents in the documents table
            docs_dir = client_dir / "input_documents"
            doc_count = 0
            if docs_dir.exists():
                for doc_file in docs_dir.iterdir():
                    if doc_file.is_file():
                        cur.execute(
                            """
                            INSERT INTO documents (client_id, filename, file_path, size_bytes)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (client_id, doc_file.name, str(doc_file), doc_file.stat().st_size),
                        )
                        doc_count += 1

    return f"{configs_inserted} configs, {audit_count} audit events, {cred_count} creds, {doc_count} docs"


if __name__ == "__main__":
    migrate_all_clients()
