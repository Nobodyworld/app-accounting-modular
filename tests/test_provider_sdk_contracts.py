from dataclasses import FrozenInstanceError

import pytest

from apps.provider_sdk import ProviderManifest, ProviderManifestError, required_methods


def manifest(**overrides: object) -> ProviderManifest:
    values: dict[str, object] = {
        "key": "market:example_demo",
        "name": "Example Provider",
        "version": "0.3.0",
        "api_major": 0,
        "capabilities": ("market",),
        "description": "  Example description  ",
        "license": "Apache-2.0",
    }
    values.update(overrides)
    return ProviderManifest(**values)  # type: ignore[arg-type]


def test_manifest_is_normalized_immutable_and_serializable() -> None:
    value = manifest(capabilities=("tax", "market"), credential_env=())
    assert value.capabilities == ("market", "tax")
    assert value.description == "Example description"
    assert value.to_dict()["capabilities"] == ["market", "tax"]
    with pytest.raises(FrozenInstanceError):
        value.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key", "bad"),
        ("key", "Market:bad"),
        ("name", " "),
        ("version", "1"),
        ("api_major", True),
        ("api_major", 1000),
        ("factory", "not-valid"),
        ("sdk_version", "1"),
        ("capabilities", ()),
        ("capabilities", ("market", "market")),
        ("capabilities", ("unknown",)),
        ("capabilities", "market"),
        ("capabilities", (1,)),
        ("network_policy", "ftp"),
        ("data_classification", "private"),
        ("homepage", "http://example.com"),
        ("credential_env", ("lowercase",)),
        ("credential_env", ("TOKEN", "TOKEN")),
    ],
)
def test_manifest_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ProviderManifestError):
        manifest(**{field: value})


def test_manifest_accepts_existing_underscore_keys_and_https_credentials() -> None:
    value = manifest(
        key="tax:oecd_vat",
        capabilities=("tax",),
        network_policy="https",
        credential_env=("TOKEN",),
    )
    assert value.key == "tax:oecd_vat"
    assert value.credential_env == ("TOKEN",)


def test_manifest_rejects_credentials_without_network() -> None:
    with pytest.raises(ProviderManifestError, match="network_policy"):
        manifest(credential_env=("TOKEN",))


def test_optional_blank_text_becomes_none_and_bounds_are_enforced() -> None:
    value = manifest(description=" ", homepage=" ", license=" ")
    assert value.description is None
    assert value.homepage is None
    assert value.license is None
    with pytest.raises(ProviderManifestError, match="description exceeds"):
        manifest(description="x" * 513)


def test_required_methods_are_sorted_and_ignore_unknown_capabilities() -> None:
    assert required_methods(("bank", "fx", "unknown")) == (
        "fetch_transactions",
        "list_accounts",
        "sync_daily_rates",
    )
