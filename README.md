# Hermes Klokkan Plugin

A Hermes Agent plugin that integrates Klokkan time tracking with Hermes session hooks.

What it does:
- Starts or resumes a Klokkan timer on each Hermes user prompt via `pre_llm_call`
- Refines the timer description from the current prompt excerpt without overwriting an already-refined entry
- Stops the timer when Hermes finalizes a session via `on_session_finalize`
- Uses a local loopback browser flow to receive credentials directly from the Klokkan dashboard and store them only on the local machine

## Features

- Hermes-native plugin hooks instead of Claude/Cursor/Codex hook files
- Local-only credentials at `~/.hermes/klokkan/config.json`
- Config file permissions set to `0600`
- Error logging to `~/.cache/klokkan/last-error.log`
- Derives a useful install/session hint from the current git repo and subdirectory
- Adds current git branch to the session label when available
- No repo-local files and no git exclude mutations required

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
- config target at `~/.hermes/klokkan/config.json`
- no side effects in dry-run mode

### 5. Connect to Klokkan

```bash
python3 ~/.hermes/plugins/klokkan/connect.py
```

The helper prints a single line:

```text
OPEN_URL=<authorize-url>
```

Open that URL in your browser. After you choose the org/project in the Klokkan dashboard, the browser posts credentials directly to the local helper over `127.0.0.1`, and the helper writes:

```text
~/.hermes/klokkan/config.json
```

with mode `0600`.

## Security model

- Integrity of the official Klokkan upstream installer should still be verified separately if you use it for comparison or auditing.
- This plugin’s auth helper uses a loopback callback on `127.0.0.1`.
- Credentials are written locally and are not intended to be persisted by the Klokkan backend.
- Overriding `--frontend-url` emits a warning and should only be used for explicit development/testing.

## How it works

### `pre_llm_call`
On every Hermes user prompt, the plugin:
1. Loads local Klokkan config
2. Starts or resumes the running timer using a label derived from hint + branch
3. Extracts up to 120 characters from the current prompt
4. PATCHes the running timer description with `onlyIfPlaceholder: true`

### `on_session_finalize`
When Hermes finalizes a session, the plugin sends a stop request to Klokkan.

## Caveats

- If Hermes crashes hard or is killed before `on_session_finalize` runs, the timer may remain running until you stop it manually.
- This implementation is Hermes-specific and does not attempt to emulate agent integrations for other tools.

## Development

Quick syntax check:

```bash
python3 -m py_compile plugin/klokkan/__init__.py plugin/klokkan/connect.py
```

## License

MIT
