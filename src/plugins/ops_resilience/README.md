# Operations Resilience Extension

This reference extension demonstrates how observability-focused packages can
expose health probes, structured contracts, and operator playbooks. The
`register` function publishes:

- A manifest advertising the `operations` and `observability` capabilities.
- An incident playbook contract (`observability:incident-playbook`) that maps to
  the `get_playbook` entrypoint.
- A lightweight health check that confirms the playbook is available so the
  platform can surface the steps in dashboards or automation workflows.

Use this extension as a starting point when defining richer operational
connectors or when experimenting with agent-driven incident response.
