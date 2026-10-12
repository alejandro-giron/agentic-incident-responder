#!/usr/bin/env bash
# Some docker-in-docker hosts (seen in GitHub Codespaces) carry stale
# iptables-legacy rules: FORWARD policy DROP with only docker0 allowed. Docker's
# own rules live in nftables, so traffic on user-defined bridges, which k3d
# uses, is silently dropped. Allow those bridges. Does nothing on hosts without
# the problem and is safe to run repeatedly.
set -euo pipefail
command -v iptables-legacy >/dev/null || exit 0
sudo iptables-legacy -S FORWARD 2>/dev/null | grep -q '^-P FORWARD DROP' || exit 0
for dir in -i -o; do
  if ! sudo iptables-legacy -C FORWARD "$dir" br-+ -j ACCEPT 2>/dev/null; then
    sudo iptables-legacy -I FORWARD "$dir" br-+ -j ACCEPT
    echo "iptables-legacy: allowed FORWARD $dir br-+"
  fi
done
