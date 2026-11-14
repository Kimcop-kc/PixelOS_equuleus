#!/usr/bin/env bash
#
# fetch_clones.sh — re-create clones/ from the recorded URLs and pins.
#
# A third party who received only the docs+patches can reconstruct the exact
# evidence base this package verifies against. Each clone's HEAD is compared to
# the pinned SHA and the script fails if any differ.
#
# Usage:
#   scripts/fetch_clones.sh [--dest ./clones] [--metadata-only]
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

DEST="${PROJECT_DIR}/clones"
METADATA_ONLY=0
while (($#)); do
    case "$1" in
        --dest) DEST="${2:-}"; shift 2 ;;
        --dest=*) DEST="${1#*=}"; shift ;;
        --metadata-only) METADATA_ONLY=1; shift ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "${DEST}" "${PROJECT_DIR}/logs"
LOG="${PROJECT_DIR}/logs/fetch-clones-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG}") 2>&1

# name|url|branch|expected-sha
SPECS=(
"pixelos-manifest|https://github.com/PixelOS-AOSP/manifest|fifteen|0334d5e468a86ab0aefa6d3a40bc2abd11bf4035"
"device-xiaomi-equuleus|https://github.com/LineageOS/android_device_xiaomi_equuleus|lineage-22.2|db40750f063e86110e20db1455729c0f6621f7da"
"device-xiaomi-sdm845-common|https://github.com/LineageOS/android_device_xiaomi_sdm845-common|lineage-22.2|35cf356b095e033e71261b16c7fa319faac12cb3"
"hardware-xiaomi-pixelos|https://github.com/PixelOS-AOSP/hardware_xiaomi|fifteen|281f97dbac46b75eb7b6a680624e62e807ec0689"
"hardware-lineage-interfaces|https://github.com/LineageOS/android_hardware_lineage_interfaces|lineage-22.2|3466aa530ace6de0760c12a68cf81b31e8d3807b"
"vendor-aosp-pixelos|https://github.com/PixelOS-AOSP/vendor_aosp|fifteen|2887d1b7729f38560b1cb4b27317c2bf29f2325b"
"hw-qcom-caf-common|https://github.com/LineageOS/android_hardware_qcom-caf_common|lineage-22.2|cd600d7651ae32648ddce111b77ccca22f491609"
"device-lineage-sepolicy-pixelos|https://github.com/PixelOS-AOSP/device_lineage_sepolicy|fifteen|b6b52ebb459e3e8968a9ab84c45c8f81a66338e3"
"vendor-gms-15|https://gitlab.com/PixelOS-AOSP/vendor_gms-15|fifteen|ffe5c52d947eec784a07124dfb72e95840e8f3c7"
)

export GIT_TERMINAL_PROMPT=0
FAIL=0
for spec in "${SPECS[@]}"; do
    IFS='|' read -r name url branch want <<< "${spec}"
    target="${DEST}/${name}"
    printf '\n=== %s ===\n' "${name}"

    if [[ -d "${target}/.git" ]]; then
        got="$(git -C "${target}" rev-parse HEAD 2>/dev/null || echo none)"
        if [[ "${got}" == "${want}" ]]; then
            echo "  already present at ${got}"
            continue
        fi
        echo "  present but at ${got}; removing and re-cloning"
        rm -rf "${target}"
    fi

    # Two strategies: a plain clone, then a metadata-only clone for the very
    # large repositories (vendor_aosp, vendor_gms-15) where a full fetch is
    # slow or flaky.
    clone_ok=0
    for attempt in 1 2 3; do
        rm -rf "${target}.tmp"
        extra=()
        (( METADATA_ONLY )) && extra=(--filter=blob:none --no-checkout)
        if timeout 900 git clone -q "${extra[@]}" --branch "${branch}" \
                "${url}" "${target}.tmp" 2>/dev/null; then
            mv "${target}.tmp" "${target}"
            clone_ok=1
            break
        fi
        echo "  attempt ${attempt} failed; retrying"
        rm -rf "${target}.tmp"
        sleep 10
    done

    if (( ! clone_ok )); then
        echo "  FAILED to clone ${url} (${branch})"
        FAIL=$((FAIL + 1))
        continue
    fi

    got="$(git -C "${target}" rev-parse HEAD)"
    if [[ "${got}" == "${want}" ]]; then
        echo "  OK HEAD ${got}"
    else
        echo "  MISMATCH: HEAD ${got}, expected ${want}"
        FAIL=$((FAIL + 1))
    fi
done

echo
if (( FAIL > 0 )); then
    echo "RESULT: ${FAIL} clone(s) failed or mismatched. See ${LOG}"
    exit 1
fi
echo "RESULT: all ${#SPECS[@]} clones present at their pinned commits."
