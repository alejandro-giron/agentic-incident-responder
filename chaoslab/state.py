"""Ground truth for the active incident, kept outside the cluster.

Lives on a host-mounted volume so investigators (human or agent) working
through kubectl can't read the answer from inside the cluster.
"""

import json
import os
from pathlib import Path


def state_dir() -> Path:
    return Path(os.environ.get("CHAOS_STATE_DIR", "/state"))


def _path() -> Path:
    return state_dir() / "state.json"


def load() -> dict | None:
    path = _path()
    return json.loads(path.read_text()) if path.exists() else None


def save(state: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def clear() -> None:
    _path().unlink(missing_ok=True)
