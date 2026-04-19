from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from plugin.klokkan.common import find_repo_config, repo_overrides, session_label, with_context  # noqa: E402


class RepoConfigTests(unittest.TestCase):
    def test_find_repo_config_searches_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "apps" / "web").mkdir(parents=True)
            (root / "klokkan.md").write_text(
                "---\nproject: argilzar-workouts\n---\n",
                encoding="utf-8",
            )

            found = find_repo_config(root / "apps" / "web")

            self.assertEqual(found.resolve(), (root / "klokkan.md").resolve())

    def test_repo_overrides_parse_frontmatter_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "klokkan.md").write_text(
                "---\nproject_name: mickey-scoreboard\ndescription_prefix: worklog/mickey-scoreboard\n---\n",
                encoding="utf-8",
            )

            overrides = repo_overrides(root)

            self.assertEqual(overrides["hint"], "mickey-scoreboard")
            self.assertEqual(overrides["description_prefix"], "worklog/mickey-scoreboard")

    def test_session_label_prefers_repo_config_hint_over_saved_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "klokkan.md").write_text(
                "---\nhint: argilzar-workouts\n---\n",
                encoding="utf-8",
            )

            cfg = {"hint": "old-default"}
            with patch("plugin.klokkan.common.git", return_value="feat/demo"):
                label = session_label(cfg, root)

            self.assertEqual(label, "argilzar-workouts · feat/demo")

    def test_with_context_uses_description_prefix_from_repo_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "klokkan.md").write_text(
                "---\nproject: mickey-scoreboard\ndescription_prefix: client/mickey-scoreboard\n---\n",
                encoding="utf-8",
            )

            cfg = {"hint": "old-default"}
            with patch("plugin.klokkan.common.git", side_effect=[str(root), "main"]):
                description = with_context(cfg, "Fix timer descriptions", root)

            self.assertEqual(description, "client/mickey-scoreboard — Fix timer descriptions")


if __name__ == "__main__":
    unittest.main()
