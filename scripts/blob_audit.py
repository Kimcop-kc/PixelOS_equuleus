#!/usr/bin/env python3
"""blob_audit.py — resolve every blob-list entry against extracted partitions.

Purpose: before copying a single byte, know exactly which entries the OTA can
satisfy, which need a destination remap, and which are genuinely absent. This
turns guesswork into a list.

For each entry in `proprietary-files.txt`:

  * `src`  — where the file is expected inside the source partition
  * `dst`  — where extract-utils installs it (== src unless `:dst` is given)

Resolution states, in priority order:

  HIT_SRC     the source path exists in the source partition
  HIT_DST     the source path is absent, but the DESTINATION path already exists
              in some partition — typically because LineageOS ships it at the
              final location already (this is the "35 target-only" class)
  HIT_RENAME  found by basename elsewhere in the same partition tree
  MISSING     not found anywhere

`HIT_DST` and `HIT_RENAME` are NOT failures: the bytes are present, just at a
different path than the list assumed. They must be copied from the location
that actually exists, and the reason must be recorded.

Usage:
    python3 blob_audit.py <dump-root> <device-tree-root> [--json out.json]

<dump-root> holds `dump/<partition>/...` produced by img_extract.sh.
<device-tree-root> holds `device-xiaomi-equuleus/proprietary-files.txt` etc.

Exit codes: 0 = audit produced (regardless of missing count), 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SEPARATORS = ";:|"
SRC_REGEX = re.compile(r"^([^;:|]+)")
EXTRA_REGEX = re.compile(r"([;:|])([^;:|]+)")

# A blob's partition is implied by its path prefix inside /vendor-style trees,
# but the OTA keeps partitions separate, so we search the union of dumps and
# record which partition actually supplied each file.
PARTITIONS = ["vendor", "product", "system_ext", "system", "odm"]


def split_partition(path: str):
    """Split "vendor/lib/x.so" -> ("vendor", "lib/x.so").

    Blob lists address files from the root of the device filesystem, but each
    partition dump is rooted at that partition, so the leading partition
    component must be stripped before lookup.
    """
    for part in PARTITIONS:
        prefix = part + "/"
        if path.startswith(prefix):
            return part, path[len(prefix):]
    return None, path


class Entry:
    __slots__ = ("lineno", "src", "dst", "args", "section")

    def __init__(self, line: str, lineno: int, section: str):
        self.lineno = lineno
        self.section = section
        self.args: list[str] = []
        line = line.strip()
        if line.startswith("-"):
            line = line[1:]
        m = SRC_REGEX.match(line)
        if not m:
            raise ValueError(f"line {lineno}: no source in {line!r}")
        self.src = m.group(1)
        self.dst = self.src
        for prefix, extra in EXTRA_REGEX.findall(line):
            if prefix == ":":
                self.dst = extra
            elif prefix == ";":
                self.args.append(extra)


def parse_list(path: str) -> list[Entry]:
    out: list[Entry] = []
    section = ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n").rstrip("\r")
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                section = s.lstrip("# ").strip()
                continue
            try:
                out.append(Entry(line, lineno, section))
            except ValueError:
                continue
    return out


def index_dump(root: str) -> dict[str, dict[str, str]]:
    """Return {partition: {relative_path: absolute_path}} for the dumped trees."""
    idx: dict[str, dict[str, str]] = {}
    for part in PARTITIONS:
        base = os.path.join(root, "dump", part)
        table: dict[str, str] = {}
        if os.path.isdir(base):
            for dirpath, _dirnames, filenames in os.walk(base):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, base).replace(os.sep, "/")
                    table[rel] = full
        idx[part] = table
    return idx


def index_by_basename(idx: dict[str, dict[str, str]]) -> dict[str, list[tuple[str, str, str]]]:
    """{basename: [(partition, relpath, abspath), ...]} across all partitions."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for part, table in idx.items():
        for rel, full in table.items():
            base = rel.rsplit("/", 1)[-1]
            out.setdefault(base, []).append((part, rel, full))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump_root")
    ap.add_argument("tree_root")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    dump_root = os.path.abspath(args.dump_root)
    tree_root = os.path.abspath(args.tree_root)
    if not os.path.isdir(os.path.join(dump_root, "dump")):
        print(f"FATAL: {dump_root}/dump does not exist", file=sys.stderr)
        return 2

    idx = index_dump(dump_root)
    by_base = index_by_basename(idx)

    # Support both layouts, preferring whichever actually exists:
    #   real synced tree : <root>/equuleus/proprietary-files.txt
    #   review package   : <root>/device-xiaomi-equuleus/proprietary-files.txt
    # `<root>` is what the caller passes (…/device/xiaomi in a real tree).
    trees = []
    for label in ("equuleus", "sdm845-common"):
        for cand in (label, "device-xiaomi-" + label):
            if os.path.isfile(os.path.join(tree_root, cand,
                                           "proprietary-files.txt")):
                trees.append((label, cand))
                break
        else:
            # keep the plain name so the warning names something sensible
            trees.append((label, label))

    report: dict[str, object] = {"dump_root": dump_root, "trees": {}, "summary": {}}
    grand = {"HIT_SRC": 0, "HIT_DST": 0, "HIT_RENAME": 0, "MISSING": 0}

    for label, dirname in trees:
        listfile = os.path.join(tree_root, dirname, "proprietary-files.txt")
        if not os.path.isfile(listfile):
            print(f"  [warn] {listfile} missing; skipping {label}")
            continue
        entries = parse_list(listfile)
        results = []
        counts = {"HIT_SRC": 0, "HIT_DST": 0, "HIT_RENAME": 0, "MISSING": 0}

        for e in entries:
            state = None
            found = None          # (partition, relpath, abspath)
            note = ""

            src_part, src_rel = split_partition(e.src)
            dst_part, dst_rel = split_partition(e.dst)

            # 1. exact source path (search the named partition first)
            search = [src_part] if src_part else PARTITIONS
            for part in search:
                if src_rel in idx[part]:
                    state = "HIT_SRC"
                    found = (part, src_rel, idx[part][src_rel])
                    break

            # 2. destination path already present (the remap class)
            if state is None and e.dst != e.src:
                search2 = [dst_part] if dst_part else PARTITIONS
                for part in search2:
                    if dst_rel in idx[part]:
                        state = "HIT_DST"
                        found = (part, dst_rel, idx[part][dst_rel])
                        note = "source path absent; destination already exists"
                        break

            # 3. same basename somewhere (rename class)
            if state is None:
                base = e.src.rsplit("/", 1)[-1]
                cands = by_base.get(base, [])
                # prefer a candidate whose suffix matches more of src
                cands.sort(key=lambda c: -_suffix_score(e.src, c[1]))
                if cands:
                    part, rel, full = cands[0]
                    state = "HIT_RENAME"
                    found = (part, rel, full)
                    note = f"found as {rel}"

            if state is None:
                state = "MISSING"
                note = "not present in any extracted partition"

            counts[state] += 1
            grand[state] += 1
            results.append({
                "lineno": e.lineno,
                "src": e.src,
                "dst": e.dst,
                "state": state,
                "partition": found[0] if found else None,
                "found_at": found[1] if found else None,
                "note": note,
                "args": e.args,
            })

        report["trees"][label] = {"list": listfile, "counts": counts,
                                  "entries": results}
        print(f"\n{label}  ({len(entries)} entries)")
        for k in ("HIT_SRC", "HIT_DST", "HIT_RENAME", "MISSING"):
            print(f"    {k:12s} {counts[k]}")

    report["summary"] = grand
    total = sum(grand.values())
    print(f"\nTOTAL {total} entries")
    for k in ("HIT_SRC", "HIT_DST", "HIT_RENAME", "MISSING"):
        pct = (100.0 * grand[k] / total) if total else 0
        print(f"    {k:12s} {grand[k]:5d}  ({pct:5.1f}%)")

    js = args.json or os.path.join(dump_root, "blob_audit.json")
    with open(js, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nreport: {js}")
    return 0


def _suffix_score(src: str, candidate: str) -> int:
    """How many trailing path components src and candidate share."""
    a = src.split("/")
    b = candidate.split("/")
    n = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y:
            break
        n += 1
    return n


if __name__ == "__main__":
    sys.exit(main())
