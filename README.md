# Hermes Portable Package

Hermes Portable Package is a template kit for moving a Hermes-style agent
system across machines without copying private machine state into Git.

The repository contains reusable architecture, scripts, skills, and knowledge
templates. Each computer generates its own local configuration and secrets.

## Design

```text
Git repository
  templates, core code, scripts, skills, docs

Local portable home
  ~/.hermes-portable/config.yaml
  ~/.hermes-portable/secrets.env
  ~/.hermes-portable/key_pool.json
  ~/.hermes-portable/runtime/

Hermes runtime home
  ~/.hermes/plan_registry/
  ~/.hermes/scripts/
  ~/.hermes/references/
```

The repo is the mold. The local homes are the instance.

## Quick Start

```bash
python -m pip install -e .
python -m hermes_portable.cli init
python -m hermes_portable.cli doctor
```

To install the bundled templates into a Hermes runtime home:

```bash
python -m hermes_portable.cli init --install-templates
```

Use custom locations on any machine:

```bash
python -m hermes_portable.cli init \
  --portable-home ./local-portable \
  --hermes-home ./local-hermes
```

On Windows PowerShell:

```powershell
python -m pip install -e .
python -m hermes_portable.cli init --portable-home .\local-portable --hermes-home .\local-hermes
python -m hermes_portable.cli doctor --portable-home .\local-portable --hermes-home .\local-hermes
```

## What Belongs In Git

- Generic PLAN Registry / Factory / Watchdog code
- Generic worker skills
- Architecture docs
- Example configuration
- Test fixtures

## What Must Stay Local

- API keys and bot tokens
- Telegram chat IDs
- User-specific profile values
- Heartbeats, logs, cache, and runtime state
- Machine-specific absolute paths

## Secrets

`key_pool.json` stores environment variable names, not raw secret values.
Put real values in the generated local `secrets.env` or your OS keychain.

Bad:

```json
{"key": "sk-real-secret"}
```

Good:

```json
{"env": "OPENAI_API_KEY"}
```

## Safety Defaults

Generated configs default to supervised mode:

- No automatic restarts unless enabled locally
- No automatic Git push unless enabled locally
- No destructive cleanup unless enabled locally
- Local web servers should bind `127.0.0.1` unless you explicitly expose them

## Useful Commands

```bash
python -m hermes_portable.cli show-template config
python -m hermes_portable.cli show-template secrets
python -m hermes_portable.cli show-template key-pool
python -m hermes_portable.cli doctor
```

## Migration From A Personal Snapshot

1. Revoke and rotate any keys that were ever committed.
2. Move real secrets into local `secrets.env`.
3. Replace personal values in `config/Owner_profile.yaml` with placeholders.
4. Run `doctor` before publishing.
5. Clean Git history before making a public release if secrets were committed.

## Status

This repository is now structured as a portable template, but the older scripts
still need deeper hardening before fully autonomous use:

- Replace remaining `shell=True` calls with allowlisted argv execution.
- Add dry-run support to state-changing scripts.
- Add CI for tests and secret scanning.
- Move hard-coded `~/.hermes` references behind shared path helpers.
