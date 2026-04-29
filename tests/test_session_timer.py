from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from plugin.klokkan import _on_pre_llm_call, _prompt_first_description  # noqa: E402


class SessionTimerTests(unittest.TestCase):
    def test_pre_llm_call_tags_timer_description_with_session_id(self) -> None:
        cfg = {
            "apiKey": "test-key",
            "apiBaseUrl": "https://klokkan.example",
            "hint": "langastina",
            "projectId": "project-123",
            "projectName": "Langastina",
        }

        captured_calls: list[tuple[str, str, str, dict[str, str] | None]] = []

        def fake_request_json(method: str, url: str, api_key: str, payload: dict[str, str] | None = None):
            captured_calls.append((method, url, api_key, payload))
            return True, 200, "{}"

        with patch("plugin.klokkan._load_config", return_value=cfg), patch(
            "plugin.klokkan._request_json", side_effect=fake_request_json
        ), patch("plugin.klokkan._with_context", side_effect=lambda cfg, suffix="": f"langastina {suffix}".strip()):
            _on_pre_llm_call(user_message="Debug timer bug", session_id="session-abc")

        start_payload = captured_calls[0][3]
        self.assertEqual(
            start_payload,
            {"description": "Debug timer bug — langastina [session:session-abc]"},
        )

        running_payload = captured_calls[1][3]
        self.assertEqual(
            running_payload,
            {
                "description": "Debug timer bug — langastina [session:session-abc]",
                "onlyIfPlaceholder": True,
            },
        )

    def test_prompt_first_description_falls_back_to_context_without_prompt(self) -> None:
        cfg = {
            "apiKey": "***",
            "apiBaseUrl": "https://klokkan.example",
            "hint": "langastina",
            "projectId": "project-123",
            "projectName": "Langastina",
        }

        with patch("plugin.klokkan._with_context", side_effect=lambda cfg, suffix="": f"langastina {suffix}".strip()):
            description = _prompt_first_description(cfg, "", session_id="session-abc")

        self.assertEqual(description, "langastina [session:session-abc]")


if __name__ == "__main__":
    unittest.main()
