#!/usr/bin/env python3
"""test_verify_blobs.py — fault-injection tests for verify_blobs.py.

The review found that verify_blobs.py reported a SONAME mismatch yet still
returned exit 0. A test suite that cannot detect that is worthless, so this
file drives the real script as a subprocess and asserts on its **exit code**,
not on text that happens to appear in its output.

Covered cases (required by the review):
  1. file missing
  2. wrong SONAME (FIX_SONAME never ran)
  3. wrong hash (content does not match the pin)
  4. correct file (must pass, exit 0)

Plus the hash-semantics cases that mirror upstream extract-utils:
  5. fixup hash declared with no fixup function  -> FAIL (upstream BAD_FIXUP)
  6. only a pre-fixup hash with a fixup          -> UNVERIFIABLE, not success
  7. fixup hash matching the installed file      -> OK
  8. non-ELF file carrying FIX_SONAME            -> FAIL
  9. ELF with no .dynamic (cannot verify)        -> FAIL, not silent pass

Usage:
    python scripts/test_verify_blobs.py [-v]

Exit codes: 0 = all cases behaved as required, 1 = at least one case regressed.
"""
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERIFIER = os.path.join(HERE, "verify_blobs.py")


# --------------------------------------------------------------------------
# Building synthetic ELF objects (no compiler needed, byte-exact control)
# --------------------------------------------------------------------------

def build_elf(soname: str | None, needed=("libc.so",), *, elf64=True,
              with_dynamic=True) -> bytes:
    """Construct a minimal but valid ELF shared object.

    `soname=None` omits DT_SONAME; `with_dynamic=False` omits .dynamic entirely,
    which is the "cannot verify" case.
    """
    dynstr = bytearray(b"\x00")
    offsets = {}
    for s in list(needed) + ([soname] if soname else []):
        if s in offsets:
            continue
        offsets[s] = len(dynstr)
        dynstr += s.encode() + b"\x00"

    shstr = b"\x00.dynstr\x00.dynamic\x00.shstrtab\x00"
    n_dynstr = shstr.index(b".dynstr")
    n_dynamic = shstr.index(b".dynamic")
    n_shstr = shstr.index(b".shstrtab")

    tags = []
    if soname:
        tags.append((14, offsets[soname]))      # DT_SONAME
    for s in needed:
        tags.append((1, offsets[s]))            # DT_NEEDED
    tags.append((5, 0x1000))                    # DT_STRTAB
    tags.append((0, 0))                         # DT_NULL

    if with_dynamic:
        dynamic = b"".join(struct.pack("<qQ", t, v) for t, v in tags)
    else:
        dynamic = b""

    ehsize, shentsize = 64, 64
    off_dynstr = ehsize
    off_dynamic = off_dynstr + len(dynstr)
    off_shstr = off_dynamic + len(dynamic)
    off_sh = off_shstr + len(shstr)

    n_sections = 4  # NULL, .dynstr, .dynamic, .shstrtab
    if not with_dynamic:
        n_sections = 3

    sh = b"\x00" * shentsize
    sh += struct.pack("<IIQQQQIIQQ", n_dynstr, 3, 0, 0x1000,
                      off_dynstr, len(dynstr), 0, 0, 1, 0)
    if with_dynamic:
        sh += struct.pack("<IIQQQQIIQQ", n_dynamic, 6, 0, 0x2000,
                          off_dynamic, len(dynamic), 0, 0, 8, 16)
    sh += struct.pack("<IIQQQQIIQQ", n_shstr, 3, 0, 0,
                      off_shstr, len(shstr), 0, 0, 1, 0)

    ehdr = b"\x7fELF" + bytes([2 if elf64 else 1, 1, 1, 0]) + b"\x00" * 8
    ehdr += struct.pack("<HHIQQQIHHHHHH", 3, 183, 1, 0, 0, off_sh, 0,
                        ehsize, 0, 0, shentsize, n_sections,
                        n_sections - 1)

    return bytes(ehdr) + bytes(dynstr) + dynamic + shstr + sh


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


# --------------------------------------------------------------------------
# Tree construction
# --------------------------------------------------------------------------

