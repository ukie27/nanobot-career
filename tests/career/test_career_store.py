from pathlib import Path

from nanobot.career.resume_service import ResumeService
from nanobot.career.store import CareerStore


def test_store_lazy_initializes_on_first_use(tmp_path: Path) -> None:
    store = CareerStore(tmp_path)

    assert not (tmp_path / "career" / "career.db").exists()

    assert store.get_profile() is None

    assert (tmp_path / "career" / "career.db").exists()
    assert (tmp_path / "career" / "files" / "resumes").exists()


def test_import_resume_creates_default_and_profile(tmp_path: Path) -> None:
    store = CareerStore(tmp_path)
    service = ResumeService(store)

    result = service.import_resume(
        name="通用版",
        content="张三\nPython / FastAPI\n项目：求职助手",
        profile={
            "name": "张三",
            "skills": "Python, FastAPI",
            "project_experiences": "求职助手：负责后端开发",
        },
    )

    resume = result["resume"]
    profile = result["profile"]

    assert resume["id"] == 1
    assert resume["is_default"] == 1
    assert resume["content_text"].startswith("张三")
    assert profile["name"] == "张三"
    assert profile["skills"] == "Python, FastAPI"


def test_save_version_keeps_parent_and_can_be_default(tmp_path: Path) -> None:
    store = CareerStore(tmp_path)
    service = ResumeService(store)

    original = service.import_resume(name="通用版", content="old resume")["resume"]
    optimized = service.save_version(
        name="后端实习版",
        content_text="new resume",
        parent_resume_id=original["id"],
        target_role="后端实习",
        make_default=True,
    )

    assert optimized["parent_resume_id"] == original["id"]
    assert optimized["is_default"] == 1
    assert store.get_resume(original["id"])["is_default"] == 0
    assert store.get_default_resume()["id"] == optimized["id"]


def test_profile_update_does_not_overwrite_existing_by_default(tmp_path: Path) -> None:
    store = CareerStore(tmp_path)

    store.upsert_profile({"name": "张三", "skills": "Python"})
    store.upsert_profile({"name": "李四", "school": "A University"}, overwrite=False)
    profile = store.get_profile()

    assert profile["name"] == "张三"
    assert profile["school"] == "A University"
