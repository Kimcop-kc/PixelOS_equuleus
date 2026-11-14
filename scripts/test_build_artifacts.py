#!/usr/bin/env python3
"""test_build_artifacts.py — fault-injection tests for build.sh's artifact gate.

The review found that build.sh only asked "does a PixelOS_*.zip exist?", which
happily accepts a leftover zip from a previous build. These tests extract the
artifact-verification logic and drive it against synthetic `out/` directories,
asserting on exit status:

  1. stale zip only (mtime older than the build start)      -> reject
  2. fresh zip + fresh recovery.img, correct assert         -> accept
  3. fresh zip asserting a DIFFERENT device                 -> reject
  4. fresh zip with no device assertion at all              -> reject
  5. fresh zip that is a corrupt archive                    -> reject
  6. fresh zip + no recovery.img                            -> reject
  7. two zips, one stale: the FRESH one must be chosen      -> accept + pick right file

Usage: python scripts/test_build_artifacts.py [-v]
Exit:  0 = all cases behaved as required, 1 = regression.
"""
import io
import itertools
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD_SH = os.path.join(HERE, "build.sh")


# --------------------------------------------------------------------------
# A minimal harness that exercises the real logic from build.sh.
# We cannot run the whole script (it needs a full AOSP tree), so we extract the
# artifact block and run it with the same shell options.
# --------------------------------------------------------------------------

