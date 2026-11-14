#!/usr/bin/env bash
#
# build-preflight.sh — Stage 2 of 2. SOURCE + BLOB DEPENDENCIES ONLY.
#
# Runs AFTER: repo init/sync, patch application, and proprietary blob
# extraction. It does not re-check CPU/RAM/disk (stage 1 owns those) except for
# a minimal free-space guard for out/.
#
# Answers: "is this tree complete and correctly pinned enough that a build
# would fail for *source* reasons rather than *missing input* reasons?"
#
# Usage:
#   scripts/build-preflight.sh /path/to/pixelos15
#
# Exit codes: 0 = all required inputs present, 1 = at least one FAIL.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TREE="${1:-}"
if [[ -z "${TREE}" ]]; then
    echo "usage: $0 /path/to/pixelos15" >&2
    exit 2
fi
if [[ ! -d "${TREE}" ]]; then
    echo "FATAL: tree does not exist: ${TREE}" >&2
    exit 2
fi
TREE="$(cd -- "${TREE}" && pwd)"

LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/build-preflight-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

FAILURES=0
WARNINGS=0
pass() { printf '[PASS] %s\n' "$*"; }
info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

PYTHON=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 && "${cand}" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        PYTHON="${cand}"; break
    fi
done

echo "=============================================================="
echo " STAGE 2/2  build-preflight  (sources + blobs)"
echo " tree : ${TREE}"
echo " log  : ${LOG_FILE}"
echo "=============================================================="

# ------------------------------------------------------- 1. tree skeleton
echo
echo "--- 1. source tree skeleton ---------------------------------------------"
for must in build/envsetup.sh build/make/core/main.mk \
            vendor/aosp/config/common_full_phone.mk \
            vendor/aosp/config/common.mk; do
    if [[ -f "${TREE}/${must}" ]]; then
        pass "present: ${must}"
    else
        fail "MISSING: ${must} (tree is not a PixelOS fifteen checkout)"
    fi
done

if [[ -d "${TREE}/.repo" ]]; then
    # Verify it is a *working* repo client, not just a leftover directory.
    if git --git-dir="${TREE}/.repo/manifests.git" rev-parse HEAD >/dev/null 2>&1; then
        pass ".repo exists and manifests.git has a valid HEAD"
    else
        fail ".repo exists but .repo/manifests.git has no valid HEAD (broken client)"
    fi
else
    fail ".repo missing — this is not a repo-managed tree; sync.sh owns this"
fi

# ------------------------------------------------------- 2. device projects
echo
echo "--- 2. device-side projects at pinned commits ---------------------------"
# name|path|expected-sha  (from .repo/local_manifests/equuleus.xml and UPSTREAM_LOCK.md)
check_repo() {
    local path="$1" want="$2" got inside
    # Do NOT test `-d path/.git`. git-repo may lay out a project's metadata as
    # a DIRECTORY (.git/), a FILE (.git containing "gitdir: ..."), or a
    # symlink, depending on version and on whether the project is a submodule
    # or a linked worktree. Ask git instead of guessing at the layout.
    if [[ ! -d "${TREE}/${path}" ]]; then
        fail "${path}: directory missing"
        return
    fi
    inside="$(git -C "${TREE}/${path}" rev-parse --is-inside-work-tree 2>/dev/null || true)"
    if [[ "${inside}" != "true" ]]; then
        fail "${path}: not a git work tree (git rev-parse --is-inside-work-tree != true)"
        return
    fi
    got="$(git -C "${TREE}/${path}" rev-parse HEAD 2>/dev/null || echo "?")"
    if [[ "${got}" == "${want}" ]]; then
        pass "${path} @ ${got}"
    else
        fail "${path} is ${got}, expected ${want}"
    fi
}
check_repo device/xiaomi/equuleus       db40750f063e86110e20db1455729c0f6621f7da
check_repo device/xiaomi/sdm845-common  35cf356b095e033e71261b16c7fa319faac12cb3
check_repo kernel/xiaomi/sdm845         aa8adfe9bf212c6e93238a86980b402da4f819a
check_repo hardware/xiaomi              281f97dbac46b75eb7b6a680624e62e807ec0689
check_repo hardware/lineage/interfaces  3466aa530ace6de0760c12a68cf81b31e8d3807b
check_repo vendor/aosp                  2887d1b7729f38560b1cb4b27317c2bf29f2325b
check_repo vendor/gms                   ffe5c52d947eec784a07124dfb72e95840e8f3c7

