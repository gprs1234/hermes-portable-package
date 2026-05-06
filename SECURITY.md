# Security Policy

## Secrets

Never commit raw API keys, bot tokens, chat IDs, account IDs, or private
machine paths. Use `.env.example`, environment variables, or an OS keychain.

If a secret is committed:

1. Revoke it with the provider immediately.
2. Rotate to a new value.
3. Remove it from the current tree.
4. Clean Git history before publishing the repository.

## Autonomy Levels

Local configs should use one of three modes:

- `off`: diagnostics only.
- `supervised`: state-changing actions require approval.
- `autonomous`: only for trusted private machines with explicit allowlists.

Public templates must default to `supervised`.

## Dangerous Operations

The following operations must support dry-run or approval before production use:

- Restarting processes
- Deleting logs or backups
- Rotating API keys
- Pushing to Git remotes
- Calling external paid APIs
- Binding services to public interfaces

## Command Execution

Avoid `shell=True`. Prefer argv lists and a command allowlist. If a command must
use a shell, keep it local-only, documented, and disabled by default.

## Network Binding

Development servers should bind to `127.0.0.1` by default. Use `0.0.0.0` only
when the machine has firewall rules and authentication configured.
