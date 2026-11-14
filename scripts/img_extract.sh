#!/usr/bin/env bash
#
# img_extract.sh — dump partition images to plain directories using debugfs.
#
# `debugfs -R 'rdump / <dir>'` walks the filesystem read-only; the image itself
# is never modified and no root or loop mount is required. This is the same
# mechanism extract-utils uses in extract_utils/extract.py::extract_ext4.
#
# Usage:
#   img_extract.sh <workdir> <part>[,<part>...]
#
# Each partition is dumped to <workdir>/dump/<part>/.
#
set -euo pipefail

WORKDIR="${1:-}"
PARTS="${2:-vendor,product,system_ext,system,odm}"
if [[ -z "${WORKDIR}" ]]; then
    echo "usage: $0 <workdir> [parts]" >&2
    exit 2
fi

mkdir -p "${WORKDIR}/dump"

IFS=',' read -ra LIST <<< "${PARTS}"
fail=0
for part in "${LIST[@]}"; do
    img="${WORKDIR}/${part}.img"
    out="${WORKDIR}/dump/${part}"
    if [[ ! -f "${img}" ]]; then
        echo "  [skip] ${part}: ${img} not found"
        continue
    fi
    rm -rf "${out}"
    mkdir -p "${out}"
    echo "  [${part}] dumping ${img} …"
    # rdump preserves directory structure and file modes.
    if debugfs -R "rdump / ${out}" "${img}" >"${WORKDIR}/dump_${part}.log" 2>&1; then
        n=$(find "${out}" -type f 2>/dev/null | wc -l)
        echo "         ${n} files"
    else
        echo "         FAILED (see dump_${part}.log)" >&2
        fail=$((fail + 1))
    fi
done

echo
if (( fail > 0 )); then
    echo "RESULT: ${fail} partition(s) failed to dump"
    exit 1
fi
echo "RESULT: all partitions dumped to ${WORKDIR}/dump"
