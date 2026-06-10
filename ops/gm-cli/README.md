# gm-cli Operations

This directory keeps gm-cli operational files out of the repository root.

Detailed workflow:

```text
../../doc/gm_cli_task_submission_workflow.md
```

Project structure policy:

```text
../../doc/project_structure_and_cleanup.md
```

## Payloads

Use this directory for local request payloads:

```text
ops/gm-cli/payloads/
```

Payloads such as `create-*.json`, `edit-*.json`, and `copy-*.json` are local operational files and should not be committed.

Known-good local payload:

```text
payloads/create-validate-a10-public-known-good.json
```

This payload corresponds to the successful smoke task:

```text
TASK_20260608_073
```
