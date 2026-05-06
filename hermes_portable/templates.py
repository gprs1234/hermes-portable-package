"""Built-in templates used by `hermes-portable init`."""

from __future__ import annotations


CONFIG_TEMPLATE = """# Hermes Portable local configuration.
# This file is generated per machine and should not be committed.

profile:
  name: "Your Name"
  timezone: "UTC+8"
  language: "zh-TW"

paths:
  hermes_home: "{hermes_home}"
  portable_home: "{portable_home}"

autonomy:
  # off: diagnostics only
  # supervised: require approval for state-changing actions
  # autonomous: allow configured actions without prompting
  level: "supervised"
  allow_restart: false
  allow_git_push: false
  allow_delete_logs: false
  allow_external_api_calls: false

notifications:
  provider: "telegram"
  chat_id_env: "TELEGRAM_CHAT_ID"
  bot_token_env: "TELEGRAM_BOT_TOKEN"

security:
  bind_host: "127.0.0.1"
  require_dry_run_by_default: true
  command_allowlist:
    - "python"
    - "python3"
    - "git"
"""


SECRETS_TEMPLATE = """# Local secrets for Hermes Portable.
# Keep this file out of Git.

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
OPENAI_API_KEY=
GOOGLE_API_KEY=
NVIDIA_API_KEY=
"""


KEY_POOL_TEMPLATE = """{
  "version": "0.3",
  "description": "Example key pool. Store only env var names here, never raw keys.",
  "rotation_threshold": 0.95,
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "keys": [
        {
          "key_id": "openai-main",
          "env": "OPENAI_API_KEY",
          "status": "active",
          "usage": {"last_checked": null, "percentage": null}
        }
      ]
    },
    "google": {
      "base_url": "https://generativelanguage.googleapis.com/v1",
      "keys": [
        {
          "key_id": "google-main",
          "env": "GOOGLE_API_KEY",
          "status": "standby",
          "usage": {"last_checked": null, "percentage": null}
        }
      ]
    }
  },
  "rotation_log": []
}
"""
