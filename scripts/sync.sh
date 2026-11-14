#!/usr/bin/env bash
#
# sync.sh — reproducible PixelOS fifteen source sync for equuleus.
#
# Design constraints (all deliberate):
#   * PixelOS' Android 15 manifest is ARCHIVED. This script therefore refuses
#     to run against a mutable branch: it pins the manifest revision.
#   * `repo sync --force-sync` is never used. Interrupted syncs are resumed
#     with a bounded retry loop instead, so local work is not destroyed.
#   * Every step is fail-fast (set -e / pipefail) and logged.
#   * It does not modify the manifest: .repo/local_manifests/equuleus.xml is
#     supplied by this deliverable and validated before use.
#
# Usage:
#   scripts/sync.sh /path/to/pixelos15
#
# Exit codes: 0 = synced, non-zero = stopped at the first failing step.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TREE="${1:-}"
if [[ -z "${TREE}" ]]; then
    echo "usage: $0 /path/to/pixelos15" >&2
    exit 2
fi

# Pinned upstream coordinates (see UPSTREAM_LOCK.md).
MANIFEST_URL="https://github.com/PixelOS-AOSP/manifest.git"
MANIFEST_BRANCH="fifteen"
MANIFEST_SHA="0334d5e468a86ab0aefa6d3a40bc2abd11bf4035"
LOCAL_MANIFEST="${PROJECT_DIR}/.repo/local_manifests/equuleus.xml"

MIN_FREE_GIB="${MIN_FREE_GIB:-400}"
SYNC_RETRIES="${SYNC_RETRIES:-3}"

mkdir -p "${PROJECT_DIR}/logs"
LOG_FILE="${PROJECT_DIR}/logs/sync-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

step "preconditions"
[[ -f "${LOCAL_MANIFEST}" ]] || die "missing local manifest: ${LOCAL_MANIFEST}"
command -v repo >/dev/null 2>&1 || die "repo is not installed"
command -v git  >/dev/null 2>&1 || die "git is not installed"

# Resolve a Python that actually runs. Under `set -u`, referencing an unset
# PYTHON used to abort the script right here with "unbound variable" — the
# manifest validation below would never run and the sync would never start.
# A bare `python3` is not enough evidence: on some systems it is an App-Store
# shim that exits non-zero, so require it to execute.
PYTHON=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 && \
            "${cand}" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        PYTHON="${cand}"
        break
    fi
done
[[ -n "${PYTHON}" ]] || die "no working python3/python found; needed to validate the local manifest"
echo "python         : ${PYTHON} ($(${PYTHON} --version 2>&1))"
echo "tree           : ${TREE}"
echo "manifest       : ${MANIFEST_URL} @ ${MANIFEST_BRANCH} (${MANIFEST_SHA})"
echo "local manifest : ${LOCAL_MANIFEST}"
echo "log            : ${LOG_FILE}"

mkdir -p "${TREE}"
TREE="$(cd -- "${TREE}" && pwd)"

step "free space check"
FREE_GIB="$(df -Pk "${TREE}" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
echo "free space: ${FREE_GIB} GiB"

# The requirement depends on what still has to happen, not on a single number.
#
# A FROM-SCRATCH sync must download ~190 GiB into the tree, so it needs the full
# MIN_FREE_GIB (400) available BEFORE it starts.
#
# A tree that is ALREADY synced only needs room for the patch application and the
# build that follows (~140 GiB: out/ 90-130 plus blob extraction ~6). Applying
# the 400 GiB pre-sync threshold to an already-synced tree aborts a perfectly
# good resume with "need at least 400 GiB free, have 398 GiB" — observed on the
# real tree, where 190 GiB is already on disk and simply is not "free".
ALREADY_SYNCED=0
if [[ -d "${TREE}/.repo" ]] && [[ -f "${TREE}/build/envsetup.sh" ]]; then
    ALREADY_SYNCED=1
fi

if (( ALREADY_SYNCED )); then
    # patch-only pass: enough for the build that follows this script
    POST_SYNC_MIN_GIB="${POST_SYNC_MIN_GIB:-150}"
    echo "tree already synced: requiring ${POST_SYNC_MIN_GIB} GiB free for the build"
    (( FREE_GIB >= POST_SYNC_MIN_GIB )) \
        || die "tree is synced but only ${FREE_GIB} GiB free; the build needs at
