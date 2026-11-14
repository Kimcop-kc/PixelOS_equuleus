#!/usr/bin/env bash
#
# cloud_vendor_transfer.sh — prepare and verify the blob transfer for an Alibaba
# Cloud ECS build, and print the exact commands to run on both sides.
#
# Why a dedicated script: the review asked for "the vendor archive, the SHA256, the
# upload and the integrity-verification commands" for the cloud build. Those are
# three different moments (produce / send / receive) and getting one of them wrong
# ships a skeleton or an unverified tree to a machine that costs money by the hour.
#
# Modes
#   prepare   build the archive + manifests, verify it by extracting it again
#   upload    print/inspect the exact upload commands (does not upload)
#   receive   verify a received archive end to end, then run the blob gate
#
# Usage:
#   scripts/cloud_vendor_transfer.sh prepare [--volume-mb N]
#   scripts/cloud_vendor_transfer.sh upload  [--host user@host] [--dir /data/transfer]
#                                             [--out DIR]
#   scripts/cloud_vendor_transfer.sh receive --archive DIR [--tree DIR]
#
# Exit codes: 0 = ok, 1 = verification failed, 2 = usage.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

MODE="${1:-}"
[[ -n "${MODE}" ]] || { echo "usage: $0 prepare|upload|receive ..." >&2; exit 2; }
shift || true

VOLUME_MB=200
HOST=""
RDIR="/data/transfer"
ARCHIVE_DIR=""
TREE=""
OUT_DIR=""

while (($#)); do
    case "$1" in
        --volume-mb) VOLUME_MB="${2:-}"; shift 2 ;;
        --volume-mb=*) VOLUME_MB="${1#*=}"; shift ;;
        --host) HOST="${2:-}"; shift 2 ;;
        --host=*) HOST="${1#*=}"; shift ;;
        --dir) RDIR="${2:-}"; shift 2 ;;
        --dir=*) RDIR="${1#*=}"; shift ;;
        --archive) ARCHIVE_DIR="${2:-}"; shift 2 ;;
        --archive=*) ARCHIVE_DIR="${1#*=}"; shift ;;
        --tree) TREE="${2:-}"; shift 2 ;;
        --tree=*) TREE="${1#*=}"; shift ;;
        --out) OUT_DIR="${2:-}"; shift 2 ;;
        --out=*) OUT_DIR="${1#*=}"; shift ;;
        -h|--help) sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

die() { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }
ok()  { printf '  [OK]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; }

# Pick an interpreter that actually runs. On Windows `python3` is frequently the
# Microsoft Store stub: `command -v` finds it, but invoking it exits non-zero and
# does nothing. Probe with a real expression.
PYTHON=""
for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
        PYTHON="$c"
        break
    fi
done
[[ -n "${PYTHON}" ]] || { echo "FATAL: no working python3 interpreter" >&2; exit 1; }

# ---------------------------------------------------------------------------
case "${MODE}" in
prepare)
    echo "Preparing the blob archive for cloud transfer"
    bash "${SCRIPT_DIR}/pack_vendor.sh" --volume-mb "${VOLUME_MB}" \
        | tee "${PROJECT_DIR}/logs/cloud-prepare-$(date -u +%Y%m%dT%H%M%SZ).log"

    OUT="${OUT_DIR:-${PROJECT_DIR}/out/vendor-archive}"
    # The packer leaves both the whole .tar.xz and its .part001. The whole file is
    # a duplicate of the volumes; shipping both invites sending the wrong one.
    WHOLE="$(ls -1 "${OUT}"/*.tar.xz 2>/dev/null | head -1 || true)"
    if [[ -n "${WHOLE}" ]]; then
        echo
        echo "Removing the un-split duplicate (the volumes carry the same bytes):"
        echo "  $(basename "${WHOLE}")"
        rm -f "${WHOLE}"
    fi
    echo
    echo "Files to upload (from ${OUT}):"
    ls -1 "${OUT}" | sed 's/^/  /'
    echo
    echo "Archive SHA256 (record this; the receiving side must match it):"
    # shellcheck disable=SC2012
    sha256sum "${OUT}"/*.part* | sed 's/^/  /'
    ;;

# ---------------------------------------------------------------------------
upload)
    OUT="${OUT_DIR:-${PROJECT_DIR}/out/vendor-archive}"
    OUT="$(cd "${OUT}" 2>/dev/null && pwd)" || die "no archive at ${OUT_DIR:-${PROJECT_DIR}/out/vendor-archive}; run '$0 prepare' first"
    [[ -n "${HOST}" ]] || HOST="user@your-ecs-public-ip"

    # ------------------------------------------------------------------
    # Exactly ONE archive generation may be present. A glob over two dates
    # concatenates incompatible volumes on the receiving side and produces a
    # corrupt tarball that still "extracts something".
    # ------------------------------------------------------------------
    mapfile -t DATES < <(ls -1 "${OUT}"/vendor-xiaomi-*.tar.xz.part* 2>/dev/null \
        | sed -E 's|.*/vendor-xiaomi-([0-9]{8})\.tar\.xz\.part.*|\1|' | sort -u)
    (( ${#DATES[@]} > 0 )) || die "no volumes found in ${OUT}; run '$0 prepare' first"
    if (( ${#DATES[@]} > 1 )); then
        KEEP_HINT="$(printf 'vendor-xiaomi-%s.tar.xz.part* ' "${DATES[@]}")"
        die "volumes from ${#DATES[@]} different archive dates are present:
    ${DATES[*]}
Remove all but one generation first. Uploading a mixture would produce a corrupt
tarball on the receiving side. Volumes currently present:
    ${KEEP_HINT}
Keep exactly one date and re-run."
    fi
    STAMP_DATE="${DATES[0]}"

    # Collect the exact file set: every volume of THIS date, plus both manifests.
    mapfile -t FILES < <(
        { ls -1 "${OUT}/vendor-xiaomi-${STAMP_DATE}.tar.xz.part"* 2>/dev/null
          echo "${OUT}/VOLUMES.sha256"
          echo "${OUT}/MANIFEST.sha256"
        } | while read -r f; do [[ -f "$f" ]] && echo "$f"; done
    )
    (( ${#FILES[@]} >= 3 )) || die "incomplete set: need >=1 volume + VOLUMES.sha256 +
MANIFEST.sha256. Found ${#FILES[@]} file(s)."

    EXPECTED_VOLS="$(ls -1 "${OUT}/vendor-xiaomi-${STAMP_DATE}.tar.xz.part"* | wc -l)"
    LISTED_VOLS="$(wc -l < "${OUT}/VOLUMES.sha256")"
    if (( EXPECTED_VOLS != LISTED_VOLS )); then
        die "VOLUMES.sha256 lists ${LISTED_VOLS} volume(s) but ${EXPECTED_VOLS} exist
on disk. Regenerate the archive rather than uploading an untracked volume."
    fi

    echo "Verifying the archive locally before upload"
    ( cd "${OUT}" && sha256sum -c VOLUMES.sha256 ) || die "local archive is corrupt; do not upload"
    ok "local volumes verified (${EXPECTED_VOLS} volume(s), date ${STAMP_DATE})"

    echo
    echo "Upload set (${#FILES[@]} files, all of them required):"
    for f in "${FILES[@]}"; do
        printf '  %-56s %s\n' "$(basename "$f")" "$(sha256sum "$f" | cut -c1-16)"
    done

    # A single remote directory is used for send and receive; both sides must
    # agree or the receiver looks in the wrong place.
    RECEIVE_DIR="${RDIR%/}"

    cat <<EOF

Upload commands — send EVERY file listed above, into ${RECEIVE_DIR}

  # a) rsync, resumable, verifies per block
  rsync -avP --partial ${OUT}/ ${HOST}:${RECEIVE_DIR}/

  # b) scp, explicit file list (never a glob over multiple dates)
  scp $(printf '%q ' "${FILES[@]}")${HOST}:${RECEIVE_DIR}/

  # c) object storage: upload the same ${#FILES[@]} files, keep the sha256 alongside

Then on the instance (Ubuntu 22.04). This is exactly what 'receive' does:

  cd ${RECEIVE_DIR}
  ls -1                       # must show ${EXPECTED_VOLS} .part file(s) + 2 .sha256
  sha256sum -c VOLUMES.sha256
  cat vendor-xiaomi-${STAMP_DATE}.tar.xz.part* > vendor.tar.xz
  tar -xJf vendor.tar.xz -C <pixelos tree>
  cd <pixelos tree> && sha256sum -c ${RECEIVE_DIR}/MANIFEST.sha256

  # or let the script do and CHECK all of it:
  ${PROJECT_DIR}/scripts/cloud_vendor_transfer.sh receive \
      --archive ${RECEIVE_DIR} --tree <pixelos tree>

'BUILD READY' is only printed when the transfer hash, the per-file manifest AND
verify_blobs.py --strict all pass. Expected verifier result:
  OK=0  FAIL=0  RESIGNED=5  UNVERIFIABLE=0  SKIPPED=857
RESIGNED=5 is expected (LineageOS re-signs 5 platform APKs). SKIPPED=857 means
those entries pin no hash; see VENDOR_TRANSFER.md on what that does and does not
prove.
EOF
    ;;

# ---------------------------------------------------------------------------
receive)
    [[ -n "${ARCHIVE_DIR}" ]] || die "receive needs --archive <dir with the transferred files>"
    [[ -d "${ARCHIVE_DIR}" ]] || die "no such directory: ${ARCHIVE_DIR}"
    TREE="${TREE:-$(pwd)}"

    echo "Verifying a received blob archive"
    cd "${ARCHIVE_DIR}"

    echo
    echo "1. per-volume checksums"
    if [[ -f VOLUMES.sha256 ]]; then
        sha256sum -c VOLUMES.sha256 || die "a volume is corrupt; re-transfer only that volume"
        ok "all volumes match"
    else
        die "VOLUMES.sha256 missing; cannot verify the transfer"
    fi

    echo
    echo "2. reassemble"
    # A glob over two archive dates would concatenate incompatible volumes and
    # produce a tarball that fails in a confusing way. Pin to one date first.
    mapfile -t RDATES < <(ls -1 vendor-xiaomi-*.tar.xz.part* 2>/dev/null \
        | sed -E 's|vendor-xiaomi-([0-9]{8})\.tar\.xz\.part.*|\1|' | sort -u)
    (( ${#RDATES[@]} > 0 )) || die "no .part files found in ${ARCHIVE_DIR}"
    if (( ${#RDATES[@]} > 1 )); then
        die "volumes from ${#RDATES[@]} different archive dates are present:
    ${RDATES[*]}
Refusing to concatenate them: that would build a corrupt tarball. Keep exactly
one generation in ${ARCHIVE_DIR} and re-run."
    fi
    R_DATE="${RDATES[0]}"

    # Cross-check the volume set against VOLUMES.sha256: a missing or extra
    # volume must be caught before the tar is even assembled.
    DISK_VOLS="$(ls -1 vendor-xiaomi-${R_DATE}.tar.xz.part* | wc -l)"
    LIST_VOLS="$(wc -l < VOLUMES.sha256)"
    if (( DISK_VOLS != LIST_VOLS )); then
        die "volume set mismatch for ${R_DATE}: ${DISK_VOLS} on disk,
${LIST_VOLS} listed in VOLUMES.sha256. A volume is missing or extra; re-transfer."
    fi
    PART_COUNT="${DISK_VOLS}"
    cat vendor-xiaomi-${R_DATE}.tar.xz.part* > received.tar.xz
    GOT="$(sha256sum received.tar.xz | cut -d' ' -f1)"
    echo "  reassembled sha256: ${GOT}"
    (( PART_COUNT > 1 )) || echo "  (single volume; the volume checksum above already covers this)"
    ok "reassembled ${PART_COUNT} volume(s) into received.tar.xz"

    echo
    echo "3. extract into the tree"
    tar -xJf received.tar.xz -C "${TREE}" || die "extraction failed"
    ok "extracted into ${TREE}"

    echo
    echo "4. per-file manifest"
    if [[ -f MANIFEST.sha256 ]]; then
        ( cd "${TREE}" && sha256sum --quiet -c "${ARCHIVE_DIR}/MANIFEST.sha256" ) \
            || die "extracted files do not match the manifest"
        ok "all $(wc -l < MANIFEST.sha256) files match"
    else
        die "MANIFEST.sha256 missing; cannot prove the bytes arrived intact"
    fi

    # ======================================================================
    # 5. blob verification — an UNCONDITIONAL gate.
    #
    # A previous revision made this step conditional on the verifier existing
    # inside the target tree, and printed "SKIP" plus BUILD READY when it did
    # not. That is a validation bypass: a tree with no verifier reported success.
    #
    # The verifier is part of THIS project, not of the PixelOS source tree, so it
    # is always invoked from ${SCRIPT_DIR}. If it cannot run, or the device trees
    # are missing, or it fails — the transfer has NOT been proven and the exit
    # code must be non-zero.
    # ======================================================================
    echo
    echo "5. blob verification (verify_blobs.py --strict)"

    VERIFIER="${SCRIPT_DIR}/verify_blobs.py"
    if [[ ! -f "${VERIFIER}" ]]; then
        die "cannot verify: ${VERIFIER} is missing. The blob transfer is NOT
proven and the tree must not be built. This is a project-integrity failure,
not a transfer failure — restore scripts/verify_blobs.py and re-run."
    fi
    ok "verifier present: ${VERIFIER}"

    MISSING_DEV=""
    for t in equuleus sdm845-common; do
        [[ -f "${TREE}/device/xiaomi/${t}/proprietary-files.txt" ]] \
            || MISSING_DEV="${MISSING_DEV} ${t}"
    done
    if [[ -n "${MISSING_DEV}" ]]; then
        die "cannot verify: device tree(s) missing for${MISSING_DEV}.
verify_blobs.py needs device/xiaomi/<name>/proprietary-files.txt to know what to
check. Those come from 'repo sync', not from this blob archive.

The transferred bytes are intact (step 4 matched the manifest), but whether they
are the RIGHT files for this build is UNPROVEN. Do not build. Run 'repo sync'
first, then re-run this command."
    fi
    ok "device trees present"

    VB_LOG="${ARCHIVE_DIR}/blob-verify.log"
    set +e
    "${PYTHON}" "${VERIFIER}" "${TREE}" --strict \
        --json "${ARCHIVE_DIR}/blob-report.json" >"${VB_LOG}" 2>&1
    VB_RC=$?
    set -e

    echo "  --- verifier output (tail) ---"
    tail -12 "${VB_LOG}" | sed 's/^/  /'
    echo "  ---"

    case "${VB_RC}" in
        0) ok "blob verification passed (FAIL=0)" ;;
        3) die "blob verification INCOMPLETE (exit 3: UNVERIFIABLE entries).
Some declared property could not be confirmed against the installed file. The
transfer is not proven. Full log: ${VB_LOG}" ;;
        *) die "blob verification FAILED (exit ${VB_RC}). The blobs are present but
wrong: missing files, bad SONAME, or hash mismatch. The transfer is not proven
and the tree must not be built. Full log: ${VB_LOG}" ;;
    esac

    # Independent re-read of the report: a zero exit with a non-zero FAIL count
    # would still be a contradiction, so refuse to trust the exit code alone.
    if [[ -f "${ARCHIVE_DIR}/blob-report.json" ]]; then
        if ! "${PYTHON}" - "${ARCHIVE_DIR}/blob-report.json" <<'PYCHECK'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    d = json.load(fh)
totals = d.get("totals") or {}
fails = totals.get("FAIL", 0)
if fails:
    print("report says FAIL=%d" % fails)
    sys.exit(1)
sys.exit(0)
PYCHECK
        then
            die "blob-report.json records failures even though the verifier exited
0. Refusing to declare the transfer verified."
        fi
        ok "report cross-checked: FAIL=0"
    else
        die "verifier produced no JSON report; cannot confirm FAIL=0 independently"
    fi

    echo
    echo "BUILD READY: transfer hash, per-file manifest and strict blob verification"
    echo "all passed. Proceed with scripts/build.sh."
    ;;

*)
    echo "unknown mode: ${MODE} (expected prepare|upload|receive)" >&2
    exit 2
    ;;
esac
