from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from plugin.klokkan import _load_config  # noqa: E402
from plugin.klokkan.connect import dry_run, write_config  # noqa: E402


class ProjectApiKeyTests(unittest.TestCase):
    def test_load_config_prefers_repo_local_credentials_inside_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git" / "info").mkdir(parents=True)
            (root / ".klokkan.json").write_text(
                json.dumps(
                    {
                        "apiKey": "repo-key",
                        "projectId": "project-123",
                        "projectName": "Repo Project",
                        "apiBaseUrl": "https://klokkan.example",
                    }
                ),
                encoding="utf-8",
            )

            with patch("plugin.klokkan.Path.cwd", return_value=root):
                cfg = _load_config()

            self.assertEqual(cfg["apiKey"], "repo-key")
            self.assertEqual(cfg["projectName"], "Repo Project")

    def test_load_config_does_not_fallback_to_global_credentials_inside_git_repo_without_repo_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git" / "info").mkdir(parents=True)
            global_config = root / "global-config.json"
            global_config.write_text(
                json.dumps(
                    {
                        "apiKey": "global-key",
                        "projectId": "global-project",
                        "projectName": "Global Project",
                        "apiBaseUrl": "https://klokkan.example",
                    }
                ),
                encoding="utf-8",
            )

            with patch("plugin.klokkan.Path.cwd", return_value=root), patch(
                "plugin.klokkan.CONFIG_PATH", global_config
            ):
                cfg = _load_config()

            self.assertIsNone(cfg)

    def test_write_config_persists_repo_local_credentials_and_marks_file_uncommitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git" / "info").mkdir(parents=True)
            exclude_path = root / ".git" / "info" / "exclude"
            exclude_path.write_text("*.swp\n", encoding="utf-8")
            creds = {
                "apiKey": "repo-key",
                "orgId": "org-1",
                "clientId": "client-1",
                "projectId": "project-123",
                "projectName": "Repo Project",
                "clientName": "Acme",
                "apiBaseUrl": "https://klokkan.example",
            }

            config_path = write_config(creds, "repo-project", cwd=root)

            self.assertEqual(Path(config_path).resolve(), (root / ".klokkan.json").resolve())
            saved = json.loads((root / ".klokkan.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["apiKey"], "repo-key")
            self.assertEqual(saved["projectName"], "Repo Project")
            self.assertEqual((root / ".klokkan.json").stat().st_mode & 0o777, 0o600)
            exclude_text = exclude_path.read_text(encoding="utf-8")
            self.assertIn(".klokkan.json", exclude_text)

    def test_dry_run_reports_repo_local_target_when_inside_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git" / "info").mkdir(parents=True)

            with patch("plugin.klokkan.connect.Path.cwd", return_value=root):
                result = dry_run("https://klokkan.usable.dev", "repo-project")

            self.assertEqual(
                Path(result["credentials"]["stored_at"]).resolve(),
                (root / ".klokkan.json").resolve(),
            )
            self.assertEqual(result["credentials"]["scope"], "repo")

    def test_write_config_supports_git_file_layouts_like_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_dir = root / ".worktree-git"
            exclude_path = git_dir / "info" / "exclude"
            exclude_path.parent.mkdir(parents=True)
            exclude_path.write_text("", encoding="utf-8")
            (root / ".git").write_text("gitdir: ./.worktree-git\n", encoding="utf-8")
            creds = {
                "apiKey": "repo-key",
                "orgId": "org-1",
                "clientId": "client-1",
                "projectId": "project-123",
                "projectName": "Repo Project",
                "clientName": "Acme",
                "apiBaseUrl": "https://klokkan.example",
            }

            with patch(
                "plugin.klokkan.common.git",
                side_effect=lambda args, cwd: str(exclude_path)
                if args == ["rev-parse", "--git-path", "info/exclude"]
                else "",
            ):
                config_path = write_config(creds, "repo-project", cwd=root)

            self.assertEqual(Path(config_path).resolve(), (root / ".klokkan.json").resolve())
            self.assertIn(".klokkan.json", exclude_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
