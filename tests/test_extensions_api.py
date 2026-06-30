from apps.api.main import create_app
from fastapi.testclient import TestClient


def test_list_contracts_exposes_variance_contract() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/extensions/contracts")

    assert response.status_code == 200
    payload = response.json()
    assert any(
        item["extension_key"] == "scenarios:variance" and item["kind"] == "scenario-augmentation" for item in payload
    )
