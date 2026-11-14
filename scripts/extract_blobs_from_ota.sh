#!/usr/bin/env bash
#
# extract_blobs_from_ota.sh — generate both proprietary vendor trees from one
# LineageOS 22.2 equuleus installation ZIP.
#
# This implements the route documented by the LineageOS wiki
# (extracting_blobs_from_zips): `extract-files.py` accepts a LineageOS OTA ZIP
# directly. One official build therefore supplies both trees, because that build
# was produced from the same four repositories this project pins.
#
# Order is mandatory: sdm845-common first, then equuleus, because
# equuleus/extract-files.py calls
#     ExtractUtils.device_with_common(module, 'sdm845-common', module.vendor)
#
# Usage:
#   scripts/extract_blobs_from_ota.sh <synced-tree> <lineage-ota.zip> [--jobs N]
#
# Exit codes:
#   0 = both trees generated AND strict verification passed
#   1 = extraction or verification problem (details printed)
#   2 = usage / missing prerequisite
#   3 = extraction succeeded but the blob set is incomplete (missing list printed)
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TREE="${1:-}"
OTA="${2:-}"
if [[ -z "${TREE}" || -z "${OTA}" ]]; then
    echo "usage: $0 <synced-tree> <lineage-ota.zip>" >&2
    exit 2
fi

mkdir -p "${PROJECT_DIR}/logs"
LOG_FILE="${PROJECT_DIR}/logs/extract-blobs-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf '\nFATAL: %s\n' "$*" >&2; exit "${2:-2}"; }

PYTHON=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 && \
            "${cand}" -c "import sys" >/dev/null 2>&1; then
        PYTHON="${cand}"; break
    fi
done
[[ -n "${PYTHON}" ]] || die "python3/python is required"

echo "Proprietary blob extraction from a LineageOS OTA"
echo "  tree : ${TREE}"
echo "  ota  : ${OTA}"
echo "  log  : ${LOG_FILE}"

# --------------------------------------------------------- 1. preconditions
step "preconditions"
[[ -d "${TREE}" ]] || die "tree does not exist: ${TREE}"
TREE="$(cd -- "${TREE}" && pwd)"
[[ -f "${OTA}" ]] || die "OTA not found: ${OTA}"

[[ -f "${TREE}/build/envsetup.sh" ]] \
    || die "no build/envsetup.sh in ${TREE}; extract-utils needs a synced tree"
[[ -d "${TREE}/tools/extract-utils/extract_utils" ]] \
    || die "tools/extract-utils is missing; it is required by extract-files.py"

for devdir in device/xiaomi/sdm845-common device/xiaomi/equuleus; do
    [[ -f "${TREE}/${devdir}/extract-files.py" ]] \
        || die "${devdir}/extract-files.py is missing; is this the right tree?"
done

# Refuse to run on a tree whose device dirs are the wrong revision: the blob
# lists and the fixups are coupled to a specific commit.
if ! git -C "${TREE}/device/xiaomi/sdm845-common" rev-parse HEAD >/dev/null 2>&1; then
    echo "  [WARN] ${TREE}/device/xiaomi/sdm845-common is not a git checkout;"
    echo "         cannot confirm the pinned revision. Continuing anyway."
fi

# -------------------------------------------------- 2. confirm the OTA identity
step "confirm OTA identity"
"${PYTHON}" - "${OTA}" <<'PY' || die "OTA metadata check failed" 1
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    meta = zf.read("META-INF/com/android/metadata").decode("utf-8", "replace")
props = dict(l.split("=", 1) for l in meta.splitlines() if "=" in l)
dev = props.get("pre-device", "").strip()
print(f"  pre-device = {dev}")
if dev != "equuleus":
    print(f"  [FAIL] expected equuleus", file=sys.stderr)
    sys.exit(1)
print("  [OK] this OTA is for equuleus")
PY

# ------------------------------------------------------ 3. sdm845-common first
step "extract sdm845-common (must run before equuleus)"
cd -- "${TREE}/device/xiaomi/sdm845-common"
# extract-files.py reads the OTA itself; no manual unzip is needed.
if ! "${PYTHON}" ./extract-files.py "${OTA}"; then
    die "sdm845-common extraction failed. Common causes:
  * the OTA layout is not what extract-utils expects (inspect ${LOG_FILE})
  * a blob the list needs is absent from this build (see BLOB_SOURCES.md §6)
Nothing was fabricated; re-run after reviewing the log." 1
fi
echo "  sdm845-common extraction reported success"

# ------------------------------------------------------------- 4. then equuleus
step "extract equuleus (depends on the common tree)"
cd -- "${TREE}/device/xiaomi/equuleus"
if ! "${PYTHON}" ./extract-files.py "${OTA}"; then
    die "equuleus extraction failed; see ${LOG_FILE}" 1
fi
echo "  equuleus extraction reported success"

# --------------------------------------------------- 5. regenerate makefiles
step "regenerate makefiles (setup-makefiles.py)"
cd -- "${TREE}/device/xiaomi/sdm845-common"
"${PYTHON}" ./setup-makefiles.py || echo "  [WARN] sdm845-common setup-makefiles.py failed"
cd -- "${TREE}/device/xiaomi/equuleus"
"${PYTHON}" ./setup-makefiles.py || echo "  [WARN] equuleus setup-makefiles.py failed"

# ------------------------------------------------------ 6. strict verification
step "strict blob verification"
REPORT="${TREE}/blob-report.json"
set +e
"${PYTHON}" "${SCRIPT_DIR}/verify_blobs.py" "${TREE}" --strict --json "${REPORT}"
BLOB_RC=$?
set -e

case "${BLOB_RC}" in
    0) echo "  [OK] every declared entry present and every declared property verified" ;;
    1) echo "  [FAIL] verify_blobs.py found defects (missing / wrong SONAME / hash mismatch)"
       echo "         report: ${REPORT}"
       exit 1 ;;
    3) echo "  [INCOMPLETE] entries present but some pins could not be verified"
       echo "               report: ${REPORT}"
       exit 3 ;;
    *) echo "  [ERROR] verify_blobs.py exited ${BLOB_RC}"
       exit 1 ;;
esac

# -------------------------------------------------- 7. summarise what is missing
step "missing / needs-other-source summary"
"${PYTHON}" - "${REPORT}" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:                                   # noqa: BLE001
    print(f"  cannot read report: {exc}")
    sys.exit(0)
for label, info in data.get("devices", {}).items():
    missing = info.get("missing") or []
    print(f"  {label}: {info.get('present')}/{info.get('total')} present, "
          f"{len(missing)} missing")
    for m in missing[:40]:
        print(f"    MISSING  {m['src']}")
        if m.get("src") != m.get("dst"):
            print(f"             (would install at {m['dst']})")
    if len(missing) > 40:
        print(f"    ... and {len(missing) - 40} more (see report)")
    if not missing:
        print("    nothing missing from this source")
PY

step "result"
cat <<EOF
Both vendor trees were generated from ONE official LineageOS 22.2 OTA:

  ${TREE}/vendor/xiaomi/sdm845-common
  ${TREE}/vendor/xiaomi/equuleus

Report: ${REPORT}

This does NOT mean the ROM builds, boots, or that FOD/camera/NFC work.
No proprietary file was fabricated: anything absent is listed above and in the
report, and must come from a documented second source (BLOB_SOURCES.md section 6).
EOF
