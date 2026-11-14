#!/usr/bin/env python3
"""extract_package.py — unpack the deliverable ZIP correctly on Windows.

`zipfile.extractall()` fails on this package because several AIDL snapshots
nest deeper than Windows' 260-character MAX_PATH. That is a property of the
*source trees* (real AOSP AIDL layouts), not of the archive, so the fix belongs
in the extractor: every path is opened through the ``\\\\?\\`` long-path prefix.

Usage:
    python scripts/extract_package.py equuleus-pixelos15-port-20261111.zip [dest]
"""
import os
import sys
import zipfile

LONG_PREFIX = "\\\\?\\"


def winlong(path: str) -> str:
    p = os.path.abspath(path)
    if os.name != "nt" or p.startswith(LONG_PREFIX):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return LONG_PREFIX + p


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("usage: extract_package.py <archive.zip> [dest]", file=sys.stderr)
        return 2
    archive = args[0]
    dest = args[1] if len(args) > 1 else "."

    if not os.path.isfile(winlong(archive)):
        print(f"FATAL: no such archive: {archive}", file=sys.stderr)
        return 2

    os.makedirs(winlong(dest), exist_ok=True)
    failures = []
    count = 0
    with zipfile.ZipFile(winlong(archive)) as zf:
        bad = zf.testzip()
        if bad:
            print(f"FATAL: archive is corrupt at member: {bad}", file=sys.stderr)
            return 2
        for info in zf.infolist():
            target = os.path.join(dest, info.filename.replace("/", os.sep))
            if info.is_dir():
                os.makedirs(winlong(target), exist_ok=True)
                continue
            try:
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(winlong(parent), exist_ok=True)
                with zf.open(info) as src, open(winlong(target), "wb") as out:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                count += 1
            except OSError as exc:
                failures.append(f"{info.filename}: {exc}")

    print(f"extracted {count} files to {os.path.abspath(dest)}")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):", file=sys.stderr)
        for f in failures[:10]:
            print("  " + f, file=sys.stderr)
        return 1
    print("no extraction failures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
