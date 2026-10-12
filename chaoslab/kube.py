"""Thin wrapper around the kubectl binary.

Every cluster mutation goes through Kube.run so tests can swap in a fake runner
and so the exact commands are easy to read (and to replay by hand).
"""

import json
import subprocess
from typing import Callable, Sequence

Runner = Callable[[Sequence[str], str | None], str]


def subprocess_runner(args: Sequence[str], stdin: str | None = None) -> str:
    result = subprocess.run(list(args), input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


class Kube:
    def __init__(self, runner: Runner = subprocess_runner, namespace: str = "default"):
        self._runner = runner
        self.namespace = namespace

    def run(self, *args: str, stdin: str | None = None) -> str:
        return self._runner(["kubectl", "-n", self.namespace, *args], stdin)

    def get_json(self, kind: str, name: str) -> dict:
        return json.loads(self.run("get", kind, name, "-o", "json"))

    def patch_json(self, kind: str, name: str, ops: list[dict]) -> None:
        self.run("patch", kind, name, "--type=json", "-p", json.dumps(ops))

    def set_env(self, deploy: str, **env: str) -> None:
        self.run("set", "env", f"deployment/{deploy}", *(f"{k}={v}" for k, v in env.items()))

    def set_resources(self, deploy: str, limits: str, requests: str) -> None:
        self.run("set", "resources", f"deployment/{deploy}", f"--limits={limits}", f"--requests={requests}")

    def set_image(self, deploy: str, container: str, image: str) -> None:
        self.run("set", "image", f"deployment/{deploy}", f"{container}={image}")

    def scale(self, deploy: str, replicas: int) -> None:
        self.run("scale", f"deployment/{deploy}", f"--replicas={replicas}")

    def apply(self, manifest: str) -> None:
        self.run("apply", "-f", "-", stdin=manifest)

    def delete(self, ref: str) -> None:
        self.run("delete", ref, "--ignore-not-found")

    def delete_pods(self, selector: str) -> None:
        self.run("delete", "pods", "-l", selector, "--wait=false")

    def wait_rollout(self, deploy: str, timeout: str = "300s") -> None:
        self.run("rollout", "status", f"deployment/{deploy}", f"--timeout={timeout}")
