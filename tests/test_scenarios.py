import json

import pytest

from chaoslab import scenarios
from tests.conftest import DEPLOY_SPEC


def test_ids_unique():
    assert len(scenarios.REGISTRY) == len(scenarios.SCENARIOS)


def test_choose_is_deterministic_for_seed():
    assert scenarios.choose(None, 42) is scenarios.choose(None, 42)


def test_choose_by_id_and_unknown():
    assert scenarios.choose("redis-down", 0).id == "redis-down"
    with pytest.raises(SystemExit):
        scenarios.choose("nope", 0)


@pytest.mark.parametrize("scenario", scenarios.SCENARIOS, ids=lambda s: s.id)
def test_inject_then_heal_restores_targets(scenario, kube, runner):
    state = scenarios.inject(kube, scenario, seed=7)
    assert state["scenario"] == scenario.id
    assert set(state["snapshots"]) == set(scenario.targets)
    assert json.loads(json.dumps(state))  # must be serialisable to state.json
    inject_calls = len(runner.calls)
    assert inject_calls > len(scenario.targets), "inject must mutate the cluster"

    scenarios.heal(kube, state)
    heal_calls = runner.calls[inject_calls:]
    patched = [c for c in heal_calls if c[3] == "patch"]
    assert [c[5] for c in patched] == list(scenario.targets)
    for call in patched:
        ops = json.loads(call[call.index("-p") + 1])
        assert {op["path"]: op["value"] for op in ops} == {
            f"/spec/{k}": DEPLOY_SPEC["spec"][k] for k in ("template", "strategy", "replicas")
        }
    deleted = [c[4] for c in heal_calls if c[3] == "delete"]
    assert deleted == list(scenario.created)


def test_recreate_strategy_applied_before_fault(kube, runner):
    scenarios.inject(kube, scenarios.REGISTRY["payment-bad-image"], seed=0)
    assert runner.verbs() == ["get", "patch", "set"]
    assert '"Recreate"' in runner.calls[1][-1]
