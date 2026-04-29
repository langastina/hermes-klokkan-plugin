# Hermes Klokkan Plugin

A Hermes Agent plugin that integrates Klokkan time tracking with Hermes session hooks.

What it does:
- Starts or resumes a Klokkan timer on each Hermes user prompt via `pre_llm_call`
- Refines the timer description from the current prompt excerpt without overwriting an already-refined entry; visible descriptions put the prompt/work text first, followed by repo/session context
- Stops the timer when Hermes finalizes a session via `on_session_finalize`
- Uses a local loopback browser flow to receive credentials directly from the Klokkan dashboard and store them only on the local machine

## Features

- Hermes-native plugin hooks instead of Claude/Cursor/Codex hook files
- Repo-local credentials by default at `<repo>/.klokkan.json` when you connect from inside a git repository
- Global fallback credentials at `~/.hermes/klokkan/config.json` only when you connect outside a git repository
- Optional per-repo `klokkan.md` files for repo-specific hint and description overrides
- Config file permissions set to `0600`
- Error logging to `~/.cache/klokkan/last-error.log`
- Derives a useful install/session hint from the current git repo and subdirectory
- Adds current git branch to the session label when available
- Tags timer descriptions with the current Hermes session ID so each session starts its own timer entry
- Includes the repo/project name in timer descriptions so entries stay attributable in Klokkan
- No repo-local files are required, but when `klokkan.md` is used it is read only and never mutated by the plugin

## Repository layout

- `plugin/klokkan/plugin.yaml` — Hermes plugin manifest
- `plugin/klokkan/__init__.py` — plugin hook implementation
- `plugin/klokkan/connect.py` — loopback auth helper
- `scripts/install_into_hermes.sh` — copy the plugin into a Hermes home directory

## Requirements

- Hermes Agent with plugin support
- Python 3.10+ (stdlib only; no third-party Python dependencies)
- A Klokkan account and access to `https://klokkan.usable.dev`

## Install

### 1. Clone the repository

```bash
git clone https://github.com/langastina/hermes-klokkan-plugin.git
cd hermes-klokkan-plugin
```

### 2. Install into Hermes

```bash
./scripts/install_into_hermes.sh ~/.hermes
```

This installs the plugin to:

```text
~/.hermes/plugins/klokkan/
```

### 3. Verify Hermes sees the plugin

```bash
hermes plugins list
```

You should see `klokkan` listed as enabled.

### 4. Review the auth helper dry-run

```bash
python3 ~/.hermes/plugins/klokkan/connect.py --dry-run
```

Expected properties:
- `agent: hermes`
- `frontend_url: https://klokkan.usable.dev`
- config target at `<repo>/.klokkan.json` when run inside a git repo, otherwise `~/.hermes/klokkan/config.json`
- no side effects in dry-run mode

### 5. Connect to Klokkan

```bash
python3 ~/.hermes/plugins/klokkan/connect.py
```

The helper prints a single line:

```text
OPEN_URL=<authorize-url>
```

Open that URL in your browser. After you choose the org/project in the Klokkan dashboard, the browser posts credentials directly to the local helper over `127.0.0.1`, and the helper writes credentials to:

```text
<repo>/.klokkan.json
```

when you run the helper inside a git repo. That file is added to `.git/info/exclude` automatically so it stays local-only.

When you run the helper outside a git repo, it falls back to:

```text
~/.hermes/klokkan/config.json
```

In both cases the file is written with mode `0600`.

## Per-repo overrides with `klokkan.md`

If you want different repositories to register time under different project labels, add a `klokkan.md` file at the repo root.

Example:

```md
---
project: argilzar-workouts
description_prefix: argilzar-workouts
---
```

Supported frontmatter keys:
- `hint` — overrides the saved default hint for this repo
- `project` or `project_name` — shorthand alias for `hint`
- `description_prefix` — optional prefix used for the timer description; defaults to the resolved hint

Behavior:
- the plugin searches upward from the current working directory to the git repo root for `klokkan.md`
- if found, the repo file wins over the saved `hint` in `~/.hermes/klokkan/config.json`
- timer descriptions become `<prompt excerpt> — <description_prefix> [session:<session_id>]` so the prompt/work text is the first visible text
- the start label still includes the current git branch when available

This makes it easy to keep per-repo Klokkan API keys while still controlling the visible repo label and timer description for each project.

## Security model

- Integrity of the official Klokkan upstream installer should still be verified separately if you use it for comparison or auditing.
- This plugin’s auth helper uses a loopback callback on `127.0.0.1`.
- Credentials are written locally and are not intended to be persisted by the Klokkan backend.
- Overriding `--frontend-url` emits a warning and should only be used for explicit development/testing.

## How it works

### `pre_llm_call`
On every Hermes user prompt, the plugin:
1. Loads repo-local Klokkan config from `<repo>/.klokkan.json` when inside a git repo
2. Falls back to `~/.hermes/klokkan/config.json` only when not inside a git repo
3. Starts or resumes the running timer using a description whose first text is the current prompt excerpt, followed by hint + branch/session context
4. Extracts up to 120 characters from the current prompt
5. PATCHes the running timer description with `onlyIfPlaceholder: true`

### `on_session_finalize`
When Hermes finalizes a session, the plugin sends a stop request to Klokkan.

## Caveats

- If Hermes crashes hard or is killed before `on_session_finalize` runs, the timer may remain running until you stop it manually.
- Inside a git repo, no timer calls are made until that repo has its own `.klokkan.json` credentials file.
- This implementation is Hermes-specific and does not attempt to emulate agent integrations for other tools.

## Development

Quick syntax check:

```bash
python3 -m py_compile plugin/klokkan/__init__.py plugin/klokkan/common.py plugin/klokkan/connect.py
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT
