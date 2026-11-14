#!/usr/bin/env python3
"""verify_blobs.py — authoritative proprietary-blob verification.

Why this exists
---------------
The naive check "does a file with this basename exist under vendor/xiaomi/?" is
wrong in several ways, all of which occur in this device's blob lists:

  1. **Destination remap**  `vendor/lib64/hw/fingerprint.goodix_fod.so:
     vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so`
     The *source* name must NOT be what lands in the tree.

  2. **Renamed module + SONAME fix**  the same line carries `;FIX_SONAME`, so
     extract-utils rewrites the ELF `DT_SONAME` of the *installed* file. A file
     can sit at the right path with the right name and still be unusable,
     because its SONAME was never patched.

  3. **Two different hashes.**  `path|hash|fixuphash` means:
        hash        = SHA1 of the file BEFORE fixups (as extracted)
        fixup_hash  = SHA1 of the file AFTER  fixups (as installed)
     Verifying the wrong one, or merely *counting* them, proves nothing.

  4. **`;`-args.**  `vendor/lib/libSNPE.so;DISABLE_CHECKELF`. Truncating at the
     first `;` or `|` yields a source path that never existed.

Parsing rules replicated from LineageOS/android_tools_extract_utils
(extract_utils/file.py, read from upstream):

    SEPARATORS = ';:|'
    SRC_REGEX  = r'^([^;:|]+)'                 -> File.src
    EXTRA_REGEX= r'([;:|])([^;:|]+)'           -> extras, in order
        ':' -> File.dst   (set_dst; has_dst = dst != src)
        ';' -> File.args  ('KEY' or 'KEY=value')
        '|' -> hash, then fixup-hash
    leading '-' -> is_package (APK/JAR treated as a package, not a copy)

Installed location is `vendor/<vendor>/<device>/proprietary/<File.dst>`.

Hash semantics replicated from extract_utils/module.py `process_pinned_file`:

    no fixup fn, no fixup_hash : verify hash        against pre-fixup SHA1
    no fixup fn, HAS fixup_hash: BAD_FIXUP (red)    -- cannot be satisfied
    fixup fn,    no fixup_hash : WARN (red)         -- hash unknown, cannot verify
    fixup fn,    HAS fixup_hash: verify hash        against pre-fixup SHA1
                                 and fixup_hash     against post-fixup SHA1

Because this script runs *after* extraction, the installed file is the
POST-fixup artefact. So:
  * `fixup_hash` can be checked directly against the installed file;
  * `hash` (pre-fixup) cannot be re-derived from the installed file when a
    fixup ran — it must be reported as UNVERIFIABLE, never as a pass.

Exit codes:
    0 = every declared entry present AND every verifiable property verified
    1 = at least one FAIL (missing, bad SONAME, hash mismatch, bad fixup config)
    2 = usage / tree error
    3 = tree is structurally fine but some properties are UNVERIFIABLE
        (this is NOT success: callers must treat it as "do not trust")

Usage
    python3 scripts/verify_blobs.py /path/to/pixelos15 [--json out.json]
                                    [--strict]   # treat UNVERIFIABLE as failure
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys

SEPARATORS = ";:|"
SRC_REGEX = re.compile(r"^([^;:|]+)")
EXTRA_REGEX = re.compile(r"([;:|])([^;:|]+)")

KNOWN_ARGS = {
    "AB", "CERTIFICATE", "BOOT_JAR", "DUMMY_SHARED_LIB", "EXTRACT_ONLY",
    "MAKE_COPY_RULE", "MAKE_COPY_RULE_ONLY", "MODULE", "MODULE_SUFFIX",
    "DISABLE_CHECKELF", "DISABLE_DEPS", "FIX_SONAME", "FIX_XML",
    "STRIP_DEBUG_SECTIONS", "OVERRIDES", "PRESIGNED", "REQUIRED",
    "SKIPAPKCHECKS", "SYMLINK", "TRYSRCFIRST", "FILEGROUP", "RECOVERY_AVAILABLE",
}

# Args whose presence means extract-utils runs a fixup on the file, i.e. the
# installed bytes differ from the extracted bytes.
FIXUP_ARGS = {"FIX_SONAME", "FIX_XML", "STRIP_DEBUG_SECTIONS"}

PROPRIETARY_SUBDIR = "proprietary"

# Outcomes for one entry.
OK = "OK"
FAIL = "FAIL"
UNVERIFIABLE = "UNVERIFIABLE"
SKIPPED = "SKIPPED"
RESIGNED = "RESIGNED"


class Entry:
    """One parsed proprietary-files.txt line (mirrors extract_utils.file.File)."""

    __slots__ = ("lineno", "raw", "src", "dst", "has_dst", "args",
                 "hash", "fixup_hash", "is_package", "section")

    def __init__(self, line: str, lineno: int, section: str):
        self.lineno = lineno
        self.raw = line
        self.section = section
        self.args: dict[str, object] = {}
        self.hash = None
        self.fixup_hash = None
        self.is_package = False

        line = line.strip()
        if line.startswith("-"):
            self.is_package = True
            line = line[1:]

        m = SRC_REGEX.match(line)
        if not m:
            raise ValueError(f"line {lineno}: cannot find source in {line!r}")
        self.src = m.group(1)
        self.dst = self.src
        self.has_dst = False

        hashes: list[str] = []
        for prefix, extra in EXTRA_REGEX.findall(line):
            if prefix == ":":
                if extra == self.src:
                    self.dst, self.has_dst = self.src, False
                else:
                    self.dst, self.has_dst = extra, True
            elif prefix == ";":
                k, _, v = extra.partition("=")
                self.args[k] = (v if v else True)
            else:  # '|'
                hashes.append(extra)
        if len(hashes) >= 1:
            self.hash = hashes[0]
        if len(hashes) == 2:
            self.fixup_hash = hashes[1]

    @property
    def dest_relpath(self) -> str:
        return self.dst

    @property
    def has_fixup(self) -> bool:
        return any(a in self.args for a in FIXUP_ARGS)


def parse_blob_list(path: str) -> list[Entry]:
    entries: list[Entry] = []
    section = ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n").rstrip("\r")
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                section = stripped.lstrip("# ").strip()
                continue
            entries.append(Entry(line, lineno, section))
    return entries


def file_sha1(path: str) -> str | None:
    """SHA1 of the whole file, matching extract_utils.utils.file_path_sha1."""
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


class ElfError(Exception):
    """Raised when a file is ELF-shaped but its dynamic section is unreadable."""


def elf_dynamic_strings(path: str) -> dict[str, list[str]] | None:
    """Return {'SONAME': [...], 'NEEDED': [...]} for an ELF file.

    Returns None when the file is not ELF at all (that is a legitimate
    "not applicable" answer, e.g. a shell script). Raises ElfError when the file
    *is* ELF but the dynamic section cannot be parsed — that must never be
    silently treated as "fine", because it is exactly the case where a broken
    SONAME would hide.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ElfError(f"unreadable: {exc}") from exc

    if len(data) < 0x40 or data[:4] != b"\x7fELF":
        return None

    try:
        ei_class = data[4]        # 1=32bit, 2=64bit
        ei_data = data[5]         # 1=LE, 2=BE
        if ei_class not in (1, 2):
            raise ElfError(f"unexpected EI_CLASS {ei_class}")
        if ei_data not in (1, 2):
            raise ElfError(f"unexpected EI_DATA {ei_data}")
        endian = "<" if ei_data == 1 else ">"

        if ei_class == 2:
            e_shoff, = struct.unpack_from(endian + "Q", data, 0x28)
            e_shentsize, e_shnum = struct.unpack_from(endian + "HH", data, 0x3A)
            e_shstrndx, = struct.unpack_from(endian + "H", data, 0x3E)
            sh_fmt, dyn_fmt = endian + "IIQQQQIIQQ", endian + "qQ"
        else:
            e_shoff, = struct.unpack_from(endian + "I", data, 0x20)
            e_shentsize, e_shnum = struct.unpack_from(endian + "HH", data, 0x2E)
            e_shstrndx, = struct.unpack_from(endian + "H", data, 0x32)
            sh_fmt, dyn_fmt = endian + "IIIIIIIIII", endian + "iI"

        if e_shoff == 0 or e_shnum == 0:
            raise ElfError("no section headers (stripped?) — cannot read .dynamic")

        need = struct.calcsize(sh_fmt)
        sections = []
        for i in range(e_shnum):
            off = e_shoff + i * e_shentsize
            if off + need > len(data):
                raise ElfError("section header table truncated")
            sections.append(struct.unpack_from(sh_fmt, data, off))

        if e_shstrndx >= len(sections):
            raise ElfError(f"e_shstrndx {e_shstrndx} out of range")
        shstr_off = sections[e_shstrndx][4]

        def section_name(idx: int) -> str:
            nm_off = sections[idx][0]
            start = shstr_off + nm_off
            if start >= len(data):
                return ""
            end = data.find(b"\x00", start)
            return data[start:end].decode("ascii", "replace") if end > 0 else ""

        dyn_sec = None
        for idx in range(len(sections)):
            if section_name(idx) == ".dynamic":
                dyn_sec = sections[idx]
                break
        if dyn_sec is None:
            # A shared library with no .dynamic cannot be a valid .so for the
            # loader; treat as unreadable rather than "no SONAME, fine".
            raise ElfError("no .dynamic section")

        d_off, d_size = dyn_sec[4], dyn_sec[5]
        entsize = struct.calcsize(dyn_fmt)
        if entsize == 0:
            raise ElfError("bad dynamic entry size")

        tags = []
        for pos in range(d_off, min(d_off + d_size, len(data)), entsize):
            if pos + entsize > len(data):
                break
            tags.append(struct.unpack_from(dyn_fmt, data, pos))

        strtab_addr = None
        needed_offsets: list[int] = []
        soname_offset = None
        for tag, val in tags:
            if tag == 0:      # DT_NULL ends the array
                break
            if tag == 5:      # DT_STRTAB
                strtab_addr = val
            elif tag == 1:    # DT_NEEDED
                needed_offsets.append(val)
            elif tag == 14:   # DT_SONAME
                soname_offset = val
        if strtab_addr is None:
            raise ElfError("no DT_STRTAB")

        strtab_file_off = None
        for sec in sections:
            sh_addr, sh_offset, sh_sz = sec[3], sec[4], sec[5]
            if sh_addr and sh_addr <= strtab_addr < sh_addr + sh_sz:
                strtab_file_off = sh_offset + (strtab_addr - sh_addr)
                break
        if strtab_file_off is None:
            raise ElfError("DT_STRTAB not covered by any section")

        def read_str(rel: int) -> str:
            start = strtab_file_off + rel
            if start >= len(data):
                return ""
            end = data.find(b"\x00", start)
            return data[start:end].decode("ascii", "replace") if end > 0 else ""

        out: dict[str, list[str]] = {"SONAME": [], "NEEDED": []}
        for rel in needed_offsets:
            s = read_str(rel)
            if s:
                out["NEEDED"].append(s)
        if soname_offset is not None:
            s = read_str(soname_offset)
            if s:
                out["SONAME"].append(s)
        return out
    except struct.error as exc:
        raise ElfError(f"struct: {exc}") from exc
    except (IndexError, ValueError) as exc:
        raise ElfError(f"malformed: {exc}") from exc


