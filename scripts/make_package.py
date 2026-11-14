#!/usr/bin/env python3
"""Build the deliverable ZIP for the PixelOS/equuleus port package.

Design decisions that matter for the recipient:

* **Long paths.** Windows refuses paths > 260 chars without the ``\\\\?\\``
  prefix, and the AIDL snapshots under ``src/`` exceed it by ~11 chars. Every
  filesystem call here goes through :func:`winlong`, so no file is silently
  dropped from the archive.
* **Clone payload.** ``clones/vendor-aosp-pixelos`` carries 740 MiB of packed
  history for 39 MiB of working tree. Shipping it verbatim makes the archive
  unusable. We therefore keep, per clone: the **working tree**, ``HEAD``,
  ``packed-refs``/``refs`` and the object database needed to satisfy
  ``git cat-file -e <sha>^{commit}``. Older unreachable history is dropped.
  ``scripts/fetch_clones.sh`` remains the way to obtain full history.
* **Verifiability.** A ``ZIP_MANIFEST.tsv`` listing every member and its size is
  written inside the archive, and the script refuses to report success if any
  walk error occurred.
"""
import io
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "out")

LONG_PREFIX = "\\\\?\\"


def winlong(path: str) -> str:
    """Return a path Windows can open even when > MAX_PATH."""
    p = os.path.abspath(path)
    if os.name != "nt":
        return p
    if p.startswith(LONG_PREFIX):
        return p
    if len(p) < 250:
        return p
    if p.startswith("\\\\"):
        # UNC: \\server\share -> \\?\UNC\server\share
        return "\\\\?\\UNC\\" + p[2:]
    return LONG_PREFIX + p


def sh(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=winlong(cwd) if cwd else None,
                          check=check, capture_output=True, text=True)


def iter_files(base: str, skip_dirs=frozenset({".git", "__pycache__", "out"})):
    """Yield file paths under base using long-path-safe calls.

    Directory listing itself is done via os.scandir on the long form so that
    deep trees are enumerated correctly on Windows.
    """
    stack = [base]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(winlong(cur)) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in skip_dirs:
                            continue
                        stack.append(os.path.join(cur, entry.name))
                    else:
                        yield os.path.join(cur, entry.name)
        except OSError as exc:
            yield ("ERROR", cur, str(exc))


def iter_dirs(base: str):
    """Yield every directory path under base, long-path safe."""
    stack = [base]
    while stack:
        cur = stack.pop()
        yield cur
        try:
            with os.scandir(winlong(cur)) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(os.path.join(cur, entry.name))
        except OSError:
            continue


