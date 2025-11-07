# Scenario Variance Toolkit

This reference extension demonstrates how extensions can advertise contracts
that downstream automation can consume. When enabled it publishes a
`scenario-augmentation` contract (`Base currency variance`) which generates
downside/upside variants for supplied snapshot scenarios.

Use `macli inspect-contracts` to list the registered contract and review the
schema payloads exposed to other agents.
