#!/usr/bin/env bash
#
# build.sh — build PixelOS fifteen for Xiaomi Mi 8 Pro (equuleus).
#
# Honest scope: this script has NEVER been run to completion against a real
# PixelOS fifteen tree with real proprietary blobs. It is written to fail
# loudly rather than silently, and it refuses to report success unless a
# ROM zip and a recovery image both actually exist afterwards.
#
# Usage:
#   scripts/build.sh /path/to/pixelos15 [user|userdebug|eng] [--clean]
#
# Exit codes:
#   0 = both artifacts exist and were hashed
#   1 = a precondition failed (nothing was attempted)
#   2 = the build itself failed (see the log)
#   3 = build exited 0 but an expected artifact is missing
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TREE="${1:-}"
VARIANT="${2:-userdebug}"
CLEAN=""
for arg in "$@"; do
    [[ "${arg}" == "--clean" ]] && CLEAN="clean"
done

if [[ -z "${TREE}" ]]; then
    echo "usage: $0 /path/to/pixelos15 [user|userdebug|eng] [--clean]" >&2
    exit 1
fi

case "${VARIANT}" in
    user|userdebug|eng) : ;;
    *) echo "variant must be user, userdebug or eng (got '${VARIANT}')" >&2; exit 1 ;;
esac

# aosp_target_release for PixelOS fifteen is bp1a (vendor/aosp/vars/aosp_target_release).
LUNCH_TARGET="aosp_equuleus-bp1a-${VARIANT}"
DEVICE="equuleus"

mkdir -p "${PROJECT_DIR}/logs"
LOG_FILE="${PROJECT_DIR}/logs/build-${VARIANT}-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

step() { printf '\n=== %s ===\n' "$*"; }
die()  { local rc="$1"; shift; printf '\nFATAL: %s\n' "$*" >&2; exit "${rc}"; }

step "preconditions"
[[ -d "${TREE}" ]] || die 1 "tree does not exist: ${TREE}"
TREE="$(cd -- "${TREE}" && pwd)"
[[ -f "${TREE}/build/envsetup.sh" ]] || die 1 "no build/envsetup.sh in ${TREE}"
[[ -f "${TREE}/vendor/aosp/config/common_full_phone.mk" ]] \
    || die 1 "no vendor/aosp product config: this is not a PixelOS fifteen tree"
[[ -d "${TREE}/device/xiaomi/equuleus" ]] || die 1 "device/xiaomi/equuleus is missing"
[[ -d "${TREE}/device/xiaomi/sdm845-common" ]] || die 1 "device/xiaomi/sdm845-common is missing"
[[ -d "${TREE}/kernel/xiaomi/sdm845" ]] || die 1 "kernel/xiaomi/sdm845 is missing"

# GMS is an unconditional dependency: vendor/aosp/config/common.mk line 5
# inherits vendor/gms/products/gms.mk, and aosp_equuleus reaches common.mk
# through common_full_phone.mk -> common_mobile_full.mk -> common_mobile.mk.
[[ -f "${TREE}/vendor/gms/products/gms.mk" ]] \
    || die 1 "vendor/gms/products/gms.mk is missing. vendor/aosp/config/common.mk
