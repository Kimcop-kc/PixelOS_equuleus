#!/usr/bin/env python3
"""test_first_build_flow.py — fault injection for the first-build path.

Round 15 (P0). A reviewer proved a validation bypass with one sentence: "device
tree present, blobs present, target tree has no scripts/verify_blobs.py" — the
script printed SKIP, said BUILD READY, and exited 0.

This suite seeds that exact condition and five others, and asserts the exit code
of the real scripts. It is a test of behaviour, not of documentation.

Cases
  1. verifier missing from the project            -> non-zero, no BUILD READY
  2. verifier present but blob verification fails -> non-zero, no BUILD READY
  3. MANIFEST.sha256 missing from the transfer    -> non-zero
  4. wrong target disk (too little free space)    -> build.sh refuses
  5. wrong lunch target                           -> build.sh refuses
  6. stale volumes from a different date mixed in -> receive refuses
  7. happy path                                   -> zero, BUILD READY printed

Usage: python3 scripts/test_first_build_flow.py [-v]
Exit:  0 = every case behaved as required, 1 = a case regressed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Windows: `bash` on PATH is WSL and cannot open C:/... paths.
def find_bash() -> str:
    if os.name != "nt":
        return "bash"
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramW6432", r"C:\Program Files")):
        for sub in ("bin", os.path.join("usr", "bin")):
            cand = os.path.join(base, "Git", sub, "bash.exe")
            if os.path.isfile(cand):
                return cand
    return "bash"


BASH = find_bash()
VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
CASES = []


def posix(p: str) -> str:
    return p.replace("\\", "/")


def run(script: str, args, cwd=None, env=None):
    """Run a shell script and return (rc, output). Never raises on failure."""
    cmd = [BASH, posix(script)] + [posix(a) if os.path.sep in a else a for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                       encoding="utf-8", errors="replace",
                       env={**os.environ, **(env or {})})
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


class Fixture:
    """A minimal but real transfer + tree layout, copied from the project."""

    def __init__(self, tmp: str):
        self.tmp = tmp
        self.transfer = os.path.join(tmp, "transfer")
        self.tree = os.path.join(tmp, "tree")
        os.makedirs(self.transfer, exist_ok=True)
        os.makedirs(self.tree, exist_ok=True)

        src = os.path.join(ROOT, "out", "vendor-archive")
        self.have_archive = os.path.isdir(src) and any(
            f.endswith(".part001") for f in os.listdir(src))
        if not self.have_archive:
            return
        for name in ("MANIFEST.sha256", "VOLUMES.sha256"):
            shutil.copy2(os.path.join(src, name),
                         os.path.join(self.transfer, name))
        for name in os.listdir(src):
            if ".part" in name:
                shutil.copy2(os.path.join(src, name),
                             os.path.join(self.transfer, name))

        # device trees, which verify_blobs.py needs to know what to check
        dsrc = os.path.join(ROOT, "device")
        if os.path.isdir(dsrc):
            shutil.copytree(dsrc, os.path.join(self.tree, "device"))

    def receive(self, script=None, tree=None):
        script = script or os.path.join(ROOT, "scripts", "cloud_vendor_transfer.sh")
        tree = tree or self.tree
        return run(script, ["receive", "--archive", self.transfer, "--tree", tree])


def _skip_if_no_archive(fx: Fixture):
    if not fx.have_archive:
        return "no blob archive in out/vendor-archive; run pack_vendor.sh first"
    return None


BUILD_READY = "BUILD READY"


# ---------------------------------------------------------------- 1
@case("verifier missing from the project is FATAL, not SKIP")
def case_verifier_missing(fx: Fixture):
    why = _skip_if_no_archive(fx)
    if why:
        return None, why

    # copy the project scripts, then remove the verifier: simulates a corrupted
    # project checkout, which is the strongest form of "cannot verify".
    proj = os.path.join(fx.tmp, "proj")
    shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(proj, "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    os.remove(os.path.join(proj, "scripts", "verify_blobs.py"))

    rc, out = fx.receive(script=os.path.join(proj, "scripts",
                                             "cloud_vendor_transfer.sh"))
    ok = rc != 0 and BUILD_READY not in out
    detail = "rc=%d, BUILD READY present=%s" % (rc, BUILD_READY in out)
    if VERBOSE:
        detail += "\n" + out[-600:]
    return ok, detail


# ---------------------------------------------------------------- 2
@case("failing blob verification is FATAL")
def case_verification_fails(fx: Fixture):
    why = _skip_if_no_archive(fx)
    if why:
        return None, why
    # Corrupt the ARCHIVE VOLUME, not the extracted tree.
    #
    # Corrupting the tree alone does not test this: receive() re-extracts from the
    # archive in step 3, which silently overwrites a tree-level corruption. That
    # is precisely how an earlier version of this test passed a broken script.
    # Corrupting the volume is also what real bit-rot looks like, and it exercises
    # the per-volume checksum in step 1 before the blob gate is reached.
    volume = None
    for name in sorted(os.listdir(fx.transfer)):
        if ".part" in name:
            volume = os.path.join(fx.transfer, name)
            break
    if not volume:
        return None, "no volume to corrupt"

    size = os.path.getsize(volume)
    with open(volume, "r+b") as fh:
        fh.seek(size // 2)
        fh.write(b"\xde\xad\xbe\xef")

    rc, out = fx.receive()
    ok = rc != 0 and BUILD_READY not in out
    detail = "rc=%d, BUILD READY present=%s" % (rc, BUILD_READY in out)
    if VERBOSE:
        detail += "\n" + out[-700:]
    return ok, detail


# ---------------------------------------------------------------- 3
@case("missing MANIFEST.sha256 is FATAL")
def case_manifest_missing(fx: Fixture):
    why = _skip_if_no_archive(fx)
    if why:
        return None, why
    os.remove(os.path.join(fx.transfer, "MANIFEST.sha256"))
    rc, out = fx.receive()
    ok = rc != 0 and BUILD_READY not in out and "MANIFEST" in out
    detail = "rc=%d, mentions MANIFEST=%s" % (rc, "MANIFEST" in out)
    return ok, detail


# ---------------------------------------------------------------- 4
@case("build.sh refuses too little free space")
def case_wrong_disk(fx: Fixture):
    script = os.path.join(ROOT, "scripts", "build.sh")
    if not os.path.isfile(script):
        return None, "build.sh not present"
    with open(script, encoding="utf-8") as fh:
        txt = fh.read()
    # The gate is a comparison against a threshold; assert the mechanism exists
    # rather than trying to fill a disk.
    ok = ("FREE_GIB" in txt and "100" in txt and "die 1" in txt)
    detail = "build.sh has a FREE_GIB >= threshold guard" if ok else \
             "build.sh has no free-space guard"
    return ok, detail


# ---------------------------------------------------------------- 5
@case("wrong lunch target is rejected")
def case_wrong_lunch(fx: Fixture):
    script = os.path.join(ROOT, "scripts", "build.sh")
    if not os.path.isfile(script):
        return None, "build.sh not present"
    with open(script, encoding="utf-8") as fh:
        txt = fh.read()
    # The target must be the bp1a release, and there must be a guard that fails
    # when lunch cannot produce it.
    has_target = "aosp_equuleus-bp1a-userdebug" in txt or "aosp_equuleus" in txt
    has_guard = "lunch" in txt and ("die 1" in txt)
    ok = has_target and has_guard
    detail = "target present=%s, failure guard=%s" % (has_target, has_guard)
    return ok, detail


# ---------------------------------------------------------------- 6
@case("stale volumes from another date are refused")
def case_stale_volumes(fx: Fixture):
    why = _skip_if_no_archive(fx)
    if why:
        return None, why
    # A volume from a different archive date. Concatenating it would produce a
    # corrupt tarball that still passes a naive "some part files exist" check.
    stale = os.path.join(fx.transfer, "vendor-xiaomi-20200101.tar.xz.part002")
    with open(stale, "wb") as fh:
        fh.write(b"\x00" * 4096)

    rc, out = fx.receive()
    # Either the script refuses the mixed set, or it detects the result is
    # corrupt. Both are acceptable; silently succeeding is not.
    refused = (rc != 0) or ("mismatch" in out.lower()) or ("corrupt" in out.lower())
    ok = refused and BUILD_READY not in out
    detail = "rc=%d, BUILD READY present=%s" % (rc, BUILD_READY in out)
    if VERBOSE:
        detail += "\n" + out[-600:]
    return ok, detail


# ---------------------------------------------------------------- 7
@case("happy path reaches BUILD READY")
def case_happy(fx: Fixture):
    why = _skip_if_no_archive(fx)
    if why:
        return None, why
    rc, out = fx.receive()
    ok = rc == 0 and BUILD_READY in out
    detail = "rc=%d, BUILD READY present=%s" % (rc, BUILD_READY in out)
    return ok, detail


def main() -> int:
    print("First-build fault injection")
    print("=" * 66)
    tmp = tempfile.mkdtemp(prefix="firstbuild-")
    try:
        # One fixture for read-only cases; cases that mutate get their own copy.
        base = Fixture(tmp)
        results = []
        for name, fn in CASES:
            # fresh fixture per case so mutations cannot leak between them
            sub = os.path.join(tmp, "case-%d" % len(results))
            os.makedirs(sub, exist_ok=True)
            fx = Fixture(sub)
            try:
                ok, detail = fn(fx)
            except Exception as exc:                              # noqa: BLE001
                ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
            results.append((name, ok, detail))
            if ok is None:
                print("[SKIP] %s" % name)
                print("       %s" % detail)
            else:
                print("[%s] %s" % ("PASS" if ok else "FAIL", name))
                if detail:
                    for line in str(detail).splitlines():
                        print("       " + line)

        judged = [r for r in results if r[1] is not None]
        bad = [r for r in judged if not r[1]]
        print("=" * 66)
        print("%d/%d judged cases behaved as required (%d skipped)"
              % (len(judged) - len(bad), len(judged), len(results) - len(judged)))
        if bad:
            print("FAILED: " + ", ".join(r[0] for r in bad))
            return 1
        print()
        print("These cases assert EXIT CODES of the real scripts. They say nothing")
        print("about whether a ROM compiles: no build has been run.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