least ${POST_SYNC_MIN_GIB} GiB (out/ plus blob extraction). Free space and re-run."
else
    echo "fresh sync: requiring ${MIN_FREE_GIB} GiB free before downloading"
    (( FREE_GIB >= MIN_FREE_GIB )) \
        || die "need at least ${MIN_FREE_GIB} GiB free for a fresh sync, have ${FREE_GIB} GiB"
fi

step "connectivity check (fails instead of silently degrading)"
for url in https://github.com/ https://android.googlesource.com/ https://gitlab.com/; do
    code="$(curl --location --silent --show-error --max-time 25 \
                  --output /dev/null --write-out '%{http_code}' "${url}")" \
        || die "cannot reach ${url}"
    echo "  ${url} -> HTTP ${code}"
    case "${code}" in
        2*|3*) : ;;
        *) die "${url} returned HTTP ${code}" ;;
    esac
done

step "repo init (manifest pinned to a branch, then verified against ${MANIFEST_SHA})"
cd -- "${TREE}"

if [[ -d .repo ]]; then
    echo ".repo already exists; verifying it points at the right manifest"
    CURRENT="$(git --git-dir=.repo/manifests.git config --get remote.origin.url 2>/dev/null || true)"
    if [[ "${CURRENT}" != "${MANIFEST_URL}" ]]; then
        die ".repo points at '${CURRENT}', not '${MANIFEST_URL}'. Refusing to reuse it."
    fi
    # Do NOT compare local branch names. `repo init -b fifteen` leaves the local
    # branch called `default` while tracking origin/fifteen, which is normal.
    # What matters is the remote and the commit; the commit is verified below.
    pass_branch="$(git --git-dir=.repo/manifests.git symbolic-ref --short HEAD 2>/dev/null || true)"
    pass_sha="$(git --git-dir=.repo/manifests.git rev-parse HEAD 2>/dev/null || true)"
    if [[ "${pass_sha}" == "${MANIFEST_SHA}" ]]; then
        echo "existing .repo is correct (local branch '${pass_branch}', HEAD ${pass_sha:0:12})"
    else
        # A different SHA may simply mean the branch moved forward. Only refuse
        # outright if the expected commit is not reachable at all.
        if git --git-dir=.repo/manifests.git cat-file -e "${MANIFEST_SHA}^{commit}" 2>/dev/null; then
            echo "existing .repo HEAD ${pass_sha:0:12} differs from the audited"
            echo "  ${MANIFEST_SHA:0:12}; checking out the audited commit"
            git --git-dir=.repo/manifests.git --work-tree=.repo/manifests \
                checkout -q "${MANIFEST_SHA}" 2>/dev/null || true
        else
            die "existing .repo HEAD is ${pass_sha} and the audited commit
${MANIFEST_SHA} is not present in it. Either this .repo belongs to another
project, or the audited manifest is unreachable. Refusing to sync."
        fi
    fi
    echo "not re-initialising"
else
    # `--git-lfs` only exists in repo >= 2.26; Ubuntu 22.04 ships 2.17, which
    # rejects it and aborts the init. Probe rather than assume, so the same
    # script works with either launcher. None of PixelOS' repointed projects
    # actually need LFS, so omitting the flag on an older repo is safe.
    REPO_LFS_FLAG=""
    if repo init --help 2>&1 | grep -q -- "--git-lfs"; then
        REPO_LFS_FLAG="--git-lfs"
        echo "repo launcher supports --git-lfs (enabling)"
    else
        echo "repo launcher predates --git-lfs (Ubuntu 2.17); continuing without it"
        echo "  non-LFS sync is sufficient for the PixelOS fifteen manifest"
    fi
    # shellcheck disable=SC2086
    repo init -u "${MANIFEST_URL}" -b "${MANIFEST_BRANCH}" ${REPO_LFS_FLAG}
fi

ACTUAL_SHA="$(git --git-dir=.repo/manifests.git rev-parse HEAD)"
echo "manifest HEAD: ${ACTUAL_SHA}"
if [[ "${ACTUAL_SHA}" != "${MANIFEST_SHA}" ]]; then
    # The manifest repo is the root of trust for every other pin: if it moved,
    # the tree we are about to build is not the tree that was audited. Refuse
    # rather than warn, so an unreviewed manifest cannot silently ship.
    die "manifest HEAD ${ACTUAL_SHA} differs from the audited ${MANIFEST_SHA}.
