from scripts.seed_close_demo import seed_close_demo

from tests._close_helpers import close_session


def test_controlled_close_demo_contains_two_person_controls_and_blockers() -> None:
    with close_session() as (session, _):
        # The helper fixture already creates a different organization, so the
        # deterministic named demo remains safe to seed in the same test DB.
        payload = seed_close_demo(session)
        assert len(payload["users"]) == 3
        assert payload["staged_transaction_id"]
        assert payload["budget_id"]
        assert payload["cash_account_id"]
