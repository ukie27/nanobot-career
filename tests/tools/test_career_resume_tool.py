import json
from pathlib import Path

from nanobot.agent.tools.career_resume import CareerResumeTool


async def test_career_resume_import_and_get_default(tmp_path: Path) -> None:
    tool = CareerResumeTool(tmp_path)

    result = await tool.execute(
        action="import",
        name="通用版",
        content="张三\n后端开发\n项目：求职助手",
        profile_name="张三",
        profile_skills="Python, SQLite",
    )
    data = json.loads(result)

    assert data["resume"]["name"] == "通用版"
    assert data["profile"]["name"] == "张三"

    default_result = await tool.execute(action="get_default")
    default_data = json.loads(default_result)
    assert default_data["resume"]["id"] == data["resume"]["id"]


async def test_career_resume_save_version(tmp_path: Path) -> None:
    tool = CareerResumeTool(tmp_path)

    imported = json.loads(await tool.execute(action="import", name="通用版", content="old"))
    saved = json.loads(
        await tool.execute(
            action="save_version",
            name="后端实习版",
            content="new",
            parent_resume_id=imported["resume"]["id"],
            make_default=True,
        )
    )

    assert saved["resume"]["name"] == "后端实习版"
    assert saved["resume"]["parent_resume_id"] == imported["resume"]["id"]
    assert saved["resume"]["is_default"] == 1