Refusing to sync an unreviewed manifest. To proceed deliberately, check out
${MANIFEST_SHA} in .repo/manifests (or update MANIFEST_SHA in this script after
re-auditing)."
fi

step "install local manifest"
mkdir -p .repo/local_manifests
install -m 0644 "${LOCAL_MANIFEST}" .repo/local_manifests/equuleus.xml
"${PYTHON}" - .repo/local_manifests/equuleus.xml <<'PY'
import re
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
projects = root.findall("project")
assert projects, "local manifest has no projects"
for p in projects:
    rev = p.get("revision") or ""
    assert re.fullmatch(r"[0-9a-f]{40}", rev), f"{p.get('path')}: unpinned revision {rev!r}"
print(f"local manifest validated: {len(projects)} pinned project(s)")
PY

step "repo sync (resumable, never --force-sync)"
attempt=1
while :; do
    echo "sync attempt ${attempt}/${SYNC_RETRIES}"
    # `$?` must be read INSIDE the else branch: after an `if` statement with no
    # else, $? is 0 regardless of what the condition did:
    #     if false; then :; fi; echo $?   ->   0
    # Reading it after the fi would have reported every failure as exit 0.
    if repo sync -c -j"$(nproc)" --no-clone-bundle -q; then
        echo "sync succeeded on attempt ${attempt}"
        break
    else
        rc=$?
    fi
    if (( attempt >= SYNC_RETRIES )); then
        die "repo sync failed ${SYNC_RETRIES} times (last exit ${rc}); see ${LOG_FILE}"
    fi
    echo "sync attempt ${attempt} failed (exit ${rc}); retrying in 30s"
    echo "note: a retry continues from the existing .repo, nothing is deleted"
    attempt=$((attempt + 1))
    sleep 30
done

step "verify the device trees landed at the pinned commits"
verify_repo() {
    local path="$1" name="$2" want="$3" got
    [[ -d "${TREE}/${path}" ]] || die "expected checkout missing: ${path}"
    got="$(git -C "${TREE}/${path}" rev-parse HEAD)"
    if [[ "${got}" == "${want}" ]]; then
        printf '  [OK]   %-34s %s\n' "${name}" "${got}"
    else
        die "${name} is at ${got}, expected ${want}"
    fi
}

verify_repo device/xiaomi/equuleus        android_device_xiaomi_equuleus        db40750f063e86110e20db1455729c0f6621f7da
verify_repo device/xiaomi/sdm845-common   android_device_xiaomi_sdm845-common   35cf356b095e033e71261b16c7fa319faac12cb3
verify_repo kernel/xiaomi/sdm845          android_kernel_xiaomi_sdm845          aa8adfe9bf212c6e93238a86980b4024da4f819a
verify_repo hardware/xiaomi               hardware_xiaomi                       281f97dbac46b75eb7b6a680624e62e807ec0689

step "apply the equuleus port patches"
apply_patch() {
    local repo="$1" patch="$2"
    local name
    name="$(basename "${patch}")"
    [[ -f "${patch}" ]] || die "patch missing: ${patch}"
    if git -C "${TREE}/${repo}" apply --check "${patch}" 2>/dev/null; then
        git -C "${TREE}/${repo}" apply "${patch}"
        printf '  [APPLIED] %-52s -> %s\n' "${name}" "${repo}"
    elif git -C "${TREE}/${repo}" apply --reverse --check "${patch}" 2>/dev/null; then
        printf '  [SKIP]    %-52s already applied to %s\n' "${name}" "${repo}"
    else
        die "${name} does not apply to ${repo}; the tree is not at the pinned base"
    fi
}

# ---------------------------------------------------------------------------
# P0-2 — DO NOT apply patches/0005 here.
#
# There are exactly two ways to repoint vendor/gms away from the sixteen-only
# upstream repository:
#   (a) the local manifest: <remove-project name="vendor_gms"/> then add
#       vendor_gms-15, installed BEFORE repo sync;
#   (b) rewriting the upstream snippets/custom.xml in place (patch 0005).
#
# They are MUTUALLY EXCLUSIVE. Combining them makes the local manifest's
# <remove-project> target vanish, and git-repo aborts with
#
#   ManifestParseError: remove-project element specifies non-existent project:
#   <remove-project name="vendor_gms"/>
#
# (manifest_xml.py: `if not removed_project and not XmlBool(node,"optional",False)`.)
# This was confirmed by running the real git-repo parser; see
# scripts/verify_manifest_parse.py, CASE 2.
#
# This script uses strategy (a). Patch 0005 is kept as documentation / for the
# alternative flow only, and is deliberately NOT applied.
# ---------------------------------------------------------------------------
if [[ -f "${PROJECT_DIR}/patches/0005-manifest-gms-repo.patch" ]] && \
        git -C "${TREE}/.repo/manifests" apply --reverse --check \
            "${PROJECT_DIR}/patches/0005-manifest-gms-repo.patch" 2>/dev/null; then
    die "patch 0005 is already applied to the upstream manifest. That conflicts with the
