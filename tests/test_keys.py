from __future__ import annotations

from echotools.keys import KeyPool, KeyState


def test_key_state_success_resets_failures() -> None:
    ks = KeyState(key="k1")
    ks.mark_failure()
    ks.mark_success()
    assert ks.n_fails == 0
    assert ks.is_ready()


def test_key_pool_rotation() -> None:
    pool = KeyPool(["k1", "k2"])
    first = pool.get_best()
    assert first is not None
    first.mark_failure(cooldown=0.0)
    second = pool.get_best()
    assert second is not None
    assert second.key != first.key


def test_key_pool_available_count() -> None:
    pool = KeyPool(["a", "b", "c"])
    assert pool.available_count == 3
    assert pool.total_count == 3
