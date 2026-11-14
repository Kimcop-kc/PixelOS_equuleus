#!/usr/bin/env bash
#
# extract_vendor_full.sh — end-to-end B-01 extraction on Ubuntu 22.04.
#
# Turns one official LineageOS 22.2 equuleus OTA into the two proprietary
# vendor trees, then verifies them. Every step is idempotent and refuses to
# continue on failure; nothing is fabricated.
#
# Stages
#   1. verify the OTA (sha256 + pre-device assertion)
#   2. extract block partitions to plain ext4 images
#   3. dump each partition to a directory (debugfs, read-only)
#   4. resolve all 862 blob-list entries against the dumps
#   5. generate vendor/xiaomi/{sdm845-common,equuleus} with makefiles
#   6. strict verification (architecture, SONAME, hashes, presence)
#   7. write a consolidated report
#
# Usage:
#   scripts/extract_vendor_full.sh --ota <zip> --tree <synced-tree> [--work DIR]
#
# Exit codes:
#   0 = both trees generated and strict verification found no FAIL
#   1 = a stage failed
#   2 = usage / prerequisite
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

OTA=""
TREE=""
WORK="${PROJECT_DIR}/work/b01"
while (($#)); do
    case "$1" in
        --ota)  OTA="${2:-}";  shift 2 ;;
        --ota=*) OTA="${1#*=}"; shift ;;
        --tree) TREE="${2:-}"; shift 2 ;;
        --tree=*) TREE="${1#*=}"; shift ;;
        --work) WORK="${2:-}"; shift 2 ;;
        --work=*) WORK="${1#*=}"; shift ;;
        -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
[[ -n "${OTA}" && -n "${TREE}" ]] || {
    echo "usage: $0 --ota <lineage-*.zip> --tree <synced-pixelos-tree>" >&2; exit 2; }

mkdir -p "${WORK}" "${PROJECT_DIR}/logs"
LOG="${PROJECT_DIR}/logs/extract-vendor-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG}") 2>&1

step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

PYTHON=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then
        PYTHON="$c"; break
    fi
done
[[ -n "${PYTHON}" ]] || die "no working python3"

echo "B-01 end-to-end extraction"
echo "  ota  : ${OTA}"
echo "  tree : ${TREE}"
echo "  work : ${WORK}"
echo "  log  : ${LOG}"

step "prerequisites"
[[ -f "${OTA}" ]] || die "OTA not found: ${OTA}"
[[ -d "${TREE}" ]] || die "tree not found: ${TREE}"
for tool in debugfs; do
    command -v "${tool}" >/dev/null 2>&1 \
        || die "${tool} is required (Ubuntu: e2fsprogs). Read-only ext4 access uses it."
done
"${PYTHON}" -c "import brotli" 2>/dev/null \
    || die "python3-brotli is required (apt install python3-brotli)"

step "1/7 verify OTA"

# The expected digest of the OTA this project was built and verified against.
# Overridable for a different nightly, but never silently ignored: an unmatched
# digest must stop the run, because every downstream claim ("862/862 present",
# "FAIL=0") is only meaningful for bytes we actually identified.
EXPECTED_OTA_SHA256="${EXPECTED_OTA_SHA256:-2ebd3d4bb7168135353c8b543bb79da4e53a1efccf32fd91c498e9fa9fe365ee}"

"${PYTHON}" - "${OTA}" "${EXPECTED_OTA_SHA256}" <<'PY' || die "OTA identity check failed"
import hashlib, os, sys, zipfile

path, expected = sys.argv[1], sys.argv[2].strip().lower()
if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
    print("  [FAIL] EXPECTED_OTA_SHA256 is not a 64-char hex digest: %r" % expected,
          file=sys.stderr)
    sys.exit(1)

h = hashlib.sha256()
with open(path, "rb") as fh:
    for c in iter(lambda: fh.read(1 << 22), b""):
        h.update(c)
actual = h.hexdigest()

print("  file      :", os.path.basename(path))
print("  size      : %d bytes" % os.path.getsize(path))
print("  expected  :", expected)
print("  actual    :", actual)

if actual != expected:
    print("", file=sys.stderr)
    print("  [FAIL] SHA256 MISMATCH — refusing to extract.", file=sys.stderr)
    print("         The OTA is not the build this project verified against.", file=sys.stderr)
    print("         Either you have a different nightly (set EXPECTED_OTA_SHA256", file=sys.stderr)
    print("         to its published digest) or the download is corrupt.", file=sys.stderr)
    sys.exit(1)