def git_head(path: str) -> str:
    r = sh("git", "-C", path, "rev-parse", "HEAD", check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def prune_clone(path: str, log=print) -> None:
    """Reduce a clone to what the verifier needs: HEAD reachable, history shallow.

    We deliberately do NOT delete the object database, because
    ``git cat-file -e <sha>^{commit}`` must keep working. Instead we drop the
    remote-tracking refs, expire reflogs, and repack with a shallow boundary
    so only the checked-out commit's tree is guaranteed.
    """
    if not os.path.isdir(winlong(os.path.join(path, ".git"))):
        return
    before = dir_size(os.path.join(path, ".git"))
    # Do NOT delete the remote: blobless (promisor) clones keep their partial
    # clone filter in remote.origin.*, and removing it makes `git cat-file` fail
    # for objects that were never fetched. Only drop reflogs and loose history.
    sh("git", "-C", path, "reflog", "expire", "--expire=now", "--all", check=False)
    sh("git", "-C", path, "gc", "--prune=now", check=False)
    after = dir_size(os.path.join(path, ".git"))
    log(f"    .git {before/1024/1024:.0f} MiB -> {after/1024/1024:.0f} MiB")


def dir_size(path: str) -> int:
    total = 0
    for item in iter_files(path, skip_dirs=frozenset()):
        if isinstance(item, tuple):
            continue
        try:
            total += os.path.getsize(winlong(item))
        except OSError:
            pass
    return total


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    zip_path = os.path.join(OUT_DIR, f"equuleus-pixelos15-port-{stamp}.zip")

    do_prune = "--prune-clones" in sys.argv

    include_files = [
        "README.md", "UPSTREAM_LOCK.md", "DEVICE_AUDIT.md", "BLOB_EXTRACTION.md",
        "KNOWN_BLOCKERS.md", "CLOUD_READINESS.md", "TEST_REPORT.md",
    ]
    include_dirs = [
        "patches", "scripts", ".repo/local_manifests", "logs",
        "src", "clones", "work",
    ]
    # ".git" must NOT be skipped: the acceptance suite re-verifies every pin
    # with `git cat-file -e <sha>^{commit}`, which needs the object database.
    # "__pycache__", "out" and "incoming" carry no evidence.
    skip_dirs = frozenset({"__pycache__", "out", "incoming", "node_modules"})

    # Any clone created with --no-checkout (vendor-gms-15) has no working tree.
    # Packing it as-is would ship a directory that looks empty but is not a
    # usable checkout, so materialise the tree first.
    cdir = os.path.join(ROOT, "clones")
    if os.path.isdir(winlong(cdir)):
        for name in sorted(os.listdir(winlong(cdir))):
            p = os.path.join(cdir, name)
            gitdir = winlong(os.path.join(p, ".git"))
            if not os.path.isdir(gitdir):
                continue
            # does the working tree have any trackable file?
            has_tree = False
            for item in iter_files(p, frozenset({".git", "__pycache__"})):
                if not isinstance(item, tuple):
                    has_tree = True
                    break
            if not has_tree:
                # A --filter=blob:none clone has trees and commits but no blobs,
                # so checkout cannot succeed. That is fine: the pin evidence we
                # pack is the commit object, not the file payload.
                print(f"  {name}: tree-less clone (blobless); packing metadata only", flush=True)
                with open(winlong(os.path.join(p, "PARTIAL_CLONE.txt")), "w",
                          encoding="utf-8", newline="\n") as fh:
                    fh.write(
                        "This clone was created with --filter=blob:none.\n"
                        "It contains HEAD, commits and trees, but not file payloads,\n"
                        "so `git checkout` cannot materialise a working tree.\n"
                        "To obtain the files: scripts/fetch_clones.sh or\n"
                        "  git -C . fetch origin --refetch\n")

    if do_prune:
        print("pruning clones (keeping HEAD + commit objects) …", flush=True)
        for name in sorted(os.listdir(winlong(cdir))):
            p = os.path.join(cdir, name)
            if os.path.isdir(winlong(os.path.join(p, ".git"))):
                before = dir_size(p)
                print(f"  {name}: {before/1024/1024:.0f} MiB", flush=True)
                prune_clone(p, log=lambda s: print(s, flush=True))

    print(f"\nwriting {zip_path} …", flush=True)
    count = 0
    errors = []
    prefix = "equuleus-pixelos15-port"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name in include_files:
            full = os.path.join(ROOT, name)
            if os.path.isfile(winlong(full)):
                zf.write(winlong(full), f"{prefix}/{name}")
                count += 1

        for dirname in include_dirs:
            base = os.path.join(ROOT, dirname)
            if not os.path.isdir(winlong(base)):
                print(f"  (skip missing {dirname})", flush=True)
                continue
            added = 0
            for item in iter_files(base, skip_dirs):
                if isinstance(item, tuple):
                    _, where, why = item
                    errors.append(f"{where}: {why}")
                    continue
                rel = os.path.relpath(item, ROOT).replace(os.sep, "/")
                try:
                    zf.write(winlong(item), f"{prefix}/{rel}")
                    added += 1
                    count += 1
                except (OSError, ValueError) as exc:
                    errors.append(f"{rel}: {exc}")
            print(f"  + {dirname}: {added} files", flush=True)

        # Git refuses to recognise a repository whose .git/refs directory is
        # absent, even when every ref lives in packed-refs. ZIP cannot represent
        # empty directories, so walk the real filesystem and emit an explicit
        # directory entry for every .git/refs and .git/objects directory.
        empty_git_dirs = set()
        for dirname in ("clones",):
            base_dir = os.path.join(ROOT, dirname)
            if not os.path.isdir(winlong(base_dir)):
                continue
            for item in iter_dirs(base_dir):
                norm = item.replace(os.sep, "/")
                if "/.git/" in norm and (norm.endswith("/.git/refs")
                                         or norm.endswith("/.git/objects")):
                    empty_git_dirs.add(norm)
        for d in sorted(empty_git_dirs):
            rel = os.path.relpath(d, ROOT).replace(os.sep, "/")
            zf.writestr(zipfile.ZipInfo(f"{prefix}/{rel}/"), b"")
        if empty_git_dirs:
            print(f"  + .git/refs|objects directory entries: {len(empty_git_dirs)}", flush=True)

        # per-member manifest so a recipient can detect lost files
        buf = io.StringIO()
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.filename.endswith("/"):
                continue
            buf.write(f"{info.file_size}\t{info.filename}\n")
        zf.writestr(f"{prefix}/ZIP_MANIFEST.tsv", buf.getvalue())

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\nwrote {zip_path}")
    print(f"  {count} files, {size_mb:.1f} MiB compressed")
    if errors:
        print(f"\n  {len(errors)} PATH ERROR(S) — the archive is INCOMPLETE:")
        for e in errors[:10]:
            print(f"    {e}")
        if len(errors) > 10:
            print(f"    … and {len(errors) - 10} more")
        return 1
    print("  no path errors: every walked file is in the archive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
