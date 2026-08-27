#!/bin/bash
set -euo pipefail

MARK="cloudflare-sync"
IPV4_URL="https://www.cloudflare.com/ips-v4"
MIN_RANGES=5
MAX_RANGES=60
PORTS="80,443"

mapfile -t ranges < <(curl -fsSL "$IPV4_URL" | sed '/^[[:space:]]*$/d')
count=${#ranges[@]}
if (( count < MIN_RANGES || count > MAX_RANGES )); then
  echo "abort: unexpected cloudflare ipv4 range count: ${count}" >&2
  exit 1
fi

for cidr in "${ranges[@]}"; do
  if ! [[ "$cidr" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]]; then
    echo "abort: invalid cidr: ${cidr}" >&2
    exit 1
  fi
done

while read -r num; do
  [[ -n "$num" ]] || continue
  ufw --force delete "$num" >/dev/null 2>&1 || true
done < <(ufw status numbered | grep -F "$MARK" | sed -n 's/^\[\([0-9]*\)\].*/\1/p' | sort -rn)

for cidr in "${ranges[@]}"; do
  ufw allow from "$cidr" to any port "$PORTS" proto tcp comment "$MARK"
done

echo "synced ${#ranges[@]} cloudflare ipv4 ranges for tcp ${PORTS}"
