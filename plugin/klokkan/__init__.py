from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import excerpt as _excerpt
from .common import project_config_path as _project_config_path
from .common import with_context as _with_context

CONFIG_PATH = Path.home() / ".hermes" / "klokkan" / "config.json"
ERROR_LOG_PATH = Path.home() / ".cache" / "klokkan" / "last-error.log"
REQUEST_TIMEOUT_SECONDS = 8


def _log_error(tag: str, message: str) -> None:
    try:
        ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with ERROR_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {tag}: {message}\n")
    except Exception:
        pass


def _read_config(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        _log_error("config", f"failed to read {path}: {exc}")
        return None
    required = ("apiKey", "projectId", "projectName", "apiBaseUrl")
    missing = [k for k in required if not data.get(k)]
    if missing:
        _log_error("config", f"missing required keys in {path}: {', '.join(missing)}")
        return None
    return data


def _load_config() -> dict[str, Any] | None:
    cwd = Path.cwd()
    repo_config = _project_config_path(cwd)
    if repo_config:
        if not repo_config.exists():
            _log_error("config", f"missing repo-local config for {cwd}: {repo_config}")
            return None
        return _read_config(repo_config)
    if not CONFIG_PATH.exists():
        return None
    return _read_config(CONFIG_PATH)


def _session_suffix(session_id: Any) -> str:
    session = str(session_id or "").strip()
    return f"[session:{session}]" if session else ""


def _request_json(method: str, url: str, api_key: str, payload: dict[str, Any] | None = None) -> tuple[bool, int | None, str]:
    data = None
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return 200 <= resp.status < 300, resp.status, body
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = exc.reason if isinstance(exc.reason, str) else str(exc.reason)
        return False, exc.code, body
    except urllib.error.URLError as exc:
        return False, None, str(exc.reason)
    except Exception as exc:
        return False, None, str(exc)


def _timer_context(cfg: dict[str, Any], session_id: Any = None) -> str:
    return " ".join(part for part in (_with_context(cfg), _session_suffix(session_id)) if part)


def _prompt_first_description(cfg: dict[str, Any], leading_text: str, session_id: Any = None) -> str:
    context = _timer_context(cfg, session_id)
    leading = _excerpt(leading_text)
    if leading and context:
        return f"{leading} — {context}"
    return leading or context


def _start_or_resume_timer(cfg: dict[str, Any], user_message: str = "", session_id: Any = None) -> None:
    api = cfg["apiBaseUrl"].rstrip("/")
    ok, status, body = _request_json(
        "POST",
        f"{api}/api/v1/agent/timer/start",
        cfg["apiKey"],
        {"description": _prompt_first_description(cfg, user_message, session_id)},
    )
    if not ok:
        _log_error(
            "on-prompt-start",
            f"status={status} url={api}/api/v1/agent/timer/start body={body[:400]}",
        )


def _refine_description(cfg: dict[str, Any], user_message: str, session_id: Any = None) -> None:
    description = _prompt_first_description(cfg, user_message, session_id)
    if not description:
        return
    api = cfg["apiBaseUrl"].rstrip("/")
    ok, status, body = _request_json(
        "PATCH",
        f"{api}/api/v1/agent/timer/running",
        cfg["apiKey"],
        {"description": description, "onlyIfPlaceholder": True},
    )
    if not ok:
        _log_error(
            "on-prompt-desc",
            f"status={status} url={api}/api/v1/agent/timer/running body={body[:400]}",
        )


def _stop_timer(cfg: dict[str, Any]) -> None:
    api = cfg["apiBaseUrl"].rstrip("/")
    ok, status, body = _request_json(
        "POST",
        f"{api}/api/v1/agent/timer/stop",
        cfg["apiKey"],
        None,
    )
    if not ok:
        _log_error(
            "session-finalize-stop",
            f"status={status} url={api}/api/v1/agent/timer/stop body={body[:400]}",
        )


def _on_pre_llm_call(user_message: str = "", session_id: Any = None, **kwargs: Any) -> None:
    cfg = _load_config()
    if not cfg:
        return None
    try:
        _start_or_resume_timer(cfg, user_message=user_message, session_id=session_id)
        _refine_description(cfg, user_message, session_id=session_id)
    except Exception as exc:
        _log_error("pre_llm_call", str(exc))
    return None


def _stop_on_idle(tag: str) -> None:
    cfg = _load_config()
    if not cfg:
        return None
    try:
        _stop_timer(cfg)
    except Exception as exc:
        _log_error(tag, str(exc))
    return None


def _on_session_end(**kwargs: Any) -> None:
    return _stop_on_idle("on_session_end")


def _on_session_finalize(**kwargs: Any) -> None:
    return _stop_on_idle("on_session_finalize")


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("on_session_finalize", _on_session_finalize)
