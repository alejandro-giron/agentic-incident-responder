# Agentic Incident Responder: Chaos Lab

Practise incident response against Google's [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo)
(v0.10.7, prebuilt images). One container starts a local Kubernetes cluster (k3d), deploys the shop, waits for it
to be healthy, and then injects a **hidden** random failure for you, or later an SRE agent, to find.

## Requirements
The easiest setup is the dev container in `.devcontainer/`: open the repo in GitHub Codespaces or with VS Code
"Reopen in Container". It includes Docker, kubectl, Python, pytest and Claude Code, sets `KUBECONFIG` to
`.chaos/kubeconfig`, and applies the networking fix from Troubleshooting automatically.

Otherwise you need Linux with Docker. The pods request about 1.6 CPU and 1.3 GiB of memory in total; 4 CPUs is plenty.

## Run a drill
```sh
make up                                   # build image, create cluster, deploy, warm up 60s, inject
export KUBECONFIG=$PWD/.chaos/kubeconfig
kubectl get pods                          # investigate: logs, describe, events, top, rollout history…
open http://localhost:8080                # the storefront
make reveal                               # see the answer
make heal                                 # undo it
make inject                               # next drill (or: make inject SCENARIO=redis-down SEED=…)
make down                                 # delete the cluster
```
`make up` is a wrapper around:
```sh
docker run --rm --network host --user $(id -u):$(id -g) --group-add $(stat -c %g /var/run/docker.sock) \
  -v /var/run/docker.sock:/var/run/docker.sock -v $PWD/.chaos:/state chaos-lab up
```
The image drives the host Docker daemon, so the k3d cluster runs as sibling containers and stays up after the
command exits. Other commands: `make deploy` (healthy cluster, no incident), `make status`, `make list`.

## Scenarios
Run `make list` to see them all. Each one is a realistic misconfiguration made through kubectl: a bad image tag,
bad env, a resource limit, a scale-down, a NetworkPolicy, or a broken probe. Investigators can find it with
ordinary tooling (`kubectl describe`, `kubectl rollout history`, logs). The answer, plus a snapshot used for an
exact heal, is stored in `.chaos/state.json` **outside** the cluster. Add new scenarios in `chaoslab/scenarios.py`.

When an SRE agent is the investigator, give it `.chaos/kubeconfig` only, never the `.chaos/` directory, because
`state.json` holds the answer. Later, score the agent's diagnosis against `make reveal`.

## Development
```sh
make test    # unit tests (fake kubectl)
make e2e     # every scenario against a real cluster: inject → symptom → heal → healthy
```

## Troubleshooting
**API server times out / pods stuck pulling `rancher/mirrored-pause`.** Containers on user-defined Docker
networks can't reach each other or the internet. On some hosts (seen in GitHub Codespaces with docker-in-docker),
stale `iptables-legacy` rules set `FORWARD` policy to DROP and only allow `docker0`. Check with
`sudo iptables-legacy -S FORWARD`. The dev container fixes this on every start with
`.devcontainer/fix-docker-forwarding.sh`. To fix it by hand, allow Docker's user bridges:
```sh
sudo iptables-legacy -I FORWARD -i br-+ -j ACCEPT
sudo iptables-legacy -I FORWARD -o br-+ -j ACCEPT
```
