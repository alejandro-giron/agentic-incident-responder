IMAGE ?= chaos-lab
STATE ?= $(CURDIR)/.chaos
SOCK  ?= /var/run/docker.sock

# Sibling-container pattern: the image drives the host Docker daemon to run a
# k3d cluster. --network host lets it reach the API server on 127.0.0.1:6550.
# SCENARIO / SEED / CHAOS_WARMUP pass through when set (e.g. `make inject SCENARIO=redis-down`).
RUN = mkdir -p $(STATE) && docker run --rm --network host \
	--user $$(id -u):$$(id -g) --group-add $$(stat -c %g $(SOCK)) \
	-v $(SOCK):/var/run/docker.sock -v $(STATE):/state \
	-e SCENARIO -e SEED -e CHAOS_WARMUP \
	$(IMAGE)

.PHONY: build up deploy inject status reveal heal list down test e2e

build:
	docker build -t $(IMAGE) .

up: build
	$(RUN) up

deploy: build  ## healthy cluster, no incident
	$(RUN) up --no-inject

inject status reveal heal list down:
	$(RUN) $@

test:
	python -m pytest -q tests

e2e: build
	scripts/e2e.sh
