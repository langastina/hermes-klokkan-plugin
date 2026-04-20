from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

PROMPT_EXCERPT_CHARS = 120
REPO_CONFIG_FILENAME = "klokkan.md"
PROJECT_CONFIG_FILENAME = ".klokkan.json"
_ALLOWED_KEYS = {
    "hint": "hint",
    "project": "hint",
    "project_name": "hint",
    "description_prefix": "description_prefix",
}


def git(args: list[str], cwd: Path) -> str:
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


def _dot_git_root(cwd: Path) -> Path | None:
    for directory in _candidate_dirs(cwd):
        if (directory / ".git").exists():
            return directory
    return None


def resolve_repo_root(cwd: Path) -> Path:
    root = git(["rev-parse", "--show-toplevel"], cwd)
    if root:
        return Path(root)
    return _dot_git_root(cwd) or cwd


def in_git_repo(cwd: Path) -> bool:
    return bool(git(["rev-parse", "--show-toplevel"], cwd) or _dot_git_root(cwd))


def project_config_path(cwd: Path) -> Path | None:
    if not in_git_repo(cwd):
        return None
    return resolve_repo_root(cwd) / PROJECT_CONFIG_FILENAME


def git_exclude_path(cwd: Path) -> Path | None:
    git_path = git(["rev-parse", "--git-path", "info/exclude"], cwd)
    if git_path:
        resolved = Path(git_path)
        if not resolved.is_absolute():
            resolved = (cwd / resolved).resolve()
        return resolved
    if not in_git_repo(cwd):
        return None
    return resolve_repo_root(cwd) / ".git" / "info" / "exclude"


def ensure_project_config_ignored(cwd: Path) -> Path | None:
    exclude_path = git_exclude_path(cwd)
    if not exclude_path:
        return None
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = exclude_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    entries = {line.strip() for line in existing.splitlines() if line.strip()}
    if PROJECT_CONFIG_FILENAME not in entries:
        prefix = "\n" if existing and not existing.endswith("\n") else ""
        with exclude_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{prefix}{PROJECT_CONFIG_FILENAME}\n")
    return exclude_path



def derive_default_hint(cwd: Path) -> str:
    repo_root = resolve_repo_root(cwd)
    try:
        relative = cwd.resolve().relative_to(repo_root.resolve())
    except Exception:
        return cwd.name or str(cwd)
    repo_name = repo_root.name or cwd.name or str(cwd)
    relative_str = relative.as_posix()
    if relative_str in ("", "."):
        return repo_name
    return f"{repo_name}/{relative_str}"



def _candidate_dirs(cwd: Path) -> list[Path]:
    try:
        resolved = cwd.resolve()
    except Exception:
        resolved = cwd
    dirs = [resolved]
    current = resolved
    while current.parent != current:
        current = current.parent
        dirs.append(current)
    return dirs



def find_repo_config(cwd: Path) -> Path | None:
    for directory in _candidate_dirs(cwd):
        candidate = directory / REPO_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None



def _parse_frontmatter(text: str) -> dict[str, str]:
    stripped = text.lstrip()
    if not stripped.startswith("---\n"):
        return {}
    _, _, remainder = stripped.partition("---\n")
    frontmatter, marker, _ = remainder.partition("\n---")
    if not marker:
        return {}
    parsed: dict[str, str] = {}
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = _ALLOWED_KEYS.get(key.strip().lower())
        if not normalized_key:
            continue
        cleaned_value = value.strip().strip("\"'")
        if cleaned_value and normalized_key not in parsed:
            parsed[normalized_key] = cleaned_value
    return parsed



def repo_overrides(cwd: Path) -> dict[str, str]:
    config_path = find_repo_config(cwd)
    if not config_path:
        return {}
    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception:
        return {}
    return _parse_frontmatter(text)



def _resolved_hint(cfg: dict[str, Any], cwd: Path) -> str:
    overrides = repo_overrides(cwd)
    return (overrides.get("hint") or (cfg.get("hint") or "").strip() or derive_default_hint(cwd)).strip()



def _description_prefix(cfg: dict[str, Any], cwd: Path) -> str:
    overrides = repo_overrides(cwd)
    return (overrides.get("description_prefix") or _resolved_hint(cfg, cwd)).strip()



def session_label(cfg: dict[str, Any], cwd: Path | None = None) -> str:
    cwd = cwd or Path.cwd()
    base = _resolved_hint(cfg, cwd)
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch and branch != "HEAD":
        if base == branch or base.endswith(f"/{branch}") or base.endswith(f" · {branch}"):
            return base
        return f"{base} · {branch}"
    return base



def with_context(cfg: dict[str, Any], suffix: str = "", cwd: Path | None = None) -> str:
    cwd = cwd or Path.cwd()
    label = _description_prefix(cfg, cwd)
    suffix = suffix.strip()
    return f"{label} — {suffix}" if suffix else label



def excerpt(text: str) -> str:
    return " ".join((text or "").split())[:PROMPT_EXCERPT_CHARS].strip()
