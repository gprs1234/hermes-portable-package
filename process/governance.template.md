# Governance Template

Use this template to define approval and autonomy rules for a local Hermes
instance.

## Autonomy Levels

- `off`: observe only
- `supervised`: propose actions, require approval for changes
- `autonomous`: execute allowlisted actions

## Approval Classes

| Class | Examples | Default |
| --- | --- | --- |
| Readonly | status, health, list, diff | allowed |
| Low risk | local report generation, cache refresh | supervised |
| State changing | restart, write config, rotate keys | approval required |
| Destructive | delete, force push, credential changes | explicit approval |

## Required Controls

- Dry-run for state-changing actions
- Command allowlist
- Secret scanning before publish
- Audit log for automation decisions
- Runtime state kept outside Git
