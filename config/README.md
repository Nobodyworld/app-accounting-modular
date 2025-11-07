# docker/

Container build definitions for local development and CI smoke tests.

- `Dockerfile.api` – Builds the FastAPI service image.
- `Dockerfile.web` – Packages the Streamlit UI.

Compose files live in the repository root; consult [docs/operations/automation_playbook.md](../docs/operations/automation_playbook.md) for deployment notes.
