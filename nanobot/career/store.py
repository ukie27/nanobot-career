"""SQLite store for career assistant data."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


PROFILE_FIELDS = (
    "name",
    "phone",
    "email",
    "location",
    "education",
    "school",
    "major",
    "graduation_date",
    "target_roles",
    "target_cities",
    "expected_salary",
    "skills",
    "project_experiences",
    "internship_experiences",
    "campus_experiences",
    "awards",
    "certificates",
    "preferences",
    "constraints",
    "weaknesses",
)

RESUME_FIELDS = (
    "name",
    "target_role",
    "target_scenario",
    "file_path",
    "file_type",
    "content_text",
    "summary",
    "strengths",
    "weaknesses",
    "keywords",
    "is_default",
    "parent_resume_id",
)


class CareerStore:
    """Lazy-initialized SQLite storage for career assistant features."""

    def __init__(self, workspace: Path, db_path: str | Path | None = None):
        self.workspace = workspace
        self.root = workspace / "career"
        self.files_dir = self.root / "files"
        self.resume_dir = self.files_dir / "resumes"
        self.db_path = Path(db_path).expanduser() if db_path else self.root / "career.db"
        if not self.db_path.is_absolute():
            self.db_path = workspace / self.db_path
        self._initialized = False

    def ensure_initialized(self) -> None:
        """Create career directory and schema on first use."""
        if self._initialized and self.db_path.exists():
            return
        self.resume_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._create_schema(conn)
        self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candidate_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT,
                phone TEXT,
                email TEXT,
                location TEXT,
                education TEXT,
                school TEXT,
                major TEXT,
                graduation_date TEXT,
                target_roles TEXT,
                target_cities TEXT,
                expected_salary TEXT,
                skills TEXT,
                project_experiences TEXT,
                internship_experiences TEXT,
                campus_experiences TEXT,
                awards TEXT,
                certificates TEXT,
                preferences TEXT,
                constraints TEXT,
                weaknesses TEXT,
                source_resume_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_role TEXT,
                target_scenario TEXT,
                file_path TEXT,
                file_type TEXT,
                content_text TEXT NOT NULL,
                summary TEXT,
                strengths TEXT,
                weaknesses TEXT,
                keywords TEXT,
                is_default INTEGER DEFAULT 0,
                parent_resume_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (parent_resume_id) REFERENCES resumes(id)
            );
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (1, 'initial_career_resume_schema', ?)
            """,
            (self._now(),),
        )
        conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def get_profile(self) -> dict[str, Any] | None:
        self.ensure_initialized()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM candidate_profile WHERE id = 1").fetchone()
        return self._row_to_dict(row)

    def upsert_profile(
        self,
        data: dict[str, Any],
        *,
        source_resume_id: int | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Insert or update the singleton candidate profile.

        Empty fields are ignored. By default existing non-empty fields are kept.
        """
        self.ensure_initialized()
        now = self._now()
        cleaned = {k: self._clean_text(data.get(k)) for k in PROFILE_FIELDS if k in data}
        cleaned = {k: v for k, v in cleaned.items() if v is not None}

        existing = self.get_profile()
        if not existing:
            values = {field: cleaned.get(field) for field in PROFILE_FIELDS}
            values["source_resume_id"] = source_resume_id
            values["created_at"] = now
            values["updated_at"] = now
            columns = ["id", *values.keys()]
            placeholders = ", ".join("?" for _ in columns)
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO candidate_profile({', '.join(columns)}) VALUES ({placeholders})",
                    [1, *values.values()],
                )
                conn.commit()
            return self.get_profile() or {}

        updates: dict[str, Any] = {}
        for field, value in cleaned.items():
            if overwrite or not self._clean_text(existing.get(field)):
                updates[field] = value
        if source_resume_id is not None:
            updates["source_resume_id"] = source_resume_id
        updates["updated_at"] = now

        assignments = ", ".join(f"{field} = ?" for field in updates)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE candidate_profile SET {assignments} WHERE id = 1",
                list(updates.values()),
            )
            conn.commit()
        return self.get_profile() or {}

    def create_resume(self, data: dict[str, Any], *, make_default: bool | None = None) -> int:
        self.ensure_initialized()
        content = self._clean_text(data.get("content_text"))
        if not content:
            raise ValueError("content_text is required")
        name = self._clean_text(data.get("name")) or "Resume"
        now = self._now()

        has_default = self.get_default_resume() is not None
        is_default = bool(make_default) or not has_default or bool(data.get("is_default"))
        if is_default:
            self._clear_default()

        values = {
            "name": name,
            "target_role": self._clean_text(data.get("target_role")),
            "target_scenario": self._clean_text(data.get("target_scenario")),
            "file_path": self._clean_text(data.get("file_path")),
            "file_type": self._clean_text(data.get("file_type")) or "pasted",
            "content_text": content,
            "summary": self._clean_text(data.get("summary")),
            "strengths": self._clean_text(data.get("strengths")),
            "weaknesses": self._clean_text(data.get("weaknesses")),
            "keywords": self._clean_text(data.get("keywords")),
            "is_default": 1 if is_default else 0,
            "parent_resume_id": data.get("parent_resume_id"),
            "created_at": now,
            "updated_at": now,
        }
        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        with self._connect() as conn:
            cur = conn.execute(
                f"INSERT INTO resumes({', '.join(columns)}) VALUES ({placeholders})",
                list(values.values()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_resume(self, resume_id: int, data: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        existing = self.get_resume(resume_id)
        if not existing:
            raise ValueError(f"Resume {resume_id} not found")

        updates = {
            field: self._clean_text(data.get(field))
            for field in RESUME_FIELDS
            if field in data and field not in {"is_default", "parent_resume_id"}
        }
        updates = {k: v for k, v in updates.items() if v is not None}
        if "parent_resume_id" in data:
            updates["parent_resume_id"] = data["parent_resume_id"]
        if "is_default" in data and data["is_default"] is not None:
            updates["is_default"] = 1 if data["is_default"] else 0
            if updates["is_default"]:
                self._clear_default()
        updates["updated_at"] = self._now()
        assignments = ", ".join(f"{field} = ?" for field in updates)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE resumes SET {assignments} WHERE id = ?",
                [*updates.values(), resume_id],
            )
            conn.commit()
        return self.get_resume(resume_id) or {}

    def get_resume(self, resume_id: int) -> dict[str, Any] | None:
        self.ensure_initialized()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        return self._row_to_dict(row)

    def get_default_resume(self) -> dict[str, Any] | None:
        self.ensure_initialized()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM resumes WHERE is_default = 1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return self._row_to_dict(row)

    def list_resumes(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, target_role, target_scenario, file_path, file_type,
                       summary, strengths, weaknesses, keywords, is_default,
                       parent_resume_id, created_at, updated_at
                FROM resumes
                ORDER BY is_default DESC, updated_at DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def set_default_resume(self, resume_id: int) -> dict[str, Any]:
        self.ensure_initialized()
        if not self.get_resume(resume_id):
            raise ValueError(f"Resume {resume_id} not found")
        self._clear_default()
        with self._connect() as conn:
            conn.execute(
                "UPDATE resumes SET is_default = 1, updated_at = ? WHERE id = ?",
                (self._now(), resume_id),
            )
            conn.commit()
        return self.get_resume(resume_id) or {}

    def _clear_default(self) -> None:
        self.ensure_initialized()
        with self._connect() as conn:
            conn.execute("UPDATE resumes SET is_default = 0")
            conn.commit()
