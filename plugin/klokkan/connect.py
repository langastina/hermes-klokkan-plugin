#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlencode

try:
    from .common import derive_default_hint, ensure_project_config_ignored, project_config_path, repo_overrides
except ImportError:  # pragma: no cover - supports direct script execution
    from common import derive_default_hint, ensure_project_config_ignored, project_config_path, repo_overrides

FRONTEND_URL_DEFAULT = "https://klokkan.usable.dev"
TIMEOUT_SECONDS = 5 * 60
CONFIG_PATH = Path.home() / ".hermes" / "klokkan" / "config.json"
PLUGIN_DIR = Path.home() / ".hermes" / "plugins" / "klokkan"
ERROR_LOG_PATH = Path.home() / ".cache" / "klokkan" / "last-error.log"


def config_target(cwd: Path) -> tuple[Path, str]:
    repo_config = project_config_path(cwd)
    if repo_config:
        return repo_config, "repo"
    return CONFIG_PATH, "global"


def log_error(tag: str, message: str) -> None:
    try:
        ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(
                f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {tag}: {message}\n"
            )
    except Exception:
        pass


def effective_hint(cwd: Path, provided: str | None) -> str:
    cleaned = (provided or "").strip()
    if cleaned:
        return cleaned
    overrides = repo_overrides(cwd)
    return (overrides.get("hint") or derive_default_hint(cwd)).strip()


class CallbackState:
    def __init__(self, expected_state: str) -> None:
        self.expected_state = expected_state
        self.creds: dict[str, str] | None = None
        self.error: str | None = None
        self.done = False


def make_handler(state: CallbackState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            if self.path != "/callback":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            parsed = parse_qs(body)
            got_state = (parsed.get("state") or [""])[0]
            if got_state != state.expected_state:
                state.error = "state mismatch"
                state.done = True
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"state mismatch")
                return
            required = ("apiKey", "orgId", "projectId", "projectName", "apiBaseUrl")
            missing = [k for k in required if not (parsed.get(k) or [""])[0]]
            if missing:
                state.error = f"missing fields: {', '.join(missing)}"
                state.done = True
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"missing: {missing}".encode())
                return
            state.creds = {
                k: (parsed.get(k) or [""])[0]
                for k in (
                    "apiKey",
                    "apiKeyPrefix",
                    "orgId",
                    "clientId",
                    "projectId",
                    "projectName",
                    "clientName",
                    "apiBaseUrl",
                )
            }
            state.done = True
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><html><head><meta charset='utf-8'><title>Klokkan connected</title></head><body><h1>Klokkan connected</h1><p>You can close this tab and return to Hermes.</p></body></html>"
            )

        def do_GET(self) -> None:
            self.send_error(404)

    return Handler


def run_listener(expected_state: str) -> tuple[int, CallbackState, HTTPServer]:
    state = CallbackState(expected_state)
    server = HTTPServer(("127.0.0.1", 0), make_handler(state))
    port = server.server_address[1]
    return port, state, server


def write_config(creds: dict[str, str], hint: str, cwd: Path | None = None) -> str:
    cwd = cwd or Path.cwd()
    target_path, scope = config_target(cwd)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "apiKey": creds["apiKey"],
        "orgId": creds["orgId"],
        "clientId": creds.get("clientId") or None,
        "projectId": creds["projectId"],
        "projectName": creds["projectName"],
        "clientName": creds.get("clientName") or None,
        "apiBaseUrl": creds["apiBaseUrl"],
        "hint": hint,
    }
    target_path.write_text(json.dumps(body, indent=2) + "\n")
    target_path.chmod(0o600)
    if scope == "repo":
        ensure_project_config_ignored(cwd)
    return str(target_path)


def check_api(api_base_url: str, api_key: str) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/api/v1/agent/project"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            project_name = None
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    raw = parsed.get("name") or parsed.get("projectName")
                    if isinstance(raw, str):
                        project_name = raw
            except json.JSONDecodeError:
                pass
            return {
                "ok": 200 <= status < 300,
                "status": status,
                "url": url,
                "project": project_name,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "url": url, "error": str(exc.reason)}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc.reason)}
    except Exception as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc)}


