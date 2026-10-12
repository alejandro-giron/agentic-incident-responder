import json

import pytest

from chaoslab.kube import Kube

DEPLOY_SPEC = {
    "spec": {
        "replicas": 1,
        "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"}},
        "template": {"spec": {"containers": [{"name": "server", "image": "img:v1"}]}},
    }
}


class FakeRunner:
    """Records kubectl invocations; answers `get ... -o json` with a canned Deployment."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, args, stdin=None):
        self.calls.append(list(args))
        return json.dumps(DEPLOY_SPEC) if "get" in args else ""

    def verbs(self):
        # kubectl -n default <verb> ...
        return [c[3] for c in self.calls]


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def kube(runner):
    return Kube(runner)


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_STATE_DIR", str(tmp_path))
    return tmp_path
