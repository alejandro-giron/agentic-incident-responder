FROM python:3.12-slim

ARG TARGETARCH=amd64
ARG KUBECTL_VERSION=v1.37.0
ARG K3D_VERSION=v5.9.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
 && echo "$(curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256")  /usr/local/bin/kubectl" | sha256sum -c - \
 && curl -fsSLo /usr/local/bin/k3d "https://github.com/k3d-io/k3d/releases/download/${K3D_VERSION}/k3d-linux-${TARGETARCH}" \
 && curl -fsSL "https://github.com/k3d-io/k3d/releases/download/${K3D_VERSION}/checksums.txt" \
    | awk -v f="_dist/k3d-linux-${TARGETARCH}" '$2 == f {print $1"  /usr/local/bin/k3d"}' | sha256sum -c - \
 && chmod +x /usr/local/bin/kubectl /usr/local/bin/k3d

WORKDIR /app
COPY manifests ./manifests
COPY chaoslab ./chaoslab

# Run as the host user (see Makefile) so files in the state volume aren't root-owned;
# HOME must be writable for k3d/kubectl caches.
ENV HOME=/tmp CHAOS_STATE_DIR=/state PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "chaoslab"]
CMD ["up"]