def dry_run(frontend_url: str, hint: str) -> dict[str, Any]:
    target_path, scope = config_target(Path.cwd())
    return {
        "mode": "dry-run",
        "agent": "hermes",
        "frontend_url": frontend_url,
        "authorize_endpoint": f"{frontend_url}/dashboard/integrations/connect/authorize",
        "loopback_callback": "http://127.0.0.1:<random-port>/callback",
        "instance_hint": hint,
        "plugin_paths": {
            "plugin_dir": str(PLUGIN_DIR),
            "plugin_manifest": str(PLUGIN_DIR / "plugin.yaml"),
            "plugin_module": str(PLUGIN_DIR / "__init__.py"),
            "runtime_config": str(target_path),
        },
        "credentials": {
            "source": "browser -> 127.0.0.1 loopback POST",
            "scope": scope,
            "stored_at": str(target_path),
            "stored_mode": "0600",
            "fields": [
                "apiKey",
                "orgId",
                "clientId",
                "projectId",
                "projectName",
                "clientName",
                "apiBaseUrl",
                "hint",
            ],
        },
        "side_effects_in_dry_run": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Klokkan loopback connect helper for Hermes")
    parser.add_argument(
        "--hint",
        help="Optional instance hint. Defaults to repo-relative cwd or cwd basename.",
    )
    parser.add_argument(
        "--frontend-url",
        default=FRONTEND_URL_DEFAULT,
        help=f"Klokkan dashboard base URL (default: {FRONTEND_URL_DEFAULT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Hermes manual-connect plan and exit",
    )
    args = parser.parse_args()

    frontend_url = args.frontend_url.rstrip("/")
    hint = effective_hint(Path.cwd(), args.hint)

    if frontend_url != FRONTEND_URL_DEFAULT:
        print(
            f"WARNING: --frontend-url overridden to {frontend_url} (default is {FRONTEND_URL_DEFAULT}). If you did not explicitly request this, abort now.",
            file=sys.stderr,
        )

    if args.dry_run:
        print(json.dumps(dry_run(frontend_url, hint), indent=2))
        return 0

    expected_state = secrets.token_urlsafe(32)
    port, state, server = run_listener(expected_state)
    authorize_query = urlencode(
        {
            "redirect_uri": f"http://127.0.0.1:{port}/callback",
            "state": expected_state,
            "agent": "hermes",
            "hint": hint,
        }
    )
    authorize_url = f"{frontend_url}/dashboard/integrations/connect/authorize?{authorize_query}"
    print(f"OPEN_URL={authorize_url}", flush=True)

    thread = Thread(target=server.serve_forever, name="klokkan-hermes-listener", daemon=True)
    thread.start()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        while not state.done:
            if time.monotonic() > deadline:
                server.shutdown()
                server.server_close()
                print("TIMEOUT: no callback received within 5 minutes", file=sys.stderr)
                return 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
        print("INTERRUPTED", file=sys.stderr)
        return 1

    time.sleep(0.1)
    server.shutdown()
    server.server_close()

    if state.error or not state.creds:
        print(f"ERROR: {state.error or 'no credentials captured'}", file=sys.stderr)
        return 2

    try:
        config_path = write_config(state.creds, hint)
    except Exception as exc:
        print(f"ERROR: failed to write config: {exc}", file=sys.stderr)
        return 1

    api_check = check_api(state.creds["apiBaseUrl"], state.creds["apiKey"])
    _, scope = config_target(Path.cwd())
    result = {
        "status": "ok",
        "agent": "hermes",
        "instance_hint": hint,
        "config_scope": scope,
        "projectName": state.creds["projectName"],
        "clientName": state.creds.get("clientName") or None,
        "config_path": config_path,
        "plugin_dir": str(PLUGIN_DIR),
        "api_check": api_check,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