def find_posix_bash() -> str:
    """Locate a Git-bash/Cygwin bash, NOT the WSL one.

    `subprocess.run(["bash", ...])` picks up C:\\Windows\\System32\\bash.exe
    (the WSL launcher) on this host. That bash sees drives as /mnt/c/... and
    cannot write to the Windows path we hand it, so `mkdir` fails with
    "Permission denied" even though the same path is writable from Git Bash.
    """
    candidates = [
        "C:/Program Files/Git/bin/bash.exe",
        "C:/Program Files/Git/usr/bin/bash.exe",
        "C:/Program Files (x86)/Git/bin/bash.exe",
        "/usr/bin/bash",
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            probe = subprocess.run([cand, "-c", "echo $OSTYPE; pwd"],
                                   capture_output=True, text=True)
            if probe.returncode == 0 and "mnt/c" not in probe.stdout:
                return cand
    raise RuntimeError("no POSIX (non-WSL) bash found")


def to_posix(path: str) -> str:
    """`C:\\x` -> `/c/x`.

    Git-bash resolves `/c/...` for directories it created itself; handing it a
    `C:/...` string as an argument loses the backslashes on Windows.
    """
    p = os.path.abspath(path)
    if os.name != "nt":
        return p.replace(os.sep, "/")
    drive, rest = os.path.splitdrive(p)
    if not drive:
        return p.replace(os.sep, "/")
    return "/" + drive.rstrip(":").lower() + "/" + rest.replace(os.sep, "/").lstrip("/")


_COUNTER = itertools.count()
BASH = None  # resolved in main()


def artifact_block() -> str:
    txt = io.open(BUILD_SH, encoding="utf-8").read()
    start = txt.find('step "verify artifacts"')
    end = txt.find('step "result"', start)
    assert start > 0 and end > start, "cannot locate the artifact block in build.sh"
    return txt[start:end]


ZIP_HELPER = r'''#!/usr/bin/env python3
import os, sys, zipfile
out = os.environ["OUT_DIR"]; name = os.environ["ZIP_NAME"]
dev = os.environ["ZIP_DEVICE"]; style = os.environ["ZIP_STYLE"]
corrupt = os.environ.get("ZIP_CORRUPT", "no")
path = os.path.join(out, name)
os.makedirs(out, exist_ok=True)
if corrupt == "corrupt":
    with open(path, "wb") as fh:
        fh.write(b"this is not a zip at all")
    sys.exit(0)
with zipfile.ZipFile(path, "w") as zf:
    zf.writestr("system/build.prop", "ro.product.device=equuleus\n")
    legacy_dev = dev
    if dev != "-":
        if style in ("modern", "both", "metadata_ok_legacy_not_equuleus"):
            zf.writestr("META-INF/com/android/metadata",
                        "post-build=PixelOS/equuleus/equuleus:15/x/y\n"
                        "pre-device=%s\n" % dev)
        if style == "both":
            zf.writestr("META-INF/com/google/android/updater-script",
                        'assert(getprop("ro.product.device") == "%s");\n' % dev)
        elif style == "metadata_ok_legacy_not_equuleus":
            zf.writestr("META-INF/com/google/android/updater-script",
                        'assert(getprop("ro.product.device") == "not_equuleus");\n')
        elif style == "legacy":
            zf.writestr("META-INF/com/google/android/updater-script",
                        'assert(getprop("ro.product.device") == "%s");\n' % dev)
sys.exit(0)
'''

SETUP_SNIPPET = """
# Everything (tree, out/, zips) is created BY BASH so that no freshly-created
# directory has to be discovered by a different process. Creating dirs in
# Python and stat-ing them from bash proved unreliable on Windows.
TREE="$FIXTURE_ROOT/tree"
OUT="$TREE/out/target/product/equuleus"
mkdir -p "$TREE/build" "$OUT" || { echo "SETUP FAILED: cannot create $OUT" >&2; exit 90; }
: > "$TREE/build/envsetup.sh"

seed_stale_recovery_fresh_zip() {
    # The P1-1 scenario: the zip is genuinely from this build, but recovery.img
    # was produced by an earlier one. Crucially it is NEWER than
    # build/envsetup.sh, which is what defeated the old AND-condition.
    make_zip PixelOS_new.zip equuleus modern
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 600 ))
    # envsetup.sh is old; recovery sits BETWEEN envsetup and build start
    touch -d "@$((STARTED - 3600))" "$TREE/build/envsetup.sh"
    touch -d "@$((STARTED - 300))"  "$OUT/recovery.img"
}

seed_legacy_not_equuleus() {
    # The P1-2 scenario: a legacy assertion naming "not_equuleus" used to pass
    # because the regex was `assert.*equuleus`.
    make_zip PixelOS_new.zip not_equuleus legacy
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_legacy_substring_equuleus() {
    # Same class, different shape: the codename merely CONTAINS "equuleus".
    make_zip PixelOS_new.zip equuleus_pro legacy legacy
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_metadata_not_equuleus() {
    # Metadata exists and declares the wrong device: strict equality required.
    make_zip PixelOS_new.zip not_equuleus modern
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_metadata_missing_but_legacy_ok() {
    # No metadata at all: PixelOS 15 must not fall back to a legacy assert.
    make_zip PixelOS_legacyonly.zip equuleus legacy
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

# Archives are written by Python (zipfile) because `zip` may not be installed;
# bash only creates directories, which is what needed to stay in this process.
make_zip() {   # make_zip <name> <device|-> <modern|legacy> [corrupt]
    local name="$1" dev="$2" style="$3" corrupt="${4:-no}"
    PYTHON_BIN="$PYTHON_BIN" OUT_DIR="$OUT" ZIP_NAME="$name" \
    ZIP_DEVICE="$dev" ZIP_STYLE="$style" ZIP_CORRUPT="$corrupt" \
        "$PYTHON_BIN" "$HELPER_PY" || return 1
}

seed_stale_only() {
    make_zip PixelOS_old.zip equuleus modern
    touch -d '2 hours ago' "$OUT/PixelOS_old.zip"
    STARTED=$(( $(date +%s) - 3600 ))
}

seed_fresh_ok() {
    make_zip PixelOS_new.zip equuleus modern
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_wrong_device() {
    make_zip PixelOS_new.zip dipper modern
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_no_assert() {
    make_zip PixelOS_new.zip - modern
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_corrupt() {
    make_zip PixelOS_new.zip equuleus modern corrupt
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_no_recovery() {
    make_zip PixelOS_new.zip equuleus modern
    STARTED=$(( $(date +%s) - 60 ))
}

seed_two_zips() {
    make_zip PixelOS_aaa.zip dipper modern
    touch -d '2 hours ago' "$OUT/PixelOS_aaa.zip"
    make_zip PixelOS_zzz.zip equuleus modern
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_legacy() {
    # A valid PixelOS 15 OTA: metadata with the right pre-device, PLUS a legacy
    # updater-script whose device assertion also says equuleus. Both must agree.
    make_zip PixelOS_new.zip equuleus both
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}

seed_metadata_ok_legacy_wrong() {
    # metadata is correct but the legacy assertion contradicts it: reject,
    # because a contradictory OTA must not be trusted.
    make_zip PixelOS_new.zip equuleus metadata_ok_legacy_not_equuleus
    printf 'recovery' > "$OUT/recovery.img"
    STARTED=$(( $(date +%s) - 60 ))
}
"""

CASES = [
    # --- original eight (all retained) ---
    ("stale zip only -> reject",            "seed_stale_only",   False),
    ("fresh zip+recovery, correct device",  "seed_fresh_ok",     True),
    ("fresh zip asserting different device", "seed_wrong_device", False),
    ("fresh zip with no device assertion",  "seed_no_assert",    False),
    ("fresh zip is a corrupt archive",      "seed_corrupt",      False),
    ("fresh zip but no recovery.img",       "seed_no_recovery",  False),
    ("two zips, stale one sorts first",     "seed_two_zips",     True),
    ("metadata + agreeing legacy assert",   "seed_legacy",       True),
    ("metadata ok but legacy contradicts",  "seed_metadata_ok_legacy_wrong", False),
    # --- round 8: the two failures the reviewer reproduced ---
    ("fresh zip + STALE recovery -> reject", "seed_stale_recovery_fresh_zip", False),
    ("legacy assert not_equuleus -> reject", "seed_legacy_not_equuleus",      False),
    # --- same class, extra shapes ---
    ("legacy assert equuleus_pro -> reject", "seed_legacy_substring_equuleus", False),
    ("metadata pre-device wrong -> reject",  "seed_metadata_not_equuleus",     False),
    ("legacy-only zip, no metadata -> reject", "seed_metadata_missing_but_legacy_ok", False),
]


def run_case(name, seed_fn, expect_accept, verbose):
    """Build the fixture *inside bash*, then run the artifact block in the same
    shell. No Windows path is marshalled as an argv element (that loses
    backslashes) and no directory crosses a process boundary."""
    # Do NOT let Python create the fixture root: a directory made by the Python
    # process is not reliably writable by the separate bash process on this
    # host (mkdir -> Permission denied). Give bash a path and let IT create the
    # tree. We only reserve a unique, non-existent name.
    # The OS temp directory is not writable by the bash process on this host
    # (mkdir -> Permission denied), so build the fixture under the project's
    # work/ directory, which both processes can write.
    base = os.path.join(ROOT, "work", "_arttest")
    os.makedirs(base, exist_ok=True)
    unique = "arttest-%d-%d" % (os.getpid(), next(_COUNTER))
    root = to_posix(os.path.join(base, unique))
    tmp = os.path.join(base, unique)
    try:
        block = artifact_block()
        helper_path = os.path.join(base, "zip_helper_%s.py" % unique)
        with io.open(helper_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ZIP_HELPER)
        script = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'FIXTURE_ROOT="{root}"\n'
            f'PYTHON_BIN="{sys.executable.replace(os.sep, "/")}"\n'
            f'HELPER_PY="{helper_path}"\n'
            + SETUP_SNIPPET
            + f"\n{seed_fn}\n"
            + f'TREE="$FIXTURE_ROOT/tree"\n'
            "DEVICE=equuleus\n"
            'BUILD_STARTED_EPOCH="$STARTED"\n'
            'LUNCH_TARGET="aosp_equuleus-bp1a-userdebug"\n'
            "die() { local rc=\"$1\"; shift; echo \"DIE rc=${rc}: $*\" >&2; exit \"${rc}\"; }\n"
            "step() { echo \"== $*\"; }\n"
            + block
            + "\necho ACCEPTED\n"
        )
        # bytes, not str: Windows text-mode stdin corrupts `set -o pipefail`.
        proc = subprocess.run([BASH, "-s"], input=script.encode("utf-8"),
                              capture_output=True)
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        if proc.returncode in (126, 127):
            return (False, name, f"test bug: harness exited {proc.returncode}", out + err)
        accepted = "ACCEPTED" in out
        ok = accepted == expect_accept
        detail = (f"exit={proc.returncode} accepted={accepted} "
                  f"expected={'accept' if expect_accept else 'reject'}")
        return ok, name, detail, out + err
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    global BASH
    verbose = "-v" in sys.argv
    try:
        BASH = find_posix_bash()
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    print(f"using bash: {BASH}")
    if not os.path.isfile(BUILD_SH):
        print(f"FATAL: {BUILD_SH} not found", file=sys.stderr)
        return 2

    print("=" * 68)
    print("build.sh artifact gate — fault-injection (asserting ACCEPT/REJECT)")
    print("=" * 68)
    failures = []
    for name, setup, expect in CASES:
        ok, label, detail, output = run_case(name, setup, expect, verbose)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:<40} {detail}")
        if not ok:
            failures.append((label, detail, output))
        elif verbose:
            for line in output.splitlines():
                if line.strip():
                    print(f"        | {line}")

    print()
    if failures:
        print(f"{len(failures)} CASE(S) REGRESSED:")
        for label, detail, output in failures:
            print(f"\n--- {label} ({detail})")
            for line in output.splitlines()[-15:]:
                print(f"    {line}")
        return 1
    print(f"all {len(CASES)} cases behaved as required")
    return 0


if __name__ == "__main__":
    sys.exit(main())
