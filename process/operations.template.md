# Operations Template

This document is a generic operating model for a Hermes Portable instance.

## Daily Checks

- Run `hermes-portable doctor`
- Review stale heartbeats
- Review queued notifications
- Check disk usage

## Incident Flow

1. Detect anomaly
2. Classify severity
3. Check dependencies
4. Propose remediation
5. Execute only if policy allows
6. Write local incident note

## Publish Checklist

- No raw secrets
- No chat IDs
- No local paths
- No runtime logs
- No private incident history
- Tests or compile checks pass
