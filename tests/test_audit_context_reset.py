from __future__ import annotations

from apps.api.audit import AuditActor, get_current_actor, pop_actor, push_actor


def test_pop_actor_handles_cross_thread_reset() -> None:
    token = push_actor(AuditActor(request_id="req"))
    # Simulate context loss in another thread
    push_actor(None)  # type: ignore[arg-type]
    pop_actor(token)
    assert get_current_actor() is None
