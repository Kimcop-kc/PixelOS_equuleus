#!/usr/bin/env bash
#
# host-preflight.sh — Stage 1 of 2. ENVIRONMENT ONLY.
#
# Answers exactly one question: "is this machine capable of hosting a PixelOS
# fifteen build?" It deliberately does NOT look for a source tree, patches,
# local manifests, or proprietary blobs. You can and should run this on a fresh
# ECS instance *before* paying for storage or downloading 165 GiB.
#
# Stage 2 (build-preflight.sh) runs after repo sync + patches + blob extraction.
#
# Usage:
#   scripts/host-preflight.sh [--tree /path/where/sources/will/go]
#   scripts/host-preflight.sh --network-only
#
# --network-only
#   Check ONLY connectivity and TLS: github.com, gitlab.com,
#   android.googlesource.com, real git-over-HTTPS, and the proxy/CA setup.
#   CPU, RAM, disk and filesystem are NOT examined, so this runs anywhere —
#   including a tiny pay-as-you-go ECS instance, a container, or a laptop —
#   to answer the one question that cannot be answered offline: can this
#   network reach the sources at all?  Exit code reflects network health only.
#
# Exit codes: 0 = adequate (warnings allowed), 1 = at least one FAIL.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TREE=""
NETWORK_ONLY=0
MIN_FREE_GIB="${MIN_FREE_GIB:-400}"
while (($#)); do
    case "$1" in
        --tree) TREE="${2:-}"; shift 2 ;;
        --tree=*) TREE="${1#*=}"; shift ;;
        --network-only) NETWORK_ONLY=1; shift ;;
        -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
# With no --tree, judge the filesystem the sources will land on.
TREE="${TREE:-${PROJECT_DIR}}"

LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/host-preflight-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

FAILURES=0
WARNINGS=0
pass() { printf '[PASS] %s\n' "$*"; }
info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

# resolve a python that actually runs (Windows ships a dead python3 shim)
PYTHON=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 && "${cand}" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        PYTHON="${cand}"; break
    fi
done

if (( NETWORK_ONLY )); then
    echo "=============================================================="
    echo " NETWORK-ONLY preflight  (no CPU / RAM / disk checks)"
    echo " host    : $(uname -s) $(uname -r) $(uname -m)"
    echo " log     : ${LOG_FILE}"
    echo " started : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "=============================================================="
    echo "Answers one question: can this network reach the source hosts?"
    echo "Resource checks are skipped by design, so this runs on a minimum-size"
    echo "instance. It does NOT mean the host can build anything."
else
    echo "=============================================================="
    echo " STAGE 1/2  host-preflight  (environment only)"
    echo " host    : $(uname -s) $(uname -r) $(uname -m)"
    echo " target  : ${TREE}"
    echo " log     : ${LOG_FILE}"
    echo " started : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "=============================================================="
    echo "This stage checks NOTHING about sources, patches or blobs."
    echo "It is safe to run on a brand-new instance with an empty disk."
fi

