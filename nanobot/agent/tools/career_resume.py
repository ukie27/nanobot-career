"""Career resume tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.career.resume_service import ResumeService
from nanobot.career.store import CareerStore


class CareerResumeTool(Tool):
    """Manage resume versions and candidate profile data."""

    def __init__(self, workspace: Path, db_path: str | None = None):
        self.store = CareerStore(workspace, db_path=db_path)
        self.service = ResumeService(self.store)

    @property
    def name(self) -> str:
        return "career_resume"

    @property
    def description(self) -> str:
        return (
            "Manage the user's resume and candidate profile. "
            "Use import to save a pasted/text resume and extracted profile, "
            "save_version after the user accepts an optimized resume, and profile/list/get "
            "to retrieve stored career context."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        text_or_null = {"type": ["string", "null"]}
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "import",
                        "profile",
                        "update_profile",
                        "list",
                        "get",
                        "get_default",
                        "set_default",
                        "save_version",
                        "update_resume",
                    ],
                },
                "resume_id": {"type": ["integer", "null"]},
                "name": text_or_null,
                "content": text_or_null,
                "file_path": text_or_null,
                "target_role": text_or_null,
                "target_scenario": text_or_null,
                "summary": text_or_null,
                "strengths": text_or_null,
                "weaknesses": text_or_null,
                "keywords": text_or_null,
                "make_default": {"type": ["boolean", "null"]},
                "overwrite": {"type": ["boolean", "null"]},
                "parent_resume_id": {"type": ["integer", "null"]},
                "profile_name": text_or_null,
                "profile_phone": text_or_null,
                "profile_email": text_or_null,
                "profile_location": text_or_null,
                "profile_education": text_or_null,
                "profile_school": text_or_null,
                "profile_major": text_or_null,
                "profile_graduation_date": text_or_null,
                "profile_target_roles": text_or_null,
                "profile_target_cities": text_or_null,
                "profile_expected_salary": text_or_null,
                "profile_skills": text_or_null,
                "profile_project_experiences": text_or_null,
                "profile_internship_experiences": text_or_null,
                "profile_campus_experiences": text_or_null,
                "profile_awards": text_or_null,
                "profile_certificates": text_or_null,
                "profile_preferences": text_or_null,
                "profile_constraints": text_or_null,
                "profile_weaknesses": text_or_null,
            },
            "required": ["action"],
        }

    async def execute(self, action: str, **kwargs: Any) -> str:
        try:
            if action == "import":
                return self._json(self._import_resume(kwargs))
            if action == "profile":
                return self._json({"profile": self.store.get_profile()})
            if action == "update_profile":
                return self._json(self._update_profile(kwargs))
            if action == "list":
                return self._json({"resumes": self.store.list_resumes()})
            if action == "get":
                return self._json({"resume": self._get_resume(kwargs)})
            if action == "get_default":
                return self._json({"resume": self.store.get_default_resume()})
            if action == "set_default":
                return self._json({"resume": self._set_default(kwargs)})
            if action == "save_version":
                return self._json({"resume": self._save_version(kwargs)})
            if action == "update_resume":
                return self._json({"resume": self._update_resume(kwargs)})
            return f"Error: unknown action '{action}'"
        except Exception as exc:
            return f"Error: {exc}"

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    def _import_resume(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        name = kwargs.get("name") or "Resume"
        profile = self.service.profile_from_tool_args(kwargs)
        return self.service.import_resume(
            name=name,
            content=kwargs.get("content"),
            file_path=kwargs.get("file_path"),
            target_role=kwargs.get("target_role"),
            target_scenario=kwargs.get("target_scenario"),
            summary=kwargs.get("summary"),
            strengths=kwargs.get("strengths"),
            weaknesses=kwargs.get("weaknesses"),
            keywords=kwargs.get("keywords"),
            profile=profile,
            make_default=kwargs.get("make_default"),
        )

    def _update_profile(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        profile = self.service.profile_from_tool_args(kwargs)
        if not profile:
            raise ValueError("No profile fields provided")
        updated = self.store.upsert_profile(
            profile,
            overwrite=bool(kwargs.get("overwrite")),
            source_resume_id=kwargs.get("resume_id"),
        )
        return {"profile": updated}

    def _get_resume(self, kwargs: dict[str, Any]) -> dict[str, Any] | None:
        resume_id = kwargs.get("resume_id")
        if not resume_id:
            raise ValueError("resume_id is required")
        return self.store.get_resume(int(resume_id))

    def _set_default(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        resume_id = kwargs.get("resume_id")
        if not resume_id:
            raise ValueError("resume_id is required")
        return self.store.set_default_resume(int(resume_id))

    def _save_version(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        content = kwargs.get("content")
        if not content:
            raise ValueError("content is required for save_version")
        return self.service.save_version(
            name=kwargs.get("name") or "Optimized Resume",
            content_text=content,
            parent_resume_id=kwargs.get("parent_resume_id") or kwargs.get("resume_id"),
            target_role=kwargs.get("target_role"),
            target_scenario=kwargs.get("target_scenario"),
            summary=kwargs.get("summary"),
            strengths=kwargs.get("strengths"),
            weaknesses=kwargs.get("weaknesses"),
            keywords=kwargs.get("keywords"),
            make_default=kwargs.get("make_default"),
        )

    def _update_resume(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        resume_id = kwargs.get("resume_id")
        if not resume_id:
            raise ValueError("resume_id is required")
        data = {
            "name": kwargs.get("name"),
            "target_role": kwargs.get("target_role"),
            "target_scenario": kwargs.get("target_scenario"),
            "content_text": kwargs.get("content"),
            "summary": kwargs.get("summary"),
            "strengths": kwargs.get("strengths"),
            "weaknesses": kwargs.get("weaknesses"),
            "keywords": kwargs.get("keywords"),
            "is_default": kwargs.get("make_default"),
        }
        return self.store.update_resume(int(resume_id), data)
