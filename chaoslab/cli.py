import argparse
import os
import random
import time

from chaoslab import cluster, scenarios, state
from chaoslab.kube import Kube


def log(msg: str) -> None:
    print(f"[chaos-lab] {msg}", flush=True)


def kubeconfig_path():
    return state.state_dir() / "kubeconfig"


def make_kube() -> Kube:
    os.environ["KUBECONFIG"] = str(kubeconfig_path())
    return Kube()


def cmd_up(args) -> None:
    if cluster.exists():
        log(f"cluster '{cluster.CLUSTER}' already exists")
    else:
        log(f"creating k3d cluster '{cluster.CLUSTER}'")
        cluster.create()
    cluster.write_kubeconfig(kubeconfig_path())
    kube = make_kube()
    log("deploying Online Boutique and waiting for all deployments to become available (first run pulls images)")
    cluster.deploy(kube)
    if args.no_inject:
        log(f"healthy. Storefront: http://localhost:{cluster.HTTP_PORT}")
        return
    if state.load():
        log("an incident is already active; not injecting another (run `heal` first)")
        return
    warmup = int(os.environ.get("CHAOS_WARMUP", "60"))
    log(f"healthy. Warming up for {warmup}s so there's a healthy baseline in the logs")
    time.sleep(warmup)
    cmd_inject(args)


def cmd_inject(args) -> None:
    if state.load():
        raise SystemExit("an incident is already active; run `heal` first")
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**32)
    scenario = scenarios.choose(args.scenario, seed)
    state.save(scenarios.inject(make_kube(), scenario, seed))
    log("🔥 an incident has been injected. Good luck!")
    log(f"  storefront: http://localhost:{cluster.HTTP_PORT}")
    log("  investigate: export KUBECONFIG=$PWD/.chaos/kubeconfig; kubectl get pods")
    log("  when done: `reveal` to see the answer, `heal` to fix it")


def cmd_status(args) -> None:
    log("incident active" if state.load() else "no incident active")
    print(make_kube().run("get", "pods", "-o", "wide"), end="")


def cmd_reveal(args) -> None:
    current = state.load()
    if not current:
        raise SystemExit("no incident active")
    scenario = scenarios.REGISTRY[current["scenario"]]
    print(f"scenario:    {scenario.id}\ninjected at: {current['injected_at']}\nseed:        {current['seed']}\n")
    print(scenario.description)


def cmd_heal(args) -> None:
    current = state.load()
    if not current:
        log("no incident active; nothing to heal")
        return
    log(f"healing '{current['scenario']}'")
    scenarios.heal(make_kube(), current)
    state.clear()
    log("healed")


def cmd_list(args) -> None:
    for s in scenarios.SCENARIOS:
        print(s.id)


def cmd_down(args) -> None:
    if cluster.exists():
        cluster.delete()
    state.clear()
    kubeconfig_path().unlink(missing_ok=True)
    log("cluster deleted")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="chaoslab", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    def add(name, func, help):
        p = sub.add_parser(name, help=help)
        p.set_defaults(func=func)
        return p

    for p in (add("up", cmd_up, "create cluster, deploy, inject a random failure"),
              add("inject", cmd_inject, "inject a random (or chosen) failure")):
        p.add_argument("--scenario", default=os.environ.get("SCENARIO") or None, help="scenario id (default: random)")
        p.add_argument("--seed", type=int, default=int(os.environ["SEED"]) if os.environ.get("SEED") else None)
    sub.choices["up"].add_argument("--no-inject", action="store_true", help="deploy only")
    add("status", cmd_status, "pod health (does not reveal the scenario)")
    add("reveal", cmd_reveal, "show the injected failure")
    add("heal", cmd_heal, "undo the injected failure")
    add("list", cmd_list, "list scenario ids")
    add("down", cmd_down, "delete the cluster")

    args = parser.parse_args(argv)
    if not args.command:
        args = parser.parse_args(["up", *(argv or [])])
    args.func(args)
    return 0
