import asyncio
import concurrent.futures
import importlib.abc
import importlib.util
import logging
import os
import sys
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class SkillEngine:
    def __init__(self, skills_dir: str = ".agents/skills") -> None:
        self.skills_dir = skills_dir
        self.skills: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._load_all_skills()

    def _load_all_skills(self) -> None:
        if not os.path.exists(self.skills_dir):
            return

        for entry in os.listdir(self.skills_dir):
            skill_path = os.path.join(self.skills_dir, entry)
            if os.path.isdir(skill_path):
                self._load_skill(entry, skill_path)

    def _load_skill(self, skill_name: str, skill_path: str) -> None:
        yaml_path = os.path.join(skill_path, "agent.yaml")
        tool_path = os.path.join(skill_path, "tool.py")

        if not os.path.exists(yaml_path) or not os.path.exists(tool_path):
            return

        try:
            with open(yaml_path) as f:
                metadata = yaml.safe_load(f)

            name = metadata.get("name", skill_name)

            # Load Python module
            spec = importlib.util.spec_from_file_location(f"skills.{name}", tool_path)
            if spec is None:
                raise ValueError(f"Failed to load module spec for skill {skill_name}")
            module = importlib.util.module_from_spec(spec)

            # This can raise SyntaxError which we want to catch
            loader: importlib.abc.Loader | None = spec.loader
            if loader is None:
                raise ValueError(f"Module spec has no loader for skill {skill_name}")
            loader.exec_module(module)

            if not hasattr(module, "execute"):
                raise ValueError("Skill module missing 'execute' function")

            self.skills[name] = {
                "name": name,
                "metadata": metadata,
                "module": module,
                "status": "loaded",
            }
            logger.info(f"Successfully loaded skill: {name}")

        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            print(f"Failed to load skill {skill_name}: {e}")
            self.skills[skill_name] = {"name": skill_name, "status": "error", "error": str(e)}

    def list_skills(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        return [
            {"name": k, "status": v.get("status"), "metadata": v.get("metadata")}
            for k, v in self.skills.items()
        ]

    async def execute_skill(self, skill_name: str, params: dict[str, Any], timeout: float = 30.0) -> Any:  # TODO(TYPE): replace Any with concrete type
        skill = self.skills.get(skill_name)
        if not skill or skill["status"] != "loaded":
            raise ValueError(f"Skill {skill_name} not found or failed to load")

        loop = asyncio.get_running_loop()

        # Run in an executor to avoid blocking the async event loop and to allow timeouts
        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                # Use asyncio.wait_for to apply a timeout to the blocking call
                result = await asyncio.wait_for(
                    loop.run_in_executor(pool, skill["module"].execute, params), timeout=timeout
                )
                return result
            except TimeoutError:
                raise TimeoutError(f"Skill {skill_name} execution timed out")
