#!/usr/bin/env bash
#
# pack_vendor.sh — produce a verifiable archive of the extracted vendor trees.
#
# Why this exists: B01_EXTRACTION_REPORT.json describes the extraction, but a
# report is not the blobs. A cloud build machine needs the actual binaries. This
# script packages them with a per-file manifest and a top-level SHA256, so the
# receiving side can prove it got the same bytes.
#
# Design points:
#   * deterministic ordering, so two runs produce the same file list
#   * a MANIFEST.sha256 listing every member's SHA256, sorted by path
#   * the archive itself hashed and written next to it
#   * split volumes, because 525 MiB is impractical to move in one piece over a
#     flaky link; each volume is independently verifiable
#   * refuses to pack an empty or implausible tree (this is the difference
#     between shipping blobs and shipping a directory skeleton)
#
# Usage:
#   scripts/pack_vendor.sh [--tree DIR] [--out DIR] [--volume-mb N]
#
# Exit codes: 0 = archive(s) + manifests written and verified, 1 = failure.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TREE="${PROJECT_DIR}"
OUT="${PROJECT_DIR}/out/vendor-archive"
VOLUME_MB=200
while (($#)); do
    case "$1" in
        --tree) TREE="${2:-}"; shift 2 ;;
        --tree=*) TREE="${1#*=}"; shift ;;
        --out) OUT="${2:-}"; shift 2 ;;
        --out=*) OUT="${1#*=}"; shift ;;
        --volume-mb) VOLUME_MB="${2:-}"; shift 2 ;;
        --volume-mb=*) VOLUME_MB="${1#*=}"; shift ;;
        -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "${OUT}" "${PROJECT_DIR}/logs"
LOG="${PROJECT_DIR}/logs/pack-vendor-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG}") 2>&1

step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

VENDOR="${TREE}/vendor/xiaomi"

step "preconditions"
[[ -d "${VENDOR}" ]] || die "no vendor tree at ${VENDOR}. Run the B-01 extraction first."
for t in equuleus sdm845-common; do
    [[ -d "${VENDOR}/${t}/proprietary" ]] \
        || die "${VENDOR}/${t}/proprietary is missing; refusing to ship a skeleton"
done

# Sanity: a real blob tree has hundreds of files and hundreds of MiB. A tree
# that passes the directory check but contains almost nothing (or only empty
# files) must not be shipped as if it were the blobs.
COUNT="$(find "${VENDOR}" -type f | wc -l)"
BYTES="$(find "${VENDOR}" -type f -printf '%s\n' | awk '{s+=$1} END {printf "%d", s}')"
EMPTY="$(find "${VENDOR}" -type f -empty | wc -l)"
echo "  files : ${COUNT}"
echo "  bytes : ${BYTES} ($(( BYTES / 1024 / 1024 )) MiB)"
echo "  empty : ${EMPTY}"
(( COUNT >= 800 )) || die "only ${COUNT} files; expected ~872. This is not a complete tree."
(( BYTES >= 400000000 )) || die "only ${BYTES} bytes; expected ~525 MiB."
(( EMPTY <= 5 )) || die "${EMPTY} empty files found; that is a broken extraction, not blobs."

step "per-file manifest"
MANIFEST="${OUT}/MANIFEST.sha256"
# Sorted for determinism; paths relative to the tree root so the manifest is
# portable across machines.
( cd "${TREE}" && find vendor/xiaomi -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum ) > "${MANIFEST}"
echo "  $(wc -l < "${MANIFEST}") entries -> ${MANIFEST}"

step "archive"
STAMP="$(date -u +%Y%m%d)"
BASE="vendor-xiaomi-${STAMP}.tar"
TARBALL="${OUT}/${BASE}.xz"

# Deterministic tar: sorted names, fixed mtime/owner, no extended attrs.
tar --create --xz --file "${TARBALL}" \
    --directory "${TREE}" \
    --sort=name \
    --owner=0 --group=0 --numeric-owner \
    --mtime='2026-11-12 00:00:00Z' \
    vendor/xiaomi

TAR_SHA="$(sha256sum "${TARBALL}" | cut -d' ' -f1)"
TAR_SIZE="$(stat -c '%s' "${TARBALL}")"
echo "  ${BASE}.xz  $(( TAR_SIZE / 1024 / 1024 )) MiB"
echo "  sha256 ${TAR_SHA}"

step "split into ${VOLUME_MB} MiB volumes"
rm -f "${OUT}/${BASE}.xz.part"* 2>/dev/null || true
split --bytes="${VOLUME_MB}M" --numeric-suffixes=1 --suffix-length=3 \
      "${TARBALL}" "${OUT}/${BASE}.xz.part"
VOLUMES="$(ls -1 "${OUT}/${BASE}.xz.part"* | wc -l)"
echo "  ${VOLUMES} volume(s)"

step "volume checksums"
( cd "${OUT}" && sha256sum "${BASE}.xz.part"* > "${OUT}/VOLUMES.sha256" )
cat "${OUT}/VOLUMES.sha256"

step "self-verify"
# Read the archive back and confirm the manifest matches what is inside. This is
# the step that catches a corrupt tar before anyone uploads it.
VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "${VERIFY_DIR}"' EXIT
tar --extract --xz --file "${TARBALL}" --directory "${VERIFY_DIR}"
if ( cd "${VERIFY_DIR}" && sha256sum --quiet --check "${MANIFEST}" ); then
    echo "  [OK] every file in the archive matches MANIFEST.sha256"
else
    die "archive contents do not match the manifest; do not upload it"
fi

step "reassemble instructions"
cat <<EOF

To reassemble on the receiving side:

  cat ${BASE}.xz.part* > ${BASE}.xz
  sha256sum -c VOLUMES.sha256          # per-volume, before reassembly
  sha256sum ${BASE}.xz                  # must equal ${TAR_SHA}
  tar -xJf ${BASE}.xz -C /path/to/pixelos15
  sha256sum -c MANIFEST.sha256          # inside the extracted tree root
  python3 scripts/verify_blobs.py /path/to/pixelos15 --strict --json blob-report.json

The last command is the real gate: it re-checks architecture, SONAME and hashes.
EOF

step "result"
echo "artifacts in ${OUT}:"
ls -lh "${OUT}" | sed 's/^/  /'
echo
echo "archive sha256: ${TAR_SHA}"
echo "log: ${LOG}"