# Sections 1-4 are RESOURCE checks. --network-only skips all of them so the
# mode works on a minimum-size instance and reports network health alone.
if (( ! NETWORK_ONLY )); then
    # ---------------------------------------------------------------- 1. platform
    echo
    echo "--- 1. platform ----------------------------------------------------------"
    case "$(uname -m)" in
        x86_64|amd64) pass "x86_64 host (required: AOSP ships no ARM host toolchain)" ;;
        *)            fail "x86_64 host required for AOSP builds, got $(uname -m)" ;;
    esac

    if [[ "$(uname -s)" == "Darwin" ]]; then
        fail "macOS cannot build AOSP (case-insensitive FS + no ELF toolchain); use Linux x86_64"
    fi

    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        info "distribution: ${PRETTY_NAME:-unknown}"
        case "${ID:-}" in
            ubuntu) pass "Ubuntu detected (the distribution PixelOS documents)" ;;
            debian) pass "Debian-family detected; Ubuntu is what upstream documents" ;;
            *)      warn "'${ID:-unknown}' is untested upstream; Ubuntu 22.04/24.04 recommended" ;;
        esac
    else
        warn "cannot read /etc/os-release (expected on non-systemd/container hosts)"
    fi

    # --------------------------------------------------------------- 2. toolchain
    echo
    echo "--- 2. toolchain ---------------------------------------------------------"
    MISSING=0
    for cmd in git curl python3 java unzip zip bc bison flex make gcc g++ lz4 rsync; do
        if command -v "${cmd}" >/dev/null 2>&1; then
            printf '  [ok] %s\n' "${cmd}"
        else
            printf '  [MISSING] %s\n' "${cmd}"
            MISSING=$((MISSING + 1))
        fi
    done
    if (( MISSING == 0 )); then
        pass "all required build tools present"
    else
        fail "${MISSING} required tool(s) missing (apt-get install the names above)"
    fi

    if command -v java >/dev/null 2>&1; then
        JAVA_MAJOR="$(java -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -1)"
        if [[ -n "${JAVA_MAJOR}" ]] && (( JAVA_MAJOR >= 17 )); then
            pass "JDK ${JAVA_MAJOR} (Android 15 needs >= 17; PixelOS documents 21)"
        else
            fail "JDK ${JAVA_MAJOR:-unknown} too old; Android 15 needs >= 17"
        fi
    fi

    if command -v repo >/dev/null 2>&1; then
        pass "repo tool present: $(command -v repo)"
    else
        fail "repo tool missing — required for the sync stage, not for this check itself"
    fi

    if command -v ccache >/dev/null 2>&1; then
        pass "ccache present (optional, speeds up rebuilds)"
    else
        info "ccache absent (optional)"
    fi

    # --------------------------------------------------------------- 3. resources
    echo
    echo "--- 3. CPU / RAM ---------------------------------------------------------"
    CPUS="$(nproc 2>/dev/null || echo 1)"
    info "logical CPUs: ${CPUS}"
    if (( CPUS >= 16 )); then
        pass "${CPUS} vCPU meets the 16-vCPU recommendation"
    elif (( CPUS >= 8 )); then
        warn "${CPUS} vCPU is below the 16-vCPU recommendation; expect ~2x wall time"
    else
        fail "${CPUS} vCPU is too few for an AOSP build"
    fi

    if [[ -r /proc/meminfo ]]; then
        MEM_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
        MEM_GIB=$(( MEM_KB / 1024 / 1024 ))
        info "RAM: ${MEM_GIB} GiB"
        if (( MEM_GIB >= 60 )); then
            pass "${MEM_GIB} GiB RAM meets the ~64 GiB recommendation"
        elif (( MEM_GIB >= 24 )); then
            warn "${MEM_GIB} GiB RAM is below 64 GiB; link steps may OOM-kill"
        else
            fail "${MEM_GIB} GiB RAM is too small (16 GiB generally cannot finish)"
        fi
        SWAP_KB="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
        SWAP_GIB=$(( SWAP_KB / 1024 / 1024 ))
        if (( SWAP_GIB >= 4 )); then
            pass "${SWAP_GIB} GiB swap configured"
        else
            warn "little/no swap (${SWAP_GIB} GiB); a single link spike can kill the build"
        fi
    fi

    # ------------------------------------------------------------------ 4. storage
    echo
    echo "--- 4. disk and filesystem ----------------------------------------------"
    if [[ -d "${TREE}" ]]; then
        PROBE="${TREE}"
    else
        PROBE="$(dirname "${TREE}")"
        info "${TREE} does not exist yet; probing its parent ${PROBE}"
    fi
    if [[ -d "${PROBE}" ]]; then
        FREE_GIB="$(df -Pk "${PROBE}" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
        TOTAL_GIB="$(df -Pk "${PROBE}" | awk 'NR==2 {printf "%d", $2/1024/1024}')"
        FS_TYPE="$(df -PTk "${PROBE}" | awk 'NR==2 {print $2}')"
        info "filesystem: ${FS_TYPE}, ${TOTAL_GIB} GiB total, ${FREE_GIB} GiB free"
        if (( FREE_GIB >= MIN_FREE_GIB )); then
            pass "${FREE_GIB} GiB free (>= ${MIN_FREE_GIB} GiB)"
        elif (( FREE_GIB >= 250 )); then
            warn "${FREE_GIB} GiB free is tight for tree + .repo + out/ (recommend 400+)"
        else
            fail "${FREE_GIB} GiB free is not enough (need >= ${MIN_FREE_GIB} GiB)"
        fi
        case "${FS_TYPE}" in
            ext4|xfs|btrfs) pass "${FS_TYPE} is case-sensitive (required)" ;;
            *)              fail "${FS_TYPE} is not case-sensitive; AOSP will fail confusingly" ;;
        esac
    fi

fi

# ------------------------------------------------------------------ 5. network
echo
echo "--- 5. network reachability ---------------------------------------------"
probe() {
    local label="$1" url="$2" out
    if out="$(curl --location --silent --show-error --max-time 20 \
                   --output /dev/null --write-out '%{http_code}' "${url}" 2>&1)"; then
        case "${out}" in
            2*|3*) pass "${label}: HTTP ${out}" ;;
            *)     fail "${label}: HTTP ${out} from ${url}" ;;
        esac
    else
        fail "${label}: unreachable (${out:-no output})"
    fi
}
# android.googlesource.com is the hard requirement: repo fetches AOSP from it.
probe "AOSP (repo backend)" "https://android.googlesource.com/"
probe "GitHub"             "https://github.com/"
probe "GitLab (vendor/gms)" "https://gitlab.com/"
probe "GitHub API"         "https://api.github.com/rate_limit"