local-manifest override in .repo/local_manifests/equuleus.xml and git-repo will fail with
'remove-project element specifies non-existent project'. Revert 0005 in .repo/manifests
(git -C .repo/manifests checkout -- snippets/custom.xml) and re-run."
fi

# Patches 0001-0004: PixelOS product/branding/build-policy adaptation.
apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0001-equuleus-product-setup.patch"
apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0002-equuleus-drop-lineage-sdk-overlay.patch"
apply_patch device/xiaomi/sdm845-common "${PROJECT_DIR}/patches/0003-sdm845-common-use-vendor-aosp.patch"
apply_patch device/xiaomi/sdm845-common "${PROJECT_DIR}/patches/0004-sdm845-common-drop-lineage-overlays.patch"

# Patch 0005 (vendor/gms repoint) is ARCHIVED and must NOT be applied: the local
# manifest already performs that repoint, and applying both makes git-repo fail
# with "remove-project element specifies non-existent project". See the guard
# above and KNOWN_BLOCKERS.md B-15.
#
# Patches 0006-0008 are part of a NORMAL build:
#   0006  fix the libpn553_fw.so path (lib/ -> lib64/) so the NFC firmware the
#         OTA ships is not looked up at a path that does not exist
#   0007  set ro.face.sense_service.camera_id so ParanoidSense uses the IR camera
#         instead of falling back to the RGB selfie sensor
#   0008  allow co.aospa.sense into vendor.camera.aux.packagelist, without which
#         Camera.shouldExposeAuxCamera() hides the IR device entirely
apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0006-equuleus-fix-pn553-fw-path.patch"
apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0007-equuleus-ir-face-unlock-camera-id.patch"
apply_patch device/xiaomi/sdm845-common "${PROJECT_DIR}/patches/0008-sdm845-common-ir-face-unlock-aux-camera.patch"

# Verify the resulting state, not just that `git apply` returned 0. A patch that
# silently applied to the wrong hunk position would pass the check above but
# leave the tree wrong.
if ! grep -qs '^ro\.face\.sense_service\.camera_id=' "${TREE}/device/xiaomi/equuleus/system_ext.prop"; then
    die "0007 applied but ro.face.sense_service.camera_id is absent from system_ext.prop"
fi
if ! grep -qs 'vendor/lib64/libpn553_fw.so' "${TREE}/device/xiaomi/equuleus/proprietary-files.txt"; then
    die "0006 applied but proprietary-files.txt still lists lib/libpn553_fw.so"
fi
if ! grep -qs 'co\.aospa\.sense' "${TREE}/device/xiaomi/sdm845-common/vendor.prop"; then
    die "0008 applied but co.aospa.sense is absent from vendor.camera.aux.packagelist"
fi

# vendor/gms must be the fifteen-compatible repo, and its products/gms.mk must
# exist, or aosp_equuleus cannot be configured at all (see KNOWN_BLOCKERS B-14).
if [[ -f "${TREE}/vendor/gms/products/gms.mk" ]]; then
    printf '  [OK]      vendor/gms/products/gms.mk present @ %s\n' \
        "$(git -C "${TREE}/vendor/gms" rev-parse --short HEAD 2>/dev/null || echo '?')"
else
    die "vendor/gms/products/gms.mk missing. vendor/aosp/config/common.mk inherits it
unconditionally. Check that .repo/local_manifests/equuleus.xml was installed before
repo sync and that it repointed vendor/gms to vendor_gms-15 (B-14). Do NOT also apply
patches/0005: the two mechanisms conflict (see the note above)."
fi

step "record provenance"
{
    echo "synced_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "manifest_url=${MANIFEST_URL}"
    echo "manifest_branch=${MANIFEST_BRANCH}"
    echo "manifest_head=${ACTUAL_SHA}"
    for path in device/xiaomi/equuleus device/xiaomi/sdm845-common \
                kernel/xiaomi/sdm845 hardware/xiaomi vendor/aosp vendor/gms; do
        if [[ -d "${TREE}/${path}/.git" ]]; then
            echo "repo:${path}=$(git -C "${TREE}/${path}" rev-parse HEAD)"
        fi
    done
} | tee "${TREE}/SYNC_PROVENANCE.txt"

