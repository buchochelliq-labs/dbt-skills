import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _frontmatter(path: Path) -> tuple[dict[str, object], str]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", content, re.DOTALL)
    if match is None:
        raise AssertionError(f"Missing YAML frontmatter: {path}")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        raise AssertionError(f"Frontmatter must be a mapping: {path}")
    return metadata, match.group(2)


class AgentAssetTests(unittest.TestCase):
    def test_portable_skill_has_required_metadata_and_safe_tool_defaults(self):
        path = ROOT / ".github" / "skills" / "dbt-context-routing" / "SKILL.md"
        metadata, body = _frontmatter(path)

        self.assertEqual(metadata.get("name"), "dbt-context-routing")
        self.assertRegex(metadata.get("description", ""), r"\S")
        self.assertLessEqual(len(metadata["description"]), 1024)
        self.assertNotIn("allowed-tools", metadata)
        self.assertIn("dbt-labs/dbt-agent-skills", body)
        self.assertIn("Use Genie One only when its MCP tool is exposed", body)
        self.assertIn("If the host exposes the `dbt-skills-uol` MCP tools", body)
        self.assertIn("do not infer column dependencies", body)

    def test_copilot_profile_is_thin_and_does_not_assume_tool_access(self):
        path = ROOT / ".github" / "agents" / "dbt-analytics-engineer.agent.md"
        metadata, body = _frontmatter(path)

        self.assertEqual(metadata.get("name"), "dbt-analytics-engineer")
        self.assertRegex(metadata.get("description", ""), r"\S")
        self.assertNotIn("tools", metadata)
        self.assertIn("dbt-context-routing", body)
        self.assertIn("not connected to Copilot CLI", body)
        self.assertIn("Do not invent server capabilities", body)

    def test_copilot_guide_documents_paths_and_current_boundaries(self):
        guide = (ROOT / "docs" / "COPILOT_CLI.md").read_text(encoding="utf-8")

        self.assertIn(".github/skills/", guide)
        self.assertIn(".github/agents/", guide)
        self.assertIn("local stdio MCP bridge for the UOL", guide)
        self.assertIn("encrypted local cache", guide)
        self.assertIn("compromised account or authorized process", guide)
        self.assertIn("Do not commit credentials", guide)


if __name__ == "__main__":
    unittest.main()
