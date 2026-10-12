"""Local k3d cluster lifecycle and Online Boutique deployment.

k3d talks to the host Docker daemon through the mounted socket, so the
cluster runs as sibling containers and outlives the chaos-lab container.
"""

import json
import os
from pathlib import Path

from chaoslab.kube import Kube, subprocess_runner

CLUSTER = os.environ.get("CHAOS_CLUSTER", "boutique")
API_PORT = os.environ.get("CHAOS_API_PORT", "6550")
HTTP_PORT = os.environ.get("CHAOS_HTTP_PORT", "8080")
MANIFESTS = Path(os.environ.get("CHAOS_MANIFESTS", Path(__file__).resolve().parent.parent / "manifests"))


def k3d(*args: str) -> str:
    return subprocess_runner(["k3d", *args])


def exists() -> bool:
    return any(c["name"] == CLUSTER for c in json.loads(k3d("cluster", "list", "-o", "json")))


def create() -> None:
    k3d(
        "cluster", "create", CLUSTER,
        "--api-port", f"127.0.0.1:{API_PORT}",
        # k3s' built-in ServiceLB serves frontend-external (type LoadBalancer) on node port 80.
        "-p", f"{HTTP_PORT}:80@loadbalancer",
        # Traefik isn't used by Online Boutique; skip it to save CPU.
        "--k3s-arg", "--disable=traefik@server:0",
        "--wait",
    )


def delete() -> None:
    k3d("cluster", "delete", CLUSTER)


def write_kubeconfig(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(k3d("kubeconfig", "get", CLUSTER))
    path.chmod(0o600)


def deploy(kube: Kube) -> None:
    kube.run("apply", "-k", str(MANIFESTS))
    kube.run("wait", "--for=condition=available", "deployment", "--all", "--timeout=900s")