# ---------------------------------------------------------------------------
# Full revision lock (P0-4).
#
# `repo init -b <branch>` resolves every project to a *branch head*, and
# git-repo does NOT read PixelOS' revision_lock.xml unless you pass
# `repo init -m`. So the only way to reproduce the exact 1,0xx-project tree
# that produced a build is `repo manifest -r`, which rewrites every <project>
# with the commit actually checked out.
# ---------------------------------------------------------------------------
step "generate full revision lock (repo manifest -r)"
LOCK_DIR="${TREE}/.repo/manifests-locks"
mkdir -p "${LOCK_DIR}"
LOCK_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCK_FILE="${LOCK_DIR}/revision_lock-${LOCK_STAMP}.xml"

if repo manifest -r -o "${LOCK_FILE}" 2>/dev/null; then
    PCOUNT="$(grep -c '<project' "${LOCK_FILE}" 2>/dev/null || echo 0)"
    PINNED="$(grep -cE 'revision="[0-9a-f]{40}"' "${LOCK_FILE}" 2>/dev/null || echo 0)"
    echo "wrote ${LOCK_FILE}"
    echo "  projects: ${PCOUNT}; pinned to a 40-char SHA: ${PINNED}"
    if (( PINNED < PCOUNT )); then
        echo "  WARNING: ${PCOUNT} projects but only ${PINNED} SHA-pinned."
        echo "           Unpinned entries will float on the next sync."
    fi
    cp "${LOCK_FILE}" "${TREE}/MANIFEST_LOCK.xml"
    echo "  stable copy: ${TREE}/MANIFEST_LOCK.xml"
    grep -oE '<project [^>]*>' "${TREE}/MANIFEST_LOCK.xml" \
        | sed -E 's/.*path="([^"]+)".*name="([^"]+)".*revision="([^"]+)".*/\1\t\2\t\3/' \
        | sort > "${TREE}/MANIFEST_LOCK.tsv" 2>/dev/null || true
    echo "  project list: ${TREE}/MANIFEST_LOCK.tsv"
else
    die "'repo manifest -r' failed: the exact revision set was not captured, so this
sync is not reproducible. Refusing to continue. Investigate and re-run:
    repo manifest -r -o ${LOCK_FILE}"
fi

step "reminder — the blob trees come from the LineageOS OTA"
# This used to say the trees were "intentionally absent" and told the reader to
# extract them from an official MIUI package. That is no longer how this project
# produces them: one official LineageOS 22.2 OTA now yields both trees, and the
# five-firmware MIUI route was never needed. Keep the message accurate so nobody
# goes looking for a MIUI package that is not part of this pipeline.
if [[ -d "${TREE}/vendor/xiaomi/equuleus/proprietary" ]]; then
    echo "  [OK] vendor/xiaomi/equuleus present"
else
    echo "  [MISSING] vendor/xiaomi/equuleus"
fi
if [[ -d "${TREE}/vendor/xiaomi/sdm845-common/proprietary" ]]; then
    echo "  [OK] vendor/xiaomi/sdm845-common present"
else
    echo "  [MISSING] vendor/xiaomi/sdm845-common"
fi

if [[ -d "${TREE}/vendor/xiaomi/equuleus/proprietary" && \
      -d "${TREE}/vendor/xiaomi/sdm845-common/proprietary" ]]; then
    cat <<'EOF'
  Both blob trees are in place. Verify them with:
      python3 scripts/verify_blobs.py <tree> --strict
EOF
else
    cat <<'EOF'
  The blob trees are NOT in place, so the ROM cannot link. Produce them with ONE
  official LineageOS 22.2 equuleus OTA:

      scripts/extract_vendor_full.sh --ota lineage-22.2-*-equuleus-signed.zip \
                                     --tree <this tree>

  Or receive the pre-built archive on a build machine (per-file SHA256 included):

      VENDOR_TRANSFER.md

  The legacy five-firmware MIUI route in BLOB_EXTRACTION.md is background only and
  is not part of this pipeline.
EOF
fi

echo
echo "sync complete: ${TREE}"
echo "log: ${LOG_FILE}"
