import os
import shutil

import pytest

from src.core.engine.skill_engine import SkillEngine


@pytest.fixture
def temp_skills_dir(tmp_path):
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)

    # Create valid calculator skill
    calc_dir = skills_dir / "calculator"
    calc_dir.mkdir()

    with open(calc_dir / "agent.yaml", "w") as f:
        f.write("name: CalculatorSkill\n")
    with open(calc_dir / "tool.py", "w") as f:
        f.write("def execute(params):\n")
        f.write("    if params.get('expression') == '2+2':\n")
        f.write("        return 4\n")
        f.write("    return 0\n")

    # Create invalid syntax skill
    bad_dir = skills_dir / "bad_syntax"
    bad_dir.mkdir()
    with open(bad_dir / "agent.yaml", "w") as f:
        f.write("name: BadSkill\n")
    with open(bad_dir / "tool.py", "w") as f:
        f.write("def execute(params):\n")
        f.write("    this is invalid python syntax\n")

    # Create infinite loop skill
    loop_dir = skills_dir / "infinite_loop"
    loop_dir.mkdir()
    with open(loop_dir / "agent.yaml", "w") as f:
        f.write("name: LoopSkill\n")
    with open(loop_dir / "tool.py", "w") as f:
        f.write("import time\n")
        f.write("def execute(params):\n")
        f.write("    time.sleep(2)\n")

    yield str(skills_dir)


@pytest.mark.asyncio
async def test_skill_engine_load_valid_skill(temp_skills_dir):
    engine = SkillEngine(skills_dir=temp_skills_dir)
    skills = engine.list_skills()

    assert any(s["name"] == "CalculatorSkill" for s in skills)

    # Test execution
    result = await engine.execute_skill("CalculatorSkill", {"expression": "2+2"})
    assert result == 4


@pytest.mark.asyncio
async def test_skill_engine_syntax_error(temp_skills_dir):
    engine = SkillEngine(skills_dir=temp_skills_dir)
    skills = engine.list_skills()

    # The bad skill should be gracefully ignored or marked as failed, but not crash the app
    bad_skill = next((s for s in skills if s["name"] == "BadSkill"), None)

    assert bad_skill is None or bad_skill.get("status") == "error"

    # Try executing it
    with pytest.raises(ValueError, match="not found or failed to load"):
        await engine.execute_skill("BadSkill", {})


@pytest.mark.asyncio
async def test_skill_engine_timeout(temp_skills_dir):
    engine = SkillEngine(skills_dir=temp_skills_dir)

    with pytest.raises(TimeoutError):
        # We pass a short timeout of 0.5s for the test
        await engine.execute_skill("LoopSkill", {}, timeout=0.5)
