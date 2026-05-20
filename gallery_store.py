from __future__ import annotations

from contextlib import contextmanager
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class GalleryStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS captures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    file_size INTEGER NOT NULL,
                    share_token TEXT UNIQUE,
                    shared_at TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_captures_created_at ON captures(created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_captures_share_token ON captures(share_token)"
            )

    def add_capture(
        self,
        filename: str,
        path: str | Path,
        width: int,
        height: int,
        file_size: int,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        created_at = created_at or datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO captures (filename, path, created_at, width, height, file_size)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (filename, str(Path(path).resolve()), created_at, width, height, file_size),
            )
            capture_id = int(cursor.lastrowid)
        capture = self.get_capture(capture_id)
        if capture is None:
            raise RuntimeError("Failed to read capture after insert")
        return capture

    def list_captures(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM captures ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_capture(self, capture_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_token(self, token: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM captures
                WHERE share_token = ? AND shared_at IS NOT NULL
                """,
                (token,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def set_share_enabled(self, capture_id: int, enabled: bool) -> dict[str, Any] | None:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            if existing is None:
                return None

            if enabled:
                token = secrets.token_urlsafe(24)
                shared_at = datetime.now().isoformat(timespec="seconds")
            else:
                token = None
                shared_at = None

            connection.execute(
                """
                UPDATE captures
                SET share_token = ?, shared_at = ?
                WHERE id = ?
                """,
                (token, shared_at, capture_id),
            )
        return self.get_capture(capture_id)

    def delete_capture(self, capture_id: int) -> dict[str, Any] | None:
        capture = self.get_capture(capture_id)
        if capture is None:
            return None

        with self.connect() as connection:
            connection.execute("DELETE FROM captures WHERE id = ?", (capture_id,))
        return capture

    def sync_existing_files(self, save_dir: str | Path) -> None:
        save_path = Path(save_dir).resolve()
        save_path.mkdir(parents=True, exist_ok=True)

        existing = {capture["filename"] for capture in self.list_captures()}
        for image_path in self._iter_image_files(save_path):
            if image_path.name in existing:
                continue

            try:
                with Image.open(image_path) as image:
                    width, height = image.size
                stat = image_path.stat()
            except OSError:
                continue

            created_at = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
            self.add_capture(
                image_path.name,
                image_path,
                width,
                height,
                stat.st_size,
                created_at,
            )

    def _iter_image_files(self, save_dir: Path) -> Iterable[Path]:
        for child in save_dir.iterdir():
            if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                yield child

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "filename": row["filename"],
            "path": row["path"],
            "created_at": row["created_at"],
            "width": row["width"],
            "height": row["height"],
            "file_size": row["file_size"],
            "share_token": row["share_token"],
            "shared_at": row["shared_at"],
            "share_enabled": row["shared_at"] is not None,
        }