inherits it unconditionally, so aosp_equuleus cannot be configured without it.
The ONLY supported fix is the local manifest: confirm that
.repo/local_manifests/equuleus.xml was installed BEFORE repo sync and that it
repoints vendor/gms to vendor_gms-15. Do NOT apply patches/0005-manifest-gms-repo.patch
inside a normal build: it is an archived alternative and conflicts with the local
manifest (git-repo raises ManifestParseError)."""

# The single most common silent failure: blobs missing -> mystery link errors.
for vendor_tree in vendor/xiaomi/equuleus vendor/xiaomi/sdm845-common; do
    [[ -d "${TREE}/${vendor_tree}" ]] \
        || die 1 "${vendor_tree} is missing. Generate it with BLOB_EXTRACTION.md first; \
a build without it cannot produce a flashable ROM and must not be reported as success."
    [[ -f "${TREE}/${vendor_tree}/BoardConfigVendor.mk" ]] \
        || die 1 "${vendor_tree}/BoardConfigVendor.mk is missing (incomplete extraction)"
done

# The device tree must actually be the patched one.
grep -q 'PRODUCT_NAME := aosp_equuleus' "${TREE}/device/xiaomi/equuleus/aosp_equuleus.mk" \
    || die 1 "device/xiaomi/equuleus is not patched (aosp_equuleus.mk missing or stale). Run sync.sh."
grep -q 'vendor/aosp/config/BoardConfigReservedSize.mk' \
    "${TREE}/device/xiaomi/sdm845-common/BoardConfigCommon.mk" \
    || die 1 "sdm845-common is not patched (still references vendor/lineage)"

step "stage-1 host preflight"
# Require the file to EXIST and invoke it via `bash`. Testing -x would silently
# skip the gate when the tree was unpacked from a ZIP created on Windows, where
# the Unix execute bit is not preserved.
[[ -f "${SCRIPT_DIR}/host-preflight.sh" ]] \
    || die 1 "scripts/host-preflight.sh is missing; cannot verify the host before building"
if ! bash "${SCRIPT_DIR}/host-preflight.sh" --tree "${TREE}"; then
    die 1 "host-preflight.sh reported an unsuitable host; not building"
fi

step "stage-2 dependency preflight"
[[ -f "${SCRIPT_DIR}/build-preflight.sh" ]] \
    || die 1 "scripts/build-preflight.sh is missing; cannot verify build inputs"
if ! bash "${SCRIPT_DIR}/build-preflight.sh" "${TREE}"; then
    die 1 "build-preflight.sh reported missing or mismatched inputs; not building"
fi

step "blob tree verification"
PY_BIN=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 && "${cand}" -c "import sys" >/dev/null 2>&1; then
        PY_BIN="${cand}"; break
    fi
done
# Proprietary blobs are this project's highest-risk blocker (B-01). Skipping
# their verification is not a degraded-but-acceptable outcome; it means the
# build would be attempted against an unverified blob tree. Fail instead.
[[ -n "${PY_BIN}" ]] || die 1 "no Python interpreter available for verify_blobs.py; refusing to build unverified blobs"
[[ -f "${SCRIPT_DIR}/verify_blobs.py" ]] \
    || die 1 "scripts/verify_blobs.py is missing; refusing to build unverified blobs"
# --strict makes UNVERIFIABLE a failure too: a pinned property that cannot be
# checked is not a pass.
#
# NOTE: under `set -e` a bare non-zero exit terminates the script before $? is
# read, so the status must be captured inside an if/elif chain. Reading
# `BLOB_RC=$?` after a bare call would be unreachable code.
if "${PY_BIN}" "${SCRIPT_DIR}/verify_blobs.py" "${TREE}" --strict; then
    echo "  [OK] blob tree verified (every declared property confirmed)"
else
    BLOB_RC=$?
    case "${BLOB_RC}" in
        1) die 1 "verify_blobs.py FAILED: missing files, wrong SONAME, or hash mismatch; not building" ;;
        3) die 1 "verify_blobs.py UNVERIFIABLE: a declared hash or SONAME could not be confirmed; not building" ;;
        2) die 1 "verify_blobs.py could not run (usage/tree error); not building" ;;
        *) die 1 "verify_blobs.py exited ${BLOB_RC}; not building" ;;
    esac
fi

step "IR face unlock static acceptance"
# Runs before the expensive part of the build so a missing camera id, a missing
# aux allow-list entry or a missing OV9282 sensor stops us in seconds rather than
# after a four-hour compile plus a flash.
#
# SCOPE: this is a STATIC check. It confirms the configuration exists and is
# self-consistent. It does NOT confirm the camera id is correct on hardware --
# camera_id=5 remains NOT VERIFIED ON DEVICE, and this script must not be read as
# claiming otherwise.
[[ -f "${SCRIPT_DIR}/verify_ir_face_unlock.py" ]] \
    || die 1 "scripts/verify_ir_face_unlock.py is missing; cannot gate IR face unlock"
if "${PY_BIN}" "${SCRIPT_DIR}/verify_ir_face_unlock.py" --root "${TREE}"; then
    echo "  [OK] IR configuration verified statically"
    echo "  [NOTE] camera id NOT VERIFIED ON DEVICE; see TEST_REPORT.md section 12"
else
    die 1 "IR face unlock static acceptance FAILED (camera_id / aux allow-list /
OV9282 driver / ParanoidSense dependency). Not building: a build that silently
falls back to the RGB front camera would look fine in daylight and fail in the
dark."
fi

step "resource check"
FREE_GIB="$(df -Pk "${TREE}" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
echo "free space: ${FREE_GIB} GiB"
(( FREE_GIB >= 100 )) || die 1 "need at least 100 GiB free to build, have ${FREE_GIB} GiB"

step "environment"
echo "tree    : ${TREE}"
echo "lunch   : ${LUNCH_TARGET}"
echo "variant : ${VARIANT}"
echo "log     : ${LOG_FILE}"

cd -- "${TREE}"

if [[ -n "${CLEAN}" ]]; then
    step "clean"
    # shellcheck disable=SC1091
    set +u
    . build/envsetup.sh
    set -u
    lunch "${LUNCH_TARGET}"
    m clean
    echo "clean finished"
fi

step "envsetup + lunch"
set +u   # envsetup.sh and lunch are not nounset-safe upstream
. build/envsetup.sh
lunch "${LUNCH_TARGET}" || die 1 "lunch ${LUNCH_TARGET} failed (product not defined?)"
set -u

step "build (mka bacon)"
# Recorded before the build so artifact freshness can be judged afterwards.
BUILD_STARTED_EPOCH="$(date +%s)"
export BUILD_STARTED_EPOCH
echo "build started at epoch ${BUILD_STARTED_EPOCH}"
echo "job count: $(nproc)"
if ! mka bacon -j"$(nproc)"; then
    die 2 "build failed; inspect ${LOG_FILE}"
fi

step "verify artifacts"

# The build start time is captured BEFORE mka runs, so "is this artifact newer
# than the build started?" is answerable below. Without this, a leftover zip
# from a previous attempt would be reported as this run's output.
PRODUCT_OUT="${TREE}/out/target/product/${DEVICE}"
[[ -d "${PRODUCT_OUT}" ]] || die 3 "out/target/product/${DEVICE} does not exist"

BUILD_STARTED_EPOCH="${BUILD_STARTED_EPOCH:-0}"
if (( BUILD_STARTED_EPOCH == 0 )); then
    die 3 "internal error: BUILD_STARTED_EPOCH was not set before the build;
cannot distinguish this run's artifacts from stale ones."
fi

# ---- 1. find candidate artifacts, newest first (by mtime, not by name) ----
mapfile -t ROM_ZIPS < <(
    find "${PRODUCT_OUT}" -maxdepth 1 -name 'PixelOS_*.zip' -type f \
        -newermt "@${BUILD_STARTED_EPOCH}" -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | cut -d' ' -f2-
)
if (( ${#ROM_ZIPS[@]} == 0 )); then
    echo "  no PixelOS_*.zip newer than the build start time."
    echo "  Files present in ${PRODUCT_OUT}:"
    find "${PRODUCT_OUT}" -maxdepth 1 -name 'PixelOS_*.zip' -type f 2>/dev/null \
        | sed 's/^/    /' || true
    die 3 "the ROM zip in out/ is STALE (predates this build). Refusing to report it as a result."
fi

ROM_ZIP="${ROM_ZIPS[0]}"
RECOVERY_IMG="${PRODUCT_OUT}/recovery.img"

echo "artifacts from this run:"
printf '  %-58s %s bytes\n' "$(basename "${ROM_ZIP}")" "$(stat -c '%s' "${ROM_ZIP}")"

# ---- 2. the recovery image must also be fresh --------------------------
# ONE criterion only: the build start marker. An earlier version also compared
# against build/envsetup.sh in an AND, which let a stale recovery through
# whenever it happened to be newer than envsetup.sh (i.e. almost always).
[[ -f "${RECOVERY_IMG}" ]] \
    || die 3 "recovery.img is missing; an OTA zip alone is not a complete build"
RECOVERY_MTIME="$(stat -c '%Y' "${RECOVERY_IMG}")" \
    || die 3 "cannot stat ${RECOVERY_IMG}"
if (( RECOVERY_MTIME < BUILD_STARTED_EPOCH )); then
    die 3 "recovery.img is STALE: mtime ${RECOVERY_MTIME} predates this build \
(start ${BUILD_STARTED_EPOCH}). Refusing to report success."
fi

# ---- 3. the zip must be a structurally valid archive -------------------
if ! unzip -tqq "${ROM_ZIP}" >/dev/null 2>&1; then
    die 3 "$(basename "${ROM_ZIP}") fails 'unzip -t': the archive is corrupt."
fi
echo "  [OK] unzip -t: archive is structurally valid"

# ---- 4. the device assertion is MANDATORY and must be EXACT -----------
# A zip asserting the wrong codename would flash another sdm845 device
# (dipper/ursa/perseus share this tree). Substring matching is not acceptable:
#   grep -qE 'assert.*equuleus'   also matches   assert(... == "not_equuleus")
# so every assertion is parsed and compared for equality.
EXPECTED_DEVICE="equuleus"

# 4a. PixelOS 15 writes META-INF/com/android/metadata; require it.
META="$(unzip -p "${ROM_ZIP}" META-INF/com/android/metadata 2>/dev/null || true)"
if [[ -z "${META}" ]]; then
    die 3 "META-INF/com/android/metadata is missing from $(basename "${ROM_ZIP}").
A PixelOS 15 OTA must carry it. Refusing to infer the device from a legacy
assertion alone."
fi

META_DEVICE="$(printf '%s\n' "${META}" | sed -n 's/^pre-device=//p' | head -1)"
[[ -n "${META_DEVICE}" ]] \
    || die 3 "META-INF/com/android/metadata has no pre-device line. Refusing to report success."
if [[ "${META_DEVICE}" != "${EXPECTED_DEVICE}" ]]; then
    die 3 "OTA metadata declares pre-device='${META_DEVICE}', expected '${EXPECTED_DEVICE}'.
Refusing to report success."
fi
echo "  [OK] META-INF/com/android/metadata pre-device == ${EXPECTED_DEVICE}"

# 4b. If a legacy updater-script is also present, every device literal it
#     asserts must be exactly the expected codename. Extra assertions about
#     other properties are ignored; device assertions are not.
US="$(unzip -p "${ROM_ZIP}" META-INF/com/google/android/updater-script 2>/dev/null || true)"
if [[ -n "${US}" ]]; then
    # Collect every double-quoted or single-quoted literal that appears inside
    # a getprop(...ro.product.device...) == "..." comparison.
    DEV_LITERALS="$(printf '%s\n' "${US}" \
        | grep -oE 'getprop\([[:space:]]*["'\'']ro\.product\.(device|product)[[:space:]]*["'\'']\)[[:space:]]*==[[:space:]]*["'\''][^"'\'']*["'\'']' \
        | sed -E 's/.*==[[:space:]]*["'\'']([^"'\'']*)["'\''].*/\1/' || true)"
    if [[ -z "${DEV_LITERALS}" ]]; then
        # No structured device comparison found. Fall back to a strict literal
        # scan: any quoted token immediately compared against a device prop.
        DEV_LITERALS="$(printf '%s\n' "${US}" \
            | grep -oE 'ro\.product\.(device|product)[^=]*==[[:space:]]*["'\''][^"'\'']*["'\'']' \
            | sed -E 's/.*["'\'']([^"'\'']*)["'\'']$/\1/' || true)"
    fi
    if [[ -n "${DEV_LITERALS}" ]]; then
        while IFS= read -r lit; do
            [[ -z "${lit}" ]] && continue
            if [[ "${lit}" != "${EXPECTED_DEVICE}" ]]; then
                die 3 "legacy updater-script asserts device '${lit}', expected '${EXPECTED_DEVICE}'.
Refusing to report success."
            fi
        done <<< "${DEV_LITERALS}"
        echo "  [OK] legacy updater-script device assertions are all '${EXPECTED_DEVICE}'"
    else
        # An updater-script with no recognisable device assertion is not proof
        # of anything; we already have metadata, so record the gap.
        echo "  [INFO] updater-script present but carries no parseable device assertion"
    fi
fi

# ---- 5. record provenance and hashes ----------------------------------
sha256sum "${ROM_ZIP}"      | tee -a "${PRODUCT_OUT}/ARTIFACTS.sha256"
sha256sum "${RECOVERY_IMG}" | tee -a "${PRODUCT_OUT}/ARTIFACTS.sha256"

{
    echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "build_started_epoch=${BUILD_STARTED_EPOCH}"
    echo "lunch=${LUNCH_TARGET}"
    echo "rom_zip=$(basename "${ROM_ZIP}")"
    echo "rom_zip_mtime=$(date -u -d "@$(stat -c '%Y' "${ROM_ZIP}")" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || stat -c '%y' "${ROM_ZIP}")"
    for path in device/xiaomi/equuleus device/xiaomi/sdm845-common \
                kernel/xiaomi/sdm845 hardware/xiaomi; do
        echo "repo:${path}=$(git -C "${TREE}/${path}" rev-parse HEAD 2>/dev/null || echo unknown)"
    done
} | tee "${PRODUCT_OUT}/BUILD_PROVENANCE.txt"

step "result"

# Reaching here means every artifact gate above passed:
#   * the ROM zip is newer than this build's start time (not a leftover),
#   * recovery.img is present and not stale,
#   * the zip passes `unzip -t`,
#   * the OTA asserts device == equuleus.
# Each of those used to be a warning or was not checked at all.
cat <<'EOF'
Build produced a ROM zip and a recovery image, both created by THIS run, with a
verified archive and an equuleus device assertion.

THIS IS STILL NOT PROOF THE ROM WORKS. Compiling is not booting, and booting is
not working hardware. Do not flash a daily-driver phone with an unvalidated
build; review KNOWN_BLOCKERS.md and CLOUD_READINESS.md first.
EOF
echo "log: ${LOG_FILE}"
exit 0
