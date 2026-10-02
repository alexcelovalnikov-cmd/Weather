#!/bin/bash
set -euo pipefail
export GH_TOKEN="$(cat "$CREDENTIALS_DIRECTORY/github-token")"
exec /usr/bin/python3 -m hybrid.broker \
 --config /opt/ci-coordinator/config.json \
 --state /opt/ci-coordinator/state/broker.sqlite \
 --health /opt/ci-coordinator/health
