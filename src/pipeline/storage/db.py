"""SQLite helpers for the approved recalls table and the review queue."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.pipeline import settings
from src.pipeline.models import DraftAlert, ReviewStatus


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    approved = settings.approved_table()
    review = settings.review_table()
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {approved} (
            record_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_org TEXT NOT NULL,
            source_url TEXT NOT NULL,
            product_name TEXT,
            source_country TEXT,
            manufacturer TEXT,
            distributor TEXT,
            publish_date TEXT,
            scraped_at TEXT NOT NULL,
            reason TEXT,
            more_info TEXT
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {review} (
            record_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_org TEXT NOT NULL,
            source_url TEXT NOT NULL,
            product_name TEXT,
            source_country TEXT,
            manufacturer TEXT,
            distributor TEXT,
            publish_date TEXT,
            scraped_at TEXT NOT NULL,
            reason TEXT,
            more_info TEXT,
            status TEXT NOT NULL,
            validation_errors TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            raw_path TEXT
        )
        """
    )
    connection.commit()


def upsert_approved(connection: sqlite3.Connection, alert: DraftAlert) -> None:
    table = settings.approved_table()
    row = alert.as_drug_alert().model_dump()
    columns = list(row.keys())
    placeholders = ", ".join("?" * len(columns))
    updates = ", ".join(
        f"{column}=excluded.{column}"
        if column in {"source_id", "source_org", "source_url", "scraped_at"}
        else f"{column}=COALESCE(excluded.{column}, {table}.{column})"
        for column in columns
        if column != "record_id"
    )
    connection.execute(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(record_id) DO UPDATE SET {updates}
        """,
        tuple(row[column] for column in columns),
    )


def upsert_review(connection: sqlite3.Connection, alert: DraftAlert) -> None:
    table = settings.review_table()
    row = alert.model_dump()
    row["validation_errors"] = "|".join(alert.validation_errors)
    row["status"] = alert.status.value
    columns = list(row.keys())
    placeholders = ", ".join("?" * len(columns))
    connection.execute(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(record_id) DO UPDATE SET
          {", ".join(f"{column}=excluded.{column}" for column in columns if column != "record_id")}
        """,
        tuple(row[column] for column in columns),
    )


def list_pending(connection: sqlite3.Connection) -> list[DraftAlert]:
    table = settings.review_table()
    cursor = connection.execute(
        f"SELECT * FROM {table} WHERE status = ?",
        (ReviewStatus.pending.value,),
    )
    drafts: list[DraftAlert] = []
    for row in cursor.fetchall():
        data = dict(row)
        data["validation_errors"] = [
            part for part in (data.get("validation_errors") or "").split("|") if part
        ]
        drafts.append(DraftAlert(**data))
    return drafts


def get_review(connection: sqlite3.Connection, record_id: str) -> DraftAlert | None:
    table = settings.review_table()
    row = connection.execute(
        f"SELECT * FROM {table} WHERE record_id = ?",
        (record_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["validation_errors"] = [
        part for part in (data.get("validation_errors") or "").split("|") if part
    ]
    return DraftAlert(**data)


def set_review_status(
    connection: sqlite3.Connection, record_id: str, status: ReviewStatus
) -> None:
    table = settings.review_table()
    connection.execute(
        f"UPDATE {table} SET status = ? WHERE record_id = ?",
        (status.value, record_id),
    )


def approved_exists(connection: sqlite3.Connection, record_id: str) -> bool:
    table = settings.approved_table()
    row = connection.execute(
        f"SELECT 1 FROM {table} WHERE record_id = ? LIMIT 1",
        (record_id,),
    ).fetchone()
    return row is not None


def delete_review(connection: sqlite3.Connection, record_id: str) -> bool:
    table = settings.review_table()
    cursor = connection.execute(
        f"DELETE FROM {table} WHERE record_id = ?",
        (record_id,),
    )
    return cursor.rowcount > 0
