#!/usr/bin/env bash
#
# preflight.sh - DEPRECATED two-in-one wrapper, kept for backward compatibility.
#
# The checks used to live here, which conflated two questions that must be
# asked at different times:
#
#   "is this MACHINE able to build?"    -> scripts/host-preflight.sh
#   "is this SOURCE TREE complete?"     -> scripts/build-preflight.sh <tree>
#
# Usage:
#   scripts/preflight.sh                 # stage 1 only (environment)
#   scripts/preflight.sh /path/to/tree   # stage 2 (requires a synced tree)
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${1:-}" ]]; then
    echo "NOTE: 'preflight.sh <tree>' now delegates to build-preflight.sh (stage 2/2)."
    echo "      Environment checks are stage 1 and are NOT repeated here."
    echo
    exec "${SCRIPT_DIR}/build-preflight.sh" "$1"
fi

echo "NOTE: 'preflight.sh' now delegates to host-preflight.sh (stage 1/2)."
echo "      After syncing the tree, run: scripts/build-preflight.sh <tree>"
echo
exec "${SCRIPT_DIR}/host-preflight.sh"
