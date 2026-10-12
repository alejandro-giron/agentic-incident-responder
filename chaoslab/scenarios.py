"""Failure scenarios and the engine that injects and heals them.

Healing is generic: before injecting, the spec (template, strategy, replicas)
of every target Deployment is snapshotted into the state file, and heal
patches it back verbatim. Extra objects a scenario creates are deleted.

Scenarios whose broken pods would never become Ready set `recreate=True`.
Under the default RollingUpdate strategy the old healthy pod would keep serving
and the fault would only show up as a stuck rollout, so we switch the
Deployment to Recreate first.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from chaoslab.kube import Kube

IMAGE_REPO = "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo"


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str  # the "answer": revealed only by `reveal`
    targets: tuple[str, ...]  # Deployments snapshotted before inject, restored on heal
    inject: Callable[[Kube], None]
    created: tuple[str, ...] = ()  # extra objects (kind/name) deleted on heal
    recreate: bool = False


PAYMENT_DENY_ALL = """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: paymentservice-ingress
spec:
  podSelector:
    matchLabels:
      app: paymentservice
  policyTypes: [Ingress]
  ingress: []
"""


def _payment_netpol(k: Kube) -> None:
    k.apply(PAYMENT_DENY_ALL)
    # Policies only block new connections; checkoutservice holds a long-lived
    # gRPC connection, so replace the pod to force it to reconnect.
    k.delete_pods("app=paymentservice")


SCENARIOS = [
    Scenario(
        id="catalog-latency",
        description="productcatalogservice has EXTRA_LATENCY=3s set: every catalog call is slow, so pages are slow or time out.",
        targets=("productcatalogservice",),
        inject=lambda k: k.set_env("productcatalogservice", EXTRA_LATENCY="3s"),
    ),
    Scenario(
        id="redis-down",
        description="redis-cart is scaled to 0 replicas: cartservice can't reach Redis and goes NotReady, so cart operations fail.",
        targets=("redis-cart",),
        inject=lambda k: k.scale("redis-cart", 0),
    ),
    Scenario(
        id="cart-bad-config",
        description="cartservice REDIS_ADDR points at redis-cart:6380 (wrong port): pods still report Ready, but every cart call fails, so pages 500.",
        targets=("cartservice",),
        inject=lambda k: k.set_env("cartservice", REDIS_ADDR="redis-cart:6380"),
    ),
    Scenario(
        id="currency-oom",
        description="currencyservice memory limit lowered to 24Mi: OOMKilled / CrashLoopBackOff, so every page needing prices fails.",
        targets=("currencyservice",),
        inject=lambda k: k.set_resources("currencyservice", limits="memory=24Mi", requests="memory=16Mi"),
        recreate=True,
    ),
    Scenario(
        id="payment-bad-image",
        description="paymentservice image set to a tag that doesn't exist (v0.10.7-hotfix1): ImagePullBackOff, so checkout fails.",
        targets=("paymentservice",),
        inject=lambda k: k.set_image("paymentservice", "server", f"{IMAGE_REPO}/paymentservice:v0.10.7-hotfix1"),
        recreate=True,
    ),
    Scenario(
        id="frontend-cpu-throttle",
        description="frontend CPU limit lowered to 5m: heavy CFS throttling while rendering, so every page is 30-50x slower (no errors).",
        targets=("frontend",),
        inject=lambda k: k.set_resources("frontend", limits="cpu=5m", requests="cpu=5m"),
    ),
    Scenario(
        id="payment-netpol",
        description="NetworkPolicy 'paymentservice-ingress' denies all ingress to paymentservice: pods look healthy but checkout can't reach payment.",
        targets=(),
        inject=_payment_netpol,
        created=("networkpolicy/paymentservice-ingress",),
    ),
    Scenario(
        id="frontend-bad-readiness",
        description="frontend readinessProbe points at port 8081 (the app listens on 8080): pod never Ready, Service has no endpoints, site is down.",
        targets=("frontend",),
        inject=lambda k: k.patch_json("deployment", "frontend", [
            {"op": "replace", "path": "/spec/template/spec/containers/0/readinessProbe/httpGet/port", "value": 8081},
        ]),
        recreate=True,
    ),
    Scenario(
        id="email-scaled-zero",
        description="emailservice is scaled to 0 replicas: orders still succeed, but checkoutservice logs 'failed to send order confirmation' warnings.",
        targets=("emailservice",),
        inject=lambda k: k.scale("emailservice", 0),
    ),
    Scenario(
        id="shipping-bad-addr",
        description="checkoutservice SHIPPING_SERVICE_ADDR typo'd to shipping-service:50051: DNS lookups fail, so checkout errors on shipping quotes.",
        targets=("checkoutservice",),
        inject=lambda k: k.set_env("checkoutservice", SHIPPING_SERVICE_ADDR="shipping-service:50051"),
    ),
]

REGISTRY = {s.id: s for s in SCENARIOS}


def choose(scenario_id: str | None, seed: int) -> Scenario:
    if scenario_id:
        if scenario_id not in REGISTRY:
            raise SystemExit(f"unknown scenario {scenario_id!r}; known: {', '.join(REGISTRY)}")
        return REGISTRY[scenario_id]
    return random.Random(seed).choice(SCENARIOS)


def inject(kube: Kube, scenario: Scenario, seed: int) -> dict:
    """Apply the scenario and return the state needed to reveal and heal it."""
    snapshots = {}
    for deploy in scenario.targets:
        spec = kube.get_json("deployment", deploy)["spec"]
        snapshots[deploy] = {k: spec[k] for k in ("template", "strategy", "replicas")}
    for deploy in scenario.targets if scenario.recreate else ():
        kube.patch_json("deployment", deploy, [{"op": "replace", "path": "/spec/strategy", "value": {"type": "Recreate"}}])
    scenario.inject(kube)
    return {
        "scenario": scenario.id,
        "seed": seed,
        "injected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshots": snapshots,
        "created": list(scenario.created),
    }


def heal(kube: Kube, state: dict) -> None:
    for ref in state["created"]:
        kube.delete(ref)
    for deploy, snap in state["snapshots"].items():
        kube.patch_json("deployment", deploy, [
            {"op": "replace", "path": f"/spec/{field}", "value": snap[field]}
            for field in ("template", "strategy", "replicas")
        ])
    for deploy in state["snapshots"]:
        kube.wait_rollout(deploy)
