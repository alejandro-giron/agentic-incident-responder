from chaoslab import state


def test_roundtrip_and_clear():
    assert state.load() is None
    state.save({"scenario": "redis-down"})
    assert state.load() == {"scenario": "redis-down"}
    state.clear()
    assert state.load() is None
    state.clear()  # idempotent