def make_tree(tmp: str, equuleus_lines: list[str],
              files: dict[str, bytes]) -> str:
    """Create a fake PixelOS tree with a blob list and installed blobs."""
    tree = os.path.join(tmp, "tree")
    for d in ("device/xiaomi/equuleus", "device/xiaomi/sdm845-common",
              "vendor/xiaomi/equuleus/proprietary", "vendor/xiaomi/sdm845-common/proprietary"):
        os.makedirs(os.path.join(tree, d), exist_ok=True)

    with open(os.path.join(tree, "device/xiaomi/equuleus/proprietary-files.txt"),
              "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(equuleus_lines) + "\n")
    with open(os.path.join(tree, "device/xiaomi/sdm845-common/proprietary-files.txt"),
              "w", encoding="utf-8", newline="\n") as fh:
        fh.write("")

    for rel, data in files.items():
        dst = os.path.join(tree, "vendor/xiaomi/equuleus/proprietary", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(data)
    return tree


def run_verifier(tree: str, extra=()) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, VERIFIER, tree, *extra],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------

def case_missing(tmp, verbose):
    tree = make_tree(tmp, ["vendor/lib64/hw/absent.so"], {})
    rc, out = run_verifier(tree)
    ok = rc == 1
    return ok, "exit 1 for a missing file", rc, out


def case_wrong_soname(tmp, verbose):
    # Installed file's SONAME still says the SOURCE name: the exact symptom of
    # a FIX_SONAME that never ran. This is the bug the review reported.
    data = build_elf(soname="fingerprint.goodix_fod.so")
    line = ("vendor/lib64/hw/fingerprint.goodix_fod.so:"
            "vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so;FIX_SONAME")
    tree = make_tree(tmp, [line],
                     {"vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so": data})
    rc, out = run_verifier(tree)
    ok = rc == 1
    return ok, "exit 1 for a SONAME mismatch (was exit 0 before the fix)", rc, out


def case_wrong_hash(tmp, verbose):
    data = build_elf(soname="libx.so")
    wrong = "0" * 40
    line = f"vendor/lib64/libx.so|{wrong}"
    tree = make_tree(tmp, [line], {"vendor/lib64/libx.so": data})
    rc, out = run_verifier(tree)
    ok = rc == 1
    return ok, "exit 1 for a hash mismatch", rc, out


def case_correct(tmp, verbose):
    data = build_elf(soname="fingerprint.goodix_fod.sdm845.so")
    line = ("vendor/lib64/hw/fingerprint.goodix_fod.so:"
            "vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so;FIX_SONAME")
    tree = make_tree(tmp, [line],
                     {"vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so": data})
    rc, out = run_verifier(tree)
    ok = rc == 0
    return ok, "exit 0 for a correct file", rc, out


def case_fixuphash_without_fixup(tmp, verbose):
    """fixup_hash declared, no fixup function.

    Two sub-cases matter and they must behave differently:

      a) the file already matches fixup_hash -> OK. This is the normal case when
         the source is an already-built ROM: upstream applied the fixup, so the
         installed bytes ARE the post-fixup artefact.
      b) the file does NOT match fixup_hash -> FAIL. The pin can never be
         satisfied, which is what upstream's BAD_FIXUP protects against.
    """
    # (a) matching: must be accepted
    data = build_elf(soname="liby.so")
    line = f"vendor/lib64/liby.so|{sha1(data)}|{sha1(data)}"
    tree = make_tree(tmp, [line], {"vendor/lib64/liby.so": data})
    rc_a, out_a = run_verifier(tree)

    # (b) not matching: must be rejected
    wrong = "0" * 40
    line_b = f"vendor/lib64/libz.so|{sha1(data)}|{wrong}"
    tree_b = os.path.join(tmp, "b")
    os.makedirs(tree_b, exist_ok=True)
    tree_b = make_tree(tree_b, [line_b], {"vendor/lib64/libz.so": data})
    rc_b, out_b = run_verifier(tree_b)

    ok = (rc_a == 0) and (rc_b == 1)
    msgs = []
    if rc_a != 0:
        msgs.append(f"(a) matching fixup_hash should be OK, got rc={rc_a}")
    if rc_b != 1:
        msgs.append(f"(b) mismatching fixup_hash should FAIL, got rc={rc_b}")
    detail = ("matching fixup_hash accepted, mismatching rejected"
              if ok else "; ".join(msgs))
    return ok, detail, (rc_a, rc_b), out_a + out_b


def case_preonly_hash_with_fixup(tmp, verbose):
    # Only the PRE-fixup hash is pinned while a fixup runs. The installed file
    # is post-fixup, so the pin cannot be re-derived -> UNVERIFIABLE, not OK.
    data = build_elf(soname="libz.so")
    line = f"vendor/lib64/libz.so|{sha1(data)};FIX_SONAME"
    tree = make_tree(tmp, [line], {"vendor/lib64/libz.so": data})
    rc, out = run_verifier(tree)
    ok = rc == 3
    ok2 = True
    if verbose:
        print(f"      [verbose] rc={rc} (3 = UNVERIFIABLE)")
    return ok, "exit 3 (UNVERIFIABLE), not 0, for a pre-only hash after a fixup", rc, out


def case_fixuphash_matches(tmp, verbose):
    data = build_elf(soname="libw.so")
    # Hash wrong (pre-fixup unknown), fixup hash correct: upstream checks the
    # fixup hash against the post-fixup file, which is what we have.
    line = f"vendor/lib64/libw.so|{'0'*40}|{sha1(data)};FIX_SONAME"
    tree = make_tree(tmp, [line], {"vendor/lib64/libw.so": data})
    rc, out = run_verifier(tree)
    # hash mismatch on the pre-fixup pin must NOT be reported when a fixup ran;
    # only the fixup hash is checkable. So this is a pass.
    ok = rc == 0
    return ok, "exit 0 when the post-fixup hash matches", rc, out


def case_nonelf_with_fix_soname(tmp, verbose):
    data = b"#!/bin/sh\necho not an elf\n"
    line = "vendor/bin/tool;FIX_SONAME"
    tree = make_tree(tmp, [line], {"vendor/bin/tool": data})
    rc, out = run_verifier(tree)
    ok = rc == 1
    return ok, "exit 1 when FIX_SONAME is declared on a non-ELF file", rc, out


def case_elf_without_dynamic(tmp, verbose):
    data = build_elf(soname="libv.so", with_dynamic=False)
    line = "vendor/lib64/libv.so;FIX_SONAME"
    tree = make_tree(tmp, [line], {"vendor/lib64/libv.so": data})
    rc, out = run_verifier(tree)
    ok = rc == 1
    return ok, "exit 1 when an ELF has no readable .dynamic (cannot verify)", rc, out


CASES = [
    ("missing file", case_missing),
    ("wrong SONAME", case_wrong_soname),
    ("wrong hash", case_wrong_hash),
    ("correct file", case_correct),
    ("fixup hash without fixup", case_fixuphash_without_fixup),
    ("pre-fixup hash only + fixup", case_preonly_hash_with_fixup),
    ("post-fixup hash matches", case_fixuphash_matches),
    ("non-ELF with FIX_SONAME", case_nonelf_with_fix_soname),
    ("ELF without .dynamic", case_elf_without_dynamic),
]


def main() -> int:
    verbose = "-v" in sys.argv
    if not os.path.isfile(VERIFIER):
        print(f"FATAL: verifier not found: {VERIFIER}", file=sys.stderr)
        return 2

    print("=" * 68)
    print("verify_blobs.py fault-injection tests (asserting EXIT CODES)")
    print("=" * 68)
    failures = []
    for name, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="blobtest-")
        try:
            ok, expect, rc, out = fn(tmp, verbose)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name:<32} rc={rc}   expected: {expect}")
        if not ok:
            failures.append((name, expect, rc, out))
        elif verbose:
            for line in out.splitlines():
                if line.strip():
                    print(f"        | {line}")

    print()
    if failures:
        print(f"{len(failures)} CASE(S) REGRESSED:")
        for name, expect, rc, out in failures:
            print(f"\n--- {name}: expected {expect}, got rc={rc}")
            for line in out.splitlines()[-12:]:
                print(f"    {line}")
        return 1
    print(f"all {len(CASES)} cases behaved as required")
    return 0


if __name__ == "__main__":
    sys.exit(main())