# ------------------------------------------------------- 3. patches applied
echo
echo "--- 3. patches applied to the device trees ------------------------------"
# A patch is applied iff reversing it succeeds; this is robust to later edits
# *on top of* the patch, unlike repeating the forward check.
patch_state() {
    local repo="$1" patch="$2" name
    name="$(basename "${patch}")"
    if [[ ! -f "${patch}" ]]; then fail "patch file missing: ${name}"; return; fi
    if git -C "${TREE}/${repo}" apply --reverse --check "${patch}" 2>/dev/null; then
        pass "${name} applied to ${repo}"
    elif git -C "${TREE}/${repo}" apply --check "${patch}" 2>/dev/null; then
        fail "${name} NOT applied to ${repo} (it would apply cleanly)"
    else
        fail "${name} neither applies nor reverses against ${repo} (tree drifted)"
    fi
}
# All SEVEN patches that a normal build applies. 0005 is deliberately absent:
# it is archived, and applying it conflicts with the local-manifest GMS repoint
# (git-repo would raise "remove-project element specifies non-existent project").
# A build that has 0005 applied is rejected by sync.sh's guard, not here.
patch_state device/xiaomi/equuleus       "${PROJECT_DIR}/patches/0001-equuleus-product-setup.patch"
patch_state device/xiaomi/equuleus       "${PROJECT_DIR}/patches/0002-equuleus-drop-lineage-sdk-overlay.patch"
patch_state device/xiaomi/sdm845-common  "${PROJECT_DIR}/patches/0003-sdm845-common-use-vendor-aosp.patch"
patch_state device/xiaomi/sdm845-common  "${PROJECT_DIR}/patches/0004-sdm845-common-drop-lineage-overlays.patch"
patch_state device/xiaomi/equuleus       "${PROJECT_DIR}/patches/0006-equuleus-fix-pn553-fw-path.patch"
patch_state device/xiaomi/equuleus       "${PROJECT_DIR}/patches/0007-equuleus-ir-face-unlock-camera-id.patch"
patch_state device/xiaomi/sdm845-common  "${PROJECT_DIR}/patches/0008-sdm845-common-ir-face-unlock-aux-camera.patch"

# Applying a patch is not the same as the resulting content being right. Verify
# the three things 0006-0008 exist to guarantee; a silently misplaced hunk would
# pass patch_state but leave the tree wrong.
echo
echo "       verifying the content 0006-0008 are meant to produce:"
if grep -qs 'vendor/lib64/libpn553_fw.so' \
        "${TREE}/device/xiaomi/equuleus/proprietary-files.txt"; then
    pass "NFC firmware path fixed (lib64/libpn553_fw.so)"
else
    fail "0006 result missing: proprietary-files.txt does not reference lib64/libpn553_fw.so"
fi

if grep -qs '^vendor/lib/libpn553_fw\.so' \
        "${TREE}/device/xiaomi/equuleus/proprietary-files.txt"; then
    fail "0006 result wrong: the list still asks for lib/libpn553_fw.so (a 32-bit path)"
else
    pass "no stale 32-bit libpn553 path remains"
fi

if grep -qs '^ro\.face\.sense_service\.camera_id=' \
        "${TREE}/device/xiaomi/equuleus/system_ext.prop"; then
    pass "IR camera id set: $(grep '^ro\.face\.sense_service\.camera_id=' \
        "${TREE}/device/xiaomi/equuleus/system_ext.prop" | head -1)"
else
    fail "0007 result missing: ro.face.sense_service.camera_id is not set; ParanoidSense would fall back to the RGB front camera"
fi

if grep -qs 'co\.aospa\.sense' "${TREE}/device/xiaomi/sdm845-common/vendor.prop"; then
    pass "co.aospa.sense in vendor.camera.aux.packagelist"
else
    fail "0008 result missing: co.aospa.sense absent from vendor.camera.aux.packagelist; the aux IR camera would be hidden"
fi

# The original packagelist entries must survive: dropping them would regress
# Aperture and the stock camera apps.
AUX_LINE="$(grep -s '^vendor\.camera\.aux\.packagelist=' \
    "${TREE}/device/xiaomi/sdm845-common/vendor.prop" || true)"
AUX_MISSING=""
for pkg in com.android.camera org.codeaurora.snapcam org.lineageos.aperture \
           org.lineageos.aperture.dev co.aospa.sense; do
    case ",${AUX_LINE#*=}," in
        *",${pkg},"*) : ;;
        *) AUX_MISSING="${AUX_MISSING} ${pkg}" ;;
    esac
done
if [[ -z "${AUX_MISSING}" ]]; then
    pass "aux packagelist keeps all 4 original entries plus co.aospa.sense"
else
    fail "aux packagelist is missing:${AUX_MISSING}"
fi

# The product must exist under the patched name, or lunch cannot resolve it.
if grep -qs 'PRODUCT_NAME := aosp_equuleus' \
        "${TREE}/device/xiaomi/equuleus/aosp_equuleus.mk"; then
    pass "product aosp_equuleus defined"
else
    fail "device/xiaomi/equuleus/aosp_equuleus.mk missing or does not declare PRODUCT_NAME"
fi