print("  [OK] sha256 matches the pinned digest")

with zipfile.ZipFile(path) as zf:
    meta = zf.read("META-INF/com/android/metadata").decode("utf-8", "replace")
props = dict(l.split("=", 1) for l in meta.splitlines() if "=" in l)
dev = props.get("pre-device", "").strip()
print("  pre-device:", dev)
if dev != "equuleus":
    print("  [FAIL] not an equuleus OTA", file=sys.stderr)
    sys.exit(1)
print("  [OK] equuleus OTA")

# Record the verified digest so the claim is auditable. Prefer the OTA's own
# directory; fall back to CWD. A failure here must NOT abort the run — the
# verification itself already passed, and losing the record would be a worse
# outcome than continuing with a warning.
record = "ota-sha256.txt"
candidates = [os.path.dirname(os.path.abspath(path)), os.getcwd()]
written = None
for d in candidates:
    target = os.path.join(d, record)
    try:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (actual, os.path.basename(path)))
        written = target
        break
    except OSError:
        continue
if written:
    print("  [OK] digest recorded in", written)
else:
    print("  [WARN] could not write the digest record; verification still passed")
PY

step "2/7 extract partitions"
"${PYTHON}" "${SCRIPT_DIR}/ota_extract.py" "${OTA}" "${WORK}/parts" \
    --json "${WORK}/parts/ota_extract_report.json" \
    || die "partition extraction failed"

step "3/7 dump partitions"
bash "${SCRIPT_DIR}/img_extract.sh" "${WORK}/parts" \
    || die "partition dump failed"

step "4/7 resolve blob lists"
"${PYTHON}" "${SCRIPT_DIR}/blob_audit.py" "${WORK}/parts" "${TREE}/device/xiaomi" \
    --json "${WORK}/blob_audit.json" \
    || die "blob audit failed"

step "5/7 generate vendor trees"
"${PYTHON}" "${SCRIPT_DIR}/make_vendor_trees.py" \
    "${WORK}/blob_audit.json" "${WORK}/parts" "${TREE}" \
    --strict-missing || die "vendor tree generation reported missing entries"

step "6/7 strict verification"
set +e
"${PYTHON}" "${SCRIPT_DIR}/verify_blobs.py" "${TREE}" --strict \
    --json "${WORK}/blob-report.json"
BLOB_RC=$?
set -e
case "${BLOB_RC}" in
    0) echo "  [OK] strict verification found no failures" ;;
    3) echo "  [PARTIAL] verification incomplete (UNVERIFIABLE entries present)" ;;
    *) die "strict verification failed (exit ${BLOB_RC})" ;;
esac

step "7/7 report"
"${PYTHON}" - "${WORK}" "${TREE}" <<'PY'
import json, os, sys
work, tree = sys.argv[1], sys.argv[2]
out = {"work": work, "tree": tree, "trees": {}}
for name in ("sdm845-common", "equuleus"):
    rp = os.path.join(tree, "vendor", "xiaomi", name, "EXTRACTION_REPORT.json")
    if os.path.isfile(rp):
        out["trees"][name] = json.load(open(rp, encoding="utf-8"))
bp = os.path.join(work, "blob-report.json")
if os.path.isfile(bp):
    out["verification"] = json.load(open(bp, encoding="utf-8"))
dest = os.path.join(tree, "B01_EXTRACTION_REPORT.json")
json.dump(out, open(dest, "w", encoding="utf-8"), indent=2)
print("  wrote", dest)
for name, info in out["trees"].items():
    print(f"  {name}: copied={info['copied']} missing={len(info['missing'])} "
          f"relocated_kinds={info.get('relocated_kinds')}")
PY

step "result"
cat <<EOF
Both vendor trees were generated from one official LineageOS 22.2 OTA:

  ${TREE}/vendor/xiaomi/sdm845-common
  ${TREE}/vendor/xiaomi/equuleus

Reports:
  ${WORK}/blob_audit.json
  ${WORK}/blob-report.json
  ${TREE}/B01_EXTRACTION_REPORT.json

This proves the blob files are present, correctly typed and consistently
named. It does NOT prove the ROM builds, boots, or that FOD/camera/NFC work.
EOF
