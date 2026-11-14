#!/usr/bin/env bash
#
# fetch_lineage_ota.sh — download and verify the official LineageOS 22.2
# equuleus installation ZIP that supplies the proprietary blobs.
#
# Why this source: the LineageOS wiki documents that extract-files.py accepts a
# LineageOS installation ZIP directly, and the official equuleus build is
# produced from exactly the four repositories this project pins
# (device_xiaomi_equuleus, device_xiaomi_sdm845-common, hardware_xiaomi,
# kernel_xiaomi_sdm845). See BLOB_SOURCES.md.
#
# The download is verified twice:
#   1. the SHA256 published by the download API (recorded in blob_sources.json)
#   2. the OTA's own pre-device assertion, read from the ZIP's first entry
#
# Usage:
#   scripts/fetch_lineage_ota.sh [--dest DIR] [--build DATE] [--check-only]
#
# Exit codes:
#   0 = file present and verified
#   1 = checksum or device-assertion mismatch
#   2 = usage / missing tool / download failure
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

DEST="${PROJECT_DIR}/work/ota"
BUILD="20261110"
CHECK_ONLY=0
while (($#)); do
    case "$1" in
        --dest) DEST="${2:-}"; shift 2 ;;
        --dest=*) DEST="${1#*=}"; shift ;;
        --build) BUILD="${2:-}"; shift 2 ;;
        --build=*) BUILD="${1#*=}"; shift ;;
        --check-only) CHECK_ONLY=1; shift ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "${DEST}" "${PROJECT_DIR}/logs"
LOG_FILE="${PROJECT_DIR}/logs/fetch-ota-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf '\nFATAL: %s\n' "$*" >&2; exit "${2:-2}"; }

# Published by https://download.lineageos.org/api/v2/devices/equuleus/builds
# (read 2026-11-12). Keep in sync with blob_sources.json.
expected_sha256_for() {
    case "$1" in
        20261110) echo "2ebd3d4bb7168135353c8b543bb79da4e53a1efccf32fd91c498e9fa9fe365ee" ;;
        20261103) echo "36df2643b7253df00419fc2b553bd2756f7b5cee95ea31b55ef70a277efa0d8a" ;;
        20261027) echo "7ed6cfefc572b41e32adda3c5698ec6769657d5cdf4b9aa0c3a60d69166a54d3" ;;
        *)        echo "" ;;
    esac
}

EXPECTED_SHA256="$(expected_sha256_for "${BUILD}")"
[[ -n "${EXPECTED_SHA256}" ]] \
    || die "no recorded SHA256 for build '${BUILD}'. Known: 20261110 20261103 20261027" 2

ZIP_NAME="lineage-22.2-${BUILD}-nightly-equuleus-signed.zip"
URL="https://mirrorbits.lineageos.org/full/equuleus/${BUILD}/${ZIP_NAME}"
TARGET="${DEST}/${ZIP_NAME}"

echo "LineageOS OTA fetch"
echo "  build    : ${BUILD}"
echo "  url      : ${URL}"
echo "  target   : ${TARGET}"
echo "  sha256   : ${EXPECTED_SHA256}"
echo "  log      : ${LOG_FILE}"

# ---------------------------------------------------------------- detect tools
PYTHON=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 && \
            "${cand}" -c "import sys" >/dev/null 2>&1; then
        PYTHON="${cand}"; break
    fi
done
[[ -n "${PYTHON}" ]] || die "python3/python is required to verify the OTA metadata"

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif [[ -n "${PYTHON}" ]]; then
        "${PYTHON}" - "$1" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
print(h.hexdigest())
PY
    else
        die "no sha256 tool available"
    fi
}

# ------------------------------------------------------ verify the OTA header
verify_device_assertion() {
    local zip="$1"
    "${PYTHON}" - "${zip}" <<'PY'
import struct, sys, zipfile

path = sys.argv[1]
try:
    with zipfile.ZipFile(path) as zf:
        meta = zf.read("META-INF/com/android/metadata").decode("utf-8", "replace")
except Exception as exc:                                   # noqa: BLE001
    print(f"  [FAIL] cannot read META-INF/com/android/metadata: {exc}", file=sys.stderr)
    sys.exit(1)

props = {}
for line in meta.splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        props[k.strip()] = v.strip()

dev = props.get("pre-device")
print(f"  pre-device              : {dev}")
print(f"  ota-type                : {props.get('ota-type')}")
print(f"  post-sdk-level          : {props.get('post-sdk-level')}")
print(f"  post-security-patch     : {props.get('post-security-patch-level')}")
print(f"  post-build-incremental  : {props.get('post-build-incremental')}")
if dev != "equuleus":
    print(f"  [FAIL] pre-device is {dev!r}, expected 'equuleus'", file=sys.stderr)
    sys.exit(1)
print("  [OK] OTA asserts pre-device=equuleus")
PY
}

step "existing file?"
if [[ -f "${TARGET}" ]]; then
    echo "  found ${TARGET}"
    ACTUAL="$(sha256_of "${TARGET}")"
    if [[ "${ACTUAL}" == "${EXPECTED_SHA256}" ]]; then
        echo "  [OK] sha256 matches"
        verify_device_assertion "${TARGET}" || die "device assertion failed on existing file" 1
        step "result"
        echo "OTA already present and verified: ${TARGET}"
        exit 0
    fi
    echo "  [WARN] sha256 mismatch on existing file; re-downloading"
    echo "         expected ${EXPECTED_SHA256}"
    echo "         actual   ${ACTUAL}"
    rm -f "${TARGET}"
fi

(( CHECK_ONLY )) && { step "check-only"; echo "  no file present at ${TARGET}"; exit 2; }

step "download"
command -v curl >/dev/null 2>&1 || die "curl is required"
echo "  size ~1.2 GiB; this takes a while on a slow link"
if ! curl --fail --location --show-error \
        --retry 5 --retry-delay 10 --retry-all-errors \
        --continue-at - --output "${TARGET}.part" "${URL}"; then
    die "download failed. Partial file kept at ${TARGET}.part for --continue-at -"
fi
mv -f "${TARGET}.part" "${TARGET}"

step "verify sha256"
ACTUAL="$(sha256_of "${TARGET}")"
echo "  expected ${EXPECTED_SHA256}"
echo "  actual   ${ACTUAL}"
[[ "${ACTUAL}" == "${EXPECTED_SHA256}" ]] \
    || die "SHA256 MISMATCH — do not use this file. Re-download or pick another build." 1
echo "  [OK] sha256 matches"

step "verify OTA device assertion"
verify_device_assertion "${TARGET}" || die "OTA does not assert equuleus" 1

step "result"
cat <<EOF
OTA verified and ready: ${TARGET}

Next:
  scripts/extract_blobs_from_ota.sh <synced-tree> "${TARGET}"
Then:
  python3 scripts/verify_blobs.py <synced-tree> --strict --json blob-report.json
EOF