# ------------------------------------------------------- 4. proprietary blobs
echo
echo "--- 4. proprietary blobs ------------------------------------------------"
for pair in "vendor/xiaomi/equuleus:equuleus" "vendor/xiaomi/sdm845-common:sdm845-common"; do
    vpath="${pair%%:*}"; label="${pair##*:}"
    if [[ ! -d "${TREE}/${vpath}" ]]; then
        fail "${vpath} MISSING — run BLOB_EXTRACTION.md first"
        continue
    fi
    if [[ ! -f "${TREE}/${vpath}/BoardConfigVendor.mk" ]]; then
        fail "${vpath}/BoardConfigVendor.mk missing (incomplete extraction)"
    else
        pass "${vpath}/BoardConfigVendor.mk present"
    fi
    # the *-vendor.mk name differs per tree; accept either
    if compgen -G "${TREE}/${vpath}/*-vendor.mk" >/dev/null; then
        pass "${vpath}/*-vendor.mk present"
    else
        fail "${vpath}/*-vendor.mk missing (setup-makefiles.py did not run)"
    fi
    if compgen -G "${TREE}/${vpath}/Android.bp" >/dev/null; then
        pass "${vpath}/Android.bp present"
    else
        fail "${vpath}/Android.bp missing (extract-files.py did not run)"
    fi
done

# ------------------------------------------------- 5. blob list completeness
echo
echo "--- 5. every blob named in proprietary-files.txt exists ------------------"
# NOTE: this is the *coarse* check. It validates that each declared source
# basename exists somewhere under the vendor tree. The authoritative check that
# honours dest paths, renames and SONAME fixes is
#   scripts/verify_blobs.py
# which parses extract-utils' real arguments. Run it after this script.
bloblist_check() {
    local devdir="$1" vpath="$2" label="$3" missing=0 total=0
    local list="${TREE}/${devdir}/proprietary-files.txt"
    if [[ ! -f "${list}" ]]; then
        fail "missing blob list: ${devdir}/proprietary-files.txt"
        return
    fi
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "${line}" | tr -d '\r' | sed 's/[[:space:]]*$//')"
        [[ -z "${line}" ]] && continue
        total=$((total + 1))
        local src="${line%%|*}"          # strip |args
        src="${src%%:*}"                 # strip :dest
        src="$(printf '%s' "${src}" | sed 's/^-//;s/[[:space:]]*$//')"
        [[ -z "${src}" ]] && continue
        local base dest
        base="$(basename "${src}")"
        # honour an explicit ":dest" when present
        if printf '%s' "${line}" | grep -q ':'; then
            dest="$(printf '%s' "${line#*:}" | sed 's/|.*//;s/[[:space:]]*$//')"
        else
            dest="${src}"
        fi
        # accept either the declared dest or any file with the same basename
        # (extract-utils may relocate); the strict check is verify_blobs.py
        if [[ -e "${TREE}/${vpath}/${dest}" ]] || \
           [[ -n "$(find "${TREE}/${vpath}" -name "${base}" -type f -print -quit 2>/dev/null)" ]]; then
            :
        else
            missing=$((missing + 1))
            (( missing <= 5 )) && printf '       missing (%s): %s\n' "${label}" "${src}"
        fi
    done < "${list}"
    if (( missing == 0 )); then
        pass "${label}: all ${total} declared entries found in ${vpath}"
    else
        fail "${label}: ${missing}/${total} declared entries not found in ${vpath}"
    fi
}
bloblist_check device/xiaomi/sdm845-common vendor/xiaomi/sdm845-common sdm845-common
bloblist_check device/xiaomi/equuleus      vendor/xiaomi/equuleus      equuleus

echo
echo "       Authoritative blob verification (dest paths, renames, SONAME fixes):"
echo "         ${PYTHON} scripts/verify_blobs.py ${TREE}"

# ------------------------------------------------------- 6. out/ capacity
echo
echo "--- 6. output space -----------------------------------------------------"
FREE_AFTER="$(df -Pk "${TREE}" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
info "free before build: ${FREE_AFTER} GiB"
if (( FREE_AFTER >= 100 )); then
    pass "${FREE_AFTER} GiB free for out/ (>= 100 GiB)"
else
    fail "${FREE_AFTER} GiB free is too little for out/ (need >= 100 GiB)"
fi

echo
echo "=============================================================="
if (( FAILURES > 0 )); then
    echo "RESULT: TREE NOT BUILDABLE — ${FAILURES} failure(s), ${WARNINGS} warning(s)"
    echo "Every [FAIL] is a missing or mismatched *input*, not an environment problem."
    exit 1
fi
echo "RESULT: TREE READY FOR BUILD — 0 failures, ${WARNINGS} warning(s)"
echo "This proves the inputs are present and pinned. It does NOT prove the build"
echo "succeeds: Soong/Make and the kernel have not been run."
echo "log: ${LOG_FILE}"
echo "=============================================================="
exit 0