# A plain HTTPS 200 is not proof that `repo` can fetch: repo speaks git
# protocol over HTTPS against several distinct hosts. Test each one for real.
git_probe() {
    local label="$1" url="$2" ref="${3:-HEAD}" err
    if ! command -v git >/dev/null 2>&1; then
        fail "git is not installed; cannot test ${label}"
        return
    fi
    if err="$(GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true \
              timeout 60 git ls-remote --heads "${url}" "${ref}" 2>&1)" \
            && [[ -n "${err}" ]]; then
        pass "${label}: git ls-remote OK (${ref})"
    else
        fail "${label}: git ls-remote failed for ${url} (${err:-empty result})"
    fi
}

# The three hosts repo actually fetches from.
git_probe "git: PixelOS manifest"   "https://github.com/PixelOS-AOSP/manifest"            "fifteen"
git_probe "git: AOSP mirror (CAF)"  "https://github.com/LineageOS/android_device_xiaomi_equuleus" "lineage-22.2"
git_probe "git: GitLab (vendor/gms)" "https://gitlab.com/PixelOS-AOSP/vendor_gms-15"     "fifteen"

# android.googlesource.com does not serve the git protocol the way GitHub does,
# but `repo` fetches hundreds of projects from it, so test a real fetch path.
if command -v git >/dev/null 2>&1; then
    AOSP_TEST_URL="https://android.googlesource.com/platform/manifest"
    if AOSP_ERR="$(GIT_TERMINAL_PROMPT=0 timeout 90 git ls-remote --heads \
            "${AOSP_TEST_URL}" 2>&1)" && [[ -n "${AOSP_ERR}" ]]; then
        pass "git: android.googlesource.com reachable (platform/manifest)"
    else
        fail "git: android.googlesource.com unreachable (${AOSP_ERR:-no output}). \
repo sync CANNOT work without it."
    fi
fi

# --------------------------------------------------------------- 6. proxies
echo
echo "--- 6. proxy / TLS sanity -----------------------------------------------"
PROXY_SET=0
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    if [[ -n "${!var:-}" ]]; then info "${var}=${!var}"; PROXY_SET=1; fi
done
if (( PROXY_SET == 0 )); then
    info "no proxy configured (direct egress)"
fi

TLS_ERR="$(curl --silent --show-error --max-time 20 \
               --output /dev/null --write-out '%{http_code}' \
               https://android.googlesource.com/ 2>&1)" || true
case "${TLS_ERR}" in
    2*|3*)
        pass "TLS to android.googlesource.com succeeds (HTTP ${TLS_ERR})" ;;
    *"certificate"*|*"SSL"*|*"CA"*)
        fail "TLS verification FAILED: ${TLS_ERR}. If this network intercepts TLS, \
repo will fail; do not disable verification, install the correct CA instead." ;;
    *)
        fail "TLS to android.googlesource.com failed: ${TLS_ERR:-no output}" ;;
esac

# git must agree with curl about TLS, because repo uses git's transport.
if command -v git >/dev/null 2>&1; then
    if GIT_SSL_ERR="$(GIT_TERMINAL_PROMPT=0 timeout 45 git ls-remote \
            https://android.googlesource.com/platform/manifest HEAD 2>&1)" \
            && [[ -n "${GIT_SSL_ERR}" ]]; then
        pass "git TLS to android.googlesource.com succeeds"
    else
        fail "git TLS to android.googlesource.com failed: ${GIT_SSL_ERR:-no output}"
    fi
fi

echo
echo "=============================================================="
if (( NETWORK_ONLY )); then
    if (( FAILURES > 0 )); then
        echo "RESULT: NETWORK NOT READY — ${FAILURES} failure(s), ${WARNINGS} warning(s)"
        echo "The source hosts are not reachable from here, so repo sync would fail."
        echo "Nothing was checked about CPU, RAM or disk (--network-only)."
        exit 1
    fi
    echo "RESULT: NETWORK READY — 0 failures, ${WARNINGS} warning(s)"
    echo "All required source hosts answered over git/HTTPS."
    echo "This says NOTHING about CPU, RAM, disk or whether the host can build."
    echo "Re-run without --network-only on the real build instance."
    echo "log: ${LOG_FILE}"
    echo "=============================================================="
    exit 0
fi

if (( FAILURES > 0 )); then
    echo "RESULT: HOST NOT READY — ${FAILURES} failure(s), ${WARNINGS} warning(s)"
    echo "Fix the [FAIL] items before renting storage or starting a sync."
    exit 1
fi
echo "RESULT: HOST READY — 0 failures, ${WARNINGS} warning(s)"
echo "Next: repo init/sync, apply patches, extract blobs, then"
echo "      scripts/build-preflight.sh  (stage 2/2)"
echo "log: ${LOG_FILE}"
echo "=============================================================="
exit 0
