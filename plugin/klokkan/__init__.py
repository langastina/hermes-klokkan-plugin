from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".hermes" / "klokkan" / "config.json"
ERROR_LOG_PATH = Path.home() / ".cache" / "klokkan" / "last-error.log"
REQUEST_TIMEOUT_SECONDS = 8
PROMPT_EXCERPT_CHARS = 120


def _log_error(tag: str, message: str) -> None:
    try:
        ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with ERROR_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {tag}: {message}\n")
    except Exception:
        pass


def _load_config() -> dict[str, Any] | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        _log_error("config", f"failed to read {CONFIG_PATH}: {exc}")
        return None
    required = ("apiKey", "projectId", "projectName", "apiBaseUrl")
    missing = [k for k in required if not data.get(k)]
    if missing:
        _log_error("config", f"missing required keys: {', '.join(missing)}")
        return None
    return data


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _resolve_repo_root(cwd: Path) -> Path:
    root = _git(["rev-parse", "--show-toplevel"], cwd)
    return Path(root) if root else cwd


def _derive_default_hint(cwd: Path) -> str:
    repo_root = _resolve_repo_root(cwd)
    try:
        relative = cwd.resolve().relative_to(repo_root.resolve())
    except Exception:
        return cwd.name or str(cwd)
    repo_name = repo_root.name or cwd.name or str(cwd)
    relative_str = relative.as_posix()
    if relative_str in ("", "."):
        return repo_name
    return f"{repo_name}/{relative_str}"


def _session_label(cfg: dict[str, Any], cwd: Path | None = None) -> str:
    cwd = cwd or Path.cwd()
    base = (cfg.get("hint") or "").strip() or _derive_default_hint(cwd)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch and branch != "HEAD":
        if base == branch or base.endswith(f"/{branch}") or base.endswith(f" · {branch}"):
            return base
        return f"{base} · {branch}"
    return base


def _with_context(cfg: dict[str, Any], suffix: str = "") -> str:
    label = _session_label(cfg)
    suffix = suffix.strip()
    return f"{label} — {suffix}" if suffix else label


def _excerpt(text: str) -> str:
    return " ".join((text or "").split())[:PROMPT_EXCERPT_CHARS].strip()


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


def _start_or_resume_timer(cfg: dict[str, Any]) -> None:
    api = cfg["apiBaseUrl"].rstrip("/")
    ok, status, body = _request_json(
        "POST",
        f"{api}/api/v1/agent/timer/start",
        cfg["apiKey"],
        {"description": _with_context(cfg)},
    )
    if not ok:
        _log_error(
            "on-prompt-start",
            f"status={status} url={api}/api/v1/agent/timer/start body={body[:400]}",
        )


def _refine_description(cfg: dict[str, Any], user_message: str) -> None:
    excerpt = _excerpt(user_message)
    if not excerpt:
        return
    api = cfg["apiBaseUrl"].rstrip("/")
    ok, status, body = _request_json(
        "PATCH",
        f"{api}/api/v1/agent/timer/running",
        cfg["apiKey"],
        {"description": _with_context(cfg, excerpt), "onlyIfPlaceholder": True},
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


def _on_pre_llm_call(user_message: str = "", **kwargs: Any) -> None:
    cfg = _load_config()
    if not cfg:
        return None
    try:
        _start_or_resume_timer(cfg)
        _refine_description(cfg, user_message)
    except Exception as exc:
        _log_error("pre_llm_call", str(exc))
    return None


def _on_session_finalize(**kwargs: Any) -> None:
    cfg = _load_config()
    if not cfg:
        return None
    try:
        _stop_timer(cfg)
    except Exception as exc:
        _log_error("on_session_finalize", str(exc))
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_session_finalize", _on_session_finalize)