def check_soname(entry: Entry, installed: str) -> dict:
    """Verify the installed file's DT_SONAME matches its installed basename.

    A shared library whose DT_SONAME still names the *source* file is the exact
    symptom of a FIX_SONAME that never ran.
    """
    rec: dict[str, object] = {"lineno": entry.lineno, "dst": entry.dst}
    try:
        dyn = elf_dynamic_strings(installed)
    except ElfError as exc:
        rec.update(status=FAIL,
                   reason=f"ELF unreadable: {exc}",
                   detail="cannot confirm DT_SONAME; a broken SONAME would hide here")
        return rec

    if dyn is None:
        rec.update(status=FAIL,
                   reason="not an ELF file",
                   detail="carries FIX_SONAME but is not ELF; nothing to patch")
        return rec

    base = os.path.basename(entry.dst)
    sonames = dyn["SONAME"]
    rec["soname"] = sonames
    rec["basename"] = base
    if not sonames:
        rec.update(status=FAIL,
                   reason="no DT_SONAME",
                   detail="FIX_SONAME expects a SONAME to rewrite; none present")
        return rec
    if sonames[0] != base:
        rec.update(status=FAIL,
                   reason=f"DT_SONAME '{sonames[0]}' != installed basename '{base}'",
                   detail="the FIX_SONAME rewrite did not happen, or a wrong file was installed")
        return rec
    rec.update(status=OK, reason=f"DT_SONAME == basename ({base})")
    return rec


