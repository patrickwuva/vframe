from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from frameapp.db import get_db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_media(original_path: str, media_type: str) -> str:
    media_id = str(uuid4())
    db = get_db()
    db.execute(
        """
        INSERT INTO media (
            id, original_path, normalized_path, type, created_at,
            duration_seconds, width, height, thumb_path, status, error
        ) VALUES (?, ?, NULL, ?, ?, NULL, NULL, NULL, NULL, 'processing', NULL)
        """,
        (media_id, original_path, media_type, now_iso()),
    )
    db.commit()
    return media_id


def get_media(media_id: str):
    db = get_db()
    return db.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()


def get_media_by_original_path(original_path: str):
    db = get_db()
    return db.execute("SELECT * FROM media WHERE original_path = ?", (original_path,)).fetchone()


def list_media():
    db = get_db()
    return db.execute("SELECT * FROM media ORDER BY created_at DESC").fetchall()


def list_ready_media():
    db = get_db()
    return db.execute(
        "SELECT * FROM media WHERE status = 'ready' ORDER BY created_at DESC"
    ).fetchall()


def set_media_processing(media_id: str) -> None:
    db = get_db()
    db.execute(
        "UPDATE media SET status = 'processing', error = NULL WHERE id = ?",
        (media_id,),
    )
    db.commit()


def mark_media_failed(media_id: str, error: str) -> None:
    db = get_db()
    db.execute(
        "UPDATE media SET status = 'failed', error = ? WHERE id = ?",
        (error[:400], media_id),
    )
    db.commit()


def mark_media_ready(
    media_id: str,
    normalized_path: str,
    thumb_path: str | None,
    duration_seconds: float | None,
    width: int | None,
    height: int | None,
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE media
        SET status = 'ready', error = NULL,
            normalized_path = ?, thumb_path = ?, duration_seconds = ?,
            width = ?, height = ?
        WHERE id = ?
        """,
        (
            normalized_path,
            thumb_path,
            duration_seconds,
            width,
            height,
            media_id,
        ),
    )
    db.commit()


def create_album(name: str) -> str:
    album_id = str(uuid4())
    db = get_db()
    db.execute(
        "INSERT INTO albums (id, name, created_at) VALUES (?, ?, ?)",
        (album_id, name.strip(), now_iso()),
    )
    db.commit()
    return album_id


def list_albums():
    db = get_db()
    return db.execute(
        """
        SELECT a.*,
               (SELECT COUNT(*) FROM album_items ai WHERE ai.album_id = a.id) AS item_count
        FROM albums a
        ORDER BY a.created_at DESC
        """
    ).fetchall()


def get_album(album_id: str):
    db = get_db()
    return db.execute("SELECT * FROM albums WHERE id = ?", (album_id,)).fetchone()


def get_album_items(album_id: str, only_ready: bool = False):
    db = get_db()
    sql = """
        SELECT ai.album_id, ai.media_id, ai.sort_index,
               m.normalized_path, m.thumb_path, m.type, m.status,
               m.duration_seconds, m.width, m.height, m.original_path
        FROM album_items ai
        JOIN media m ON m.id = ai.media_id
        WHERE ai.album_id = ?
    """
    params = [album_id]
    if only_ready:
        sql += " AND m.status = 'ready' AND m.normalized_path IS NOT NULL"
    sql += " ORDER BY ai.sort_index ASC"
    return db.execute(sql, params).fetchall()


def add_media_to_album(album_id: str, media_id: str) -> None:
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(MAX(sort_index), -1) + 1 AS next_idx FROM album_items WHERE album_id = ?",
        (album_id,),
    ).fetchone()
    next_idx = row["next_idx"]
    db.execute(
        """
        INSERT OR IGNORE INTO album_items (album_id, media_id, sort_index)
        VALUES (?, ?, ?)
        """,
        (album_id, media_id, next_idx),
    )
    db.commit()


def remove_media_from_album(album_id: str, media_id: str) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM album_items WHERE album_id = ? AND media_id = ?",
        (album_id, media_id),
    )
    db.commit()
    normalize_album_order(album_id)


def move_media_in_album(album_id: str, media_id: str, direction: str) -> None:
    db = get_db()
    items = db.execute(
        "SELECT media_id FROM album_items WHERE album_id = ? ORDER BY sort_index ASC",
        (album_id,),
    ).fetchall()
    ids = [row["media_id"] for row in items]
    if media_id not in ids:
        return
    i = ids.index(media_id)
    if direction == "up" and i > 0:
        ids[i - 1], ids[i] = ids[i], ids[i - 1]
    elif direction == "down" and i < len(ids) - 1:
        ids[i + 1], ids[i] = ids[i], ids[i + 1]
    else:
        return

    for idx, mid in enumerate(ids):
        db.execute(
            "UPDATE album_items SET sort_index = ? WHERE album_id = ? AND media_id = ?",
            (idx, album_id, mid),
        )
    db.commit()


def normalize_album_order(album_id: str) -> None:
    db = get_db()
    rows = db.execute(
        "SELECT media_id FROM album_items WHERE album_id = ? ORDER BY sort_index ASC",
        (album_id,),
    ).fetchall()
    for idx, row in enumerate(rows):
        db.execute(
            "UPDATE album_items SET sort_index = ? WHERE album_id = ? AND media_id = ?",
            (idx, album_id, row["media_id"]),
        )
    db.commit()


def reorder_album_items(album_id: str, ordered_media_ids: list[str]) -> None:
    if not ordered_media_ids:
        return

    db = get_db()
    rows = db.execute(
        "SELECT media_id FROM album_items WHERE album_id = ? ORDER BY sort_index ASC",
        (album_id,),
    ).fetchall()
    existing_ids = [row["media_id"] for row in rows]
    if not existing_ids:
        return

    existing_set = set(existing_ids)
    requested = [mid for mid in ordered_media_ids if mid in existing_set]
    seen: set[str] = set()
    deduped = []
    for mid in requested:
        if mid in seen:
            continue
        seen.add(mid)
        deduped.append(mid)

    for mid in existing_ids:
        if mid not in seen:
            deduped.append(mid)

    for idx, mid in enumerate(deduped):
        db.execute(
            "UPDATE album_items SET sort_index = ? WHERE album_id = ? AND media_id = ?",
            (idx, album_id, mid),
        )
    db.commit()


def get_settings() -> dict[str, str]:
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default: str | None = None) -> str | None:
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    db.commit()


def get_active_album_id() -> str | None:
    db = get_db()
    row = db.execute("SELECT active_album_id FROM player_state WHERE id = 1").fetchone()
    return None if row is None else row["active_album_id"]


def set_active_album(album_id: str | None) -> None:
    db = get_db()
    db.execute(
        "UPDATE player_state SET active_album_id = ?, updated_at = ? WHERE id = 1",
        (album_id, now_iso()),
    )
    db.commit()


def get_counts() -> dict[str, int]:
    db = get_db()
    media_count = db.execute("SELECT COUNT(*) AS c FROM media").fetchone()["c"]
    ready_count = db.execute(
        "SELECT COUNT(*) AS c FROM media WHERE status = 'ready'"
    ).fetchone()["c"]
    album_count = db.execute("SELECT COUNT(*) AS c FROM albums").fetchone()["c"]
    return {
        "media": media_count,
        "ready": ready_count,
        "albums": album_count,
    }
