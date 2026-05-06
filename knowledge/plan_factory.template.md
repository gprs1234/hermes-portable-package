# PLAN Factory Template

The PLAN Factory converts an idea into a structured, monitored PLAN.

## Inputs

- Name
- Description
- Domain
- Interfaces
- Data layer
- Autonomy level
- Human approval requirements

## Output Files

```text
plans/<plan_id>/
  blueprint.json
  heartbeat.json
  main.py
  monitor.py
  skill.json
```

## Creation Phases

1. Understand the need
2. Choose interfaces
3. Choose storage
4. Choose implementation stack
5. Define autonomy and escalation rules
6. Generate blueprint
7. Register in PLAN Registry
8. Report next actions

## Template Rule

Generated plans may contain local state, but the public template repository must
contain only generic examples.
