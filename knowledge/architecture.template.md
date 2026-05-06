# Hermes Portable Architecture Template

Hermes Portable separates reusable architecture from local runtime state.

## Layers

1. Prompt and policy layer
2. Local profile and configuration layer
3. PLAN registry and command layer
4. Worker skills and automation layer
5. Local runtime logs, heartbeats, and reports

## Repository Boundary

The Git repository stores only:

- Generic code
- Generic skills
- Example configuration
- Architecture templates
- Tests and safety documentation

The repository must not store:

- Chat history
- API keys or tokens
- Real account IDs
- Runtime heartbeats
- Local absolute paths
- Business incident logs

## Runtime Boundary

Each machine creates its own runtime directories through:

```bash
python -m hermes_portable.cli init
```

The local runtime owns secrets, state, and machine-specific configuration.

## Safety Defaults

- Supervised autonomy by default
- Dry-run preferred for state-changing tasks
- Localhost-only network binding by default
- Environment-variable references instead of raw secrets
- Fail-closed notification routing
