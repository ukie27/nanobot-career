"""Business helpers for resume persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.career.resume_parser import parse_resume_input
from nanobot.career.store import CareerStore, PROFILE_FIELDS


class ResumeService:
    """Small service layer for resume MVP operations."""

    def __init__(self, store: CareerStore):
        self.store = store

    def import_resume(
        self,
        *,
        name: str,
        content: str | None = None,
        file_path: str | None = None,
        target_role: str | None = None,
        target_scenario: str | None = None,
        summary: str | None = None,
        strengths: str | None = None,
        weaknesses: str | None = None,
        keywords: str | None = None,
        profile: dict[str, Any] | None = None,
        make_default: bool | None = None,
    ) -> dict[str, Any]:
        self.store.ensure_initialized()
        parsed = parse_resume_input(
            content=content,
            file_path=file_path,
            resume_dir=self.store.resume_dir,
            name=name,
        )
        resume_id = self.store.create_resume(
            {
                "name": name,
                "target_role": target_role,
                "target_scenario": target_scenario,
                "file_path": parsed.file_path,
                "file_type": parsed.file_type,
                "content_text": parsed.content_text,
                "summary": summary,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "keywords": keywords,
            },
            make_default=make_default,
        )
        if profile:
            self.store.upsert_profile(profile, source_resume_id=resume_id, overwrite=False)
        resume = self.store.get_resume(resume_id) or {}
        return {"resume": resume, "profile": self.store.get_profile()}

    def save_version(
        self,
        *,
        name: str,
        content_text: str,
        parent_resume_id: int | None = None,
        target_role: str | None = None,
        target_scenario: str | None = None,
        summary: str | None = None,
        strengths: str | None = None,
        weaknesses: str | None = None,
        keywords: str | None = None,
        make_default: bool | None = None,
    ) -> dict[str, Any]:
        resume_id = self.store.create_resume(
            {
                "name": name,
                "target_role": target_role,
                "target_scenario": target_scenario,
                "file_type": "generated",
                "content_text": content_text,
                "summary": summary,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "keywords": keywords,
                "parent_resume_id": parent_resume_id,
            },
            make_default=make_default,
        )
        return self.store.get_resume(resume_id) or {}

    @staticmethod
    def profile_from_tool_args(args: dict[str, Any]) -> dict[str, Any]:
        """Extract profile_* tool arguments into store field names."""
        profile: dict[str, Any] = {}
        for field in PROFILE_FIELDS:
            key = f"profile_{field}"
            if args.get(key):
                profile[field] = args[key]
        return profile