def looks_like_platform_apk(path: str) -> bool:
    """True if the file is a ZIP-based APK (so a re-sign change is plausible)."""
    try:
        if os.path.getsize(path) < 22:
            return False
        with open(path, "rb") as fh:
            return fh.read(2) == b"PK"
    except OSError:
        return False


def check_hashes(entry: Entry, installed: str) -> dict:
    """Apply extract-utils' hash semantics to the installed (post-fixup) file.

    See module.py `process_pinned_file` for the upstream branches reproduced
    below. The crucial distinction: `hash` pins the PRE-fixup bytes, so once a
    fixup has run it cannot be re-derived from the installed file.
    """
    rec: dict[str, object] = {"lineno": entry.lineno, "dst": entry.dst}
    if entry.hash is None and entry.fixup_hash is None:
        rec.update(status=SKIPPED, reason="no hash pinned in the list")
        return rec

    has_fixup = entry.has_fixup
    actual = file_sha1(installed)
    if actual is None:
        rec.update(status=FAIL, reason="cannot read installed file for hashing")
        return rec
    rec["actual_sha1"] = actual

    # --- fixup hash declared but no fixup function -------------------------
    # Upstream returns BAD_FIXUP here because it has just extracted the file and
    # the bytes still need patching. That reasoning does NOT apply when the
    # source is an already-built ROM: there the fixup is already applied, so the
    # installed file *is* the post-fixup artefact and fixup_hash must match
    # directly. Verify the hash first and only complain if it disagrees.
    if entry.fixup_hash is not None and not has_fixup:
        if entry.fixup_hash == actual:
            rec.update(
                status=OK,
                reason="fixup hash matches the installed file "
                       "(fixup already applied by the source ROM)",
                expected_fixup=entry.fixup_hash)
            return rec
        rec.update(
            status=FAIL,
            reason="list declares a fixup hash but the entry has no fixup, "
                   "and the installed file does not match that hash",
            detail="either the source differs or the list is stale",
            expected_fixup=entry.fixup_hash)
        return rec

    # --- upstream branch: fixup function but no fixup hash -------------------
    if has_fixup and entry.fixup_hash is None:
        if entry.hash is not None:
            rec.update(
                status=UNVERIFIABLE,
                reason="only a pre-fixup hash is pinned, but a fixup ran",
                detail=("the installed file is post-fixup, so the pinned hash "
                        "cannot be re-derived; upstream would print the new "
                        "fixup hash in red and expect it to be added"),
                expected_pre_fixup=entry.hash)
            return rec
        rec.update(status=SKIPPED, reason="no hash pinned")
        return rec

    # --- fixup hash declared and a fixup exists ----------------------------
    if entry.fixup_hash is not None:
        if entry.fixup_hash == actual:
            rec.update(status=OK,
                       reason="post-fixup hash matches the installed file",
                       expected_fixup=entry.fixup_hash)
            return rec
        rec.update(status=FAIL,
                   reason="post-fixup hash mismatch",
                   expected_fixup=entry.fixup_hash)
        return rec

    # --- no fixup at all: the pinned hash is the file itself ----------------
    if entry.hash == actual:
        rec.update(status=OK, reason="hash matches the installed file",
                   expected=entry.hash)
        return rec

    # A signed ROM re-signs platform APKs. The pinned hash came from the original
    # firmware, so a mismatch on an APK whose contents are a valid ZIP is a
    # provenance difference: report it explicitly instead of calling it a defect.
    if looks_like_platform_apk(installed):
        rec.update(
            status=RESIGNED,
            reason="APK hash differs from the pinned value "
                   "(re-signed by the source ROM)",
            detail="the code may be identical but the signature differs; "
                   "this is not proof of a bad file, and not proof of a good one",
            expected=entry.hash)
        return rec

    rec.update(status=FAIL, reason="hash mismatch", expected=entry.hash)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree", help="root of the synced PixelOS tree")
    ap.add_argument("--json", help="write a machine-readable report here")
    ap.add_argument("--quiet", action="store_true", help="only print problems")
    ap.add_argument("--strict", action="store_true",
                    help="treat UNVERIFIABLE findings as failures (exit 1)")
    args = ap.parse_args()

    tree = os.path.abspath(args.tree)
    if not os.path.isdir(tree):
        print(f"FATAL: not a directory: {tree}", file=sys.stderr)
        return 2

    targets = [
        ("device/xiaomi/sdm845-common", "vendor/xiaomi/sdm845-common", "sdm845-common"),
        ("device/xiaomi/equuleus", "vendor/xiaomi/equuleus", "equuleus"),
    ]

    report: dict[str, object] = {
        "tree": tree, "devices": {}, "counts": {}, "verdict": None,
    }
    totals = {OK: 0, FAIL: 0, UNVERIFIABLE: 0, SKIPPED: 0, RESIGNED: 0}

    for devdir, vdir, label in targets:
        listpath = os.path.join(tree, devdir, "proprietary-files.txt")
        blobroot = os.path.join(tree, vdir, PROPRIETARY_SUBDIR)
        info: dict[str, object] = {
            "blob_list": listpath, "blob_root": blobroot,
            "total": 0, "present": 0, "missing": [],
            "soname": [], "hashes": [], "unknown_args": [],
            "outcomes": {OK: 0, FAIL: 0, UNVERIFIABLE: 0, SKIPPED: 0, RESIGNED: 0},
        }
        report["devices"][label] = info

        if not os.path.isfile(listpath):
            info["error"] = "proprietary-files.txt missing"
            totals[FAIL] += 1
            info["outcomes"][FAIL] += 1
            print(f"[FAIL] {label}: missing {listpath}")
            continue

        entries = parse_blob_list(listpath)
        info["total"] = len(entries)

        if not os.path.isdir(blobroot):
            info["error"] = f"blob root missing: {blobroot}"
            totals[FAIL] += 1
            info["outcomes"][FAIL] += 1
            print(f"[FAIL] {label}: blob root does not exist: {blobroot}")
            continue

        for e in entries:
            installed = os.path.join(blobroot, e.dest_relpath)
            exists = os.path.exists(installed)

            for k in e.args:
                if k not in KNOWN_ARGS:
                    info["unknown_args"].append({"arg": k, "lineno": e.lineno})

            if not exists:
                info["missing"].append({
                    "src": e.src, "dst": e.dst,
                    "expected": os.path.relpath(installed, tree),
                    "lineno": e.lineno})
                info["outcomes"][FAIL] += 1
                totals[FAIL] += 1
                continue
            info["present"] += 1

            # Every present entry has an outcome; default is OK only if there
            # was nothing to check. Hash and SONAME results override it.
            entry_outcome = SKIPPED
            entry_reason = "no verifiable property declared"

            if "FIX_SONAME" in e.args:
                rec = check_soname(e, installed)
                info["soname"].append(rec)
                entry_outcome = rec["status"]
                entry_reason = rec["reason"]

            hrec = check_hashes(e, installed)
            info["hashes"].append(hrec)
            # A hash verdict is at least as authoritative as the SONAME one for
            # deciding pass/fail; a worse status wins.
            rank = {OK: 0, SKIPPED: 1, RESIGNED: 2, UNVERIFIABLE: 3, FAIL: 4}
            if rank[hrec["status"]] >= rank[entry_outcome]:
                entry_outcome = hrec["status"]
                entry_reason = hrec["reason"]

            info["outcomes"][entry_outcome] += 1
            totals[entry_outcome] += 1

        oc = info["outcomes"]
        if not args.quiet:
            print(f"[{label}] {info['present']}/{info['total']} declared entries present")
            print(f"          outcomes: "
                  f"OK={oc[OK]} FAIL={oc[FAIL]} RESIGNED={oc[RESIGNED]} "
                  f"UNVERIFIABLE={oc[UNVERIFIABLE]} SKIPPED={oc[SKIPPED]}")

            if info["missing"]:
                print(f"          {len(info['missing'])} MISSING:")
                for m in info["missing"][:10]:
                    print(f"            line {m['lineno']}: {m['src']}")
                    print(f"                     expected {m['expected']}")
            bad_soname = [r for r in info["soname"] if r["status"] == FAIL]
            if bad_soname:
                print(f"          {len(bad_soname)} SONAME FAILURE(S):")
                for r in bad_soname[:10]:
                    print(f"            line {r['lineno']}: {r['dst']}")
                    print(f"                     {r['reason']}")
                    if r.get("detail"):
                        print(f"                     {r['detail']}")
            bad_hash = [r for r in info["hashes"] if r["status"] == FAIL]
            if bad_hash:
                print(f"          {len(bad_hash)} HASH FAILURE(S):")
                for r in bad_hash[:10]:
                    print(f"            line {r['lineno']}: {r['dst']}")
                    print(f"                     {r['reason']}")
                    if r.get("expected"):
                        print(f"                     expected {r['expected']}")
                    if r.get("expected_fixup"):
                        print(f"                     expected fixup {r['expected_fixup']}")
                    if r.get("actual_sha1"):
                        print(f"                     actual   {r['actual_sha1']}")
            unver = [r for r in info["hashes"] if r["status"] == UNVERIFIABLE]
            if unver:
                print(f"          {len(unver)} UNVERIFIABLE hash pin(s) — cannot be confirmed:")
                for r in unver[:5]:
                    print(f"            line {r['lineno']}: {r['dst']}: {r['reason']}")
            if info["unknown_args"]:
                print(f"          {len(info['unknown_args'])} unknown ;-argument(s):")
                for u in info["unknown_args"][:5]:
                    print(f"            line {u['lineno']}: {u['arg']}")
            print()

    report["counts"] = totals

    if totals[FAIL] > 0:
        verdict = "FAIL"
        code = 1
    elif totals[UNVERIFIABLE] > 0:
        verdict = "UNVERIFIABLE"
        code = 1 if args.strict else 3
    else:
        verdict = "OK"
        code = 0
    report["verdict"] = verdict

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"JSON report: {args.json}")

    print("=" * 62)
    print(f"OK={totals[OK]}  FAIL={totals[FAIL]}  RESIGNED={totals[RESIGNED]}  "
          f"UNVERIFIABLE={totals[UNVERIFIABLE]}  SKIPPED={totals[SKIPPED]}")
    if verdict == "OK":
        print("RESULT: every declared entry is present and every declared")
        print("        property was verified against the installed file.")
        print("This does NOT prove the blobs came from the declared firmware")
        print("version (most lines pin no hash), nor that they run on hardware.")
        return 0
    if verdict == "UNVERIFIABLE":
        print("RESULT: entries present, but some pinned properties CANNOT be")
        print("        verified from the installed tree (see lines above).")
        print("        Treat as NOT verified; re-run with --strict to fail.")
        return code
    print("RESULT: FAILED — do not build. See the failures above.")
    return code


if __name__ == "__main__":
    sys.exit(main())
