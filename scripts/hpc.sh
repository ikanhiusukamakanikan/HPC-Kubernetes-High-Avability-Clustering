#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
exec python3 "$ROOT/scripts/hpc.py" "$@"
