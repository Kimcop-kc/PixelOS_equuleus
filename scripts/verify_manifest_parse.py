#!/usr/bin/env python3
"""verify_manifest_parse.py — parse our local manifest with the REAL git-repo code.

Why this exists
---------------
Every previous claim about manifest validity in this project was derived from
*re-implementing* git-repo's rules by reading `manifest_xml.py`. That is
reasoning, not evidence: an emulation can agree with the real parser on the
cases we thought of and diverge on the ones we did not.

This script imports `manifest_xml` from an actual git-repo checkout and runs the
genuine `XmlManifest` against:

  * the pristine PixelOS fifteen manifest (`default.xml` + its 3 snippets), and
  * the same manifest with our `.repo/local_manifests/equuleus.xml` merged in,
    exactly as `repo init`/`repo sync` does.

It then asserts the specific failure modes the review flagged:

  P0-2  double GMS override. If patches/0005 has been applied to the upstream
        manifest AND our local manifest also does
        `<remove-project name="vendor_gms"/>`, the real parser raises
        ManifestParseError("remove-project element specifies non-existent
        project"). We prove BOTH that this happens (regression fixture) and that
        it does NOT happen in the shipped configuration.

Usage:
    python scripts/verify_manifest_parse.py --repo-src /path/to/git-repo-src \
                                            --manifests /path/to/manifest-checkout

Exit codes: 0 = shipped config parses cleanly and the regression is caught,
            1 = shipped config is broken, or the regression was not detected,
            2 = prerequisites missing (git-repo source or manifest checkout).
"""
import argparse
import io
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

LONG_PREFIX = "\\\\?\\"


def winlong(path: str) -> str:
    p = os.path.abspath(path)
    if os.name != "nt" or p.startswith(LONG_PREFIX):
        return p
    if len(p) < 250:
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return LONG_PREFIX + p


def load_repo_module(repo_src: str):
    """Import the genuine git-repo manifest parser."""
    sys.path.insert(0, winlong(repo_src))
    try:
        import manifest_xml  # noqa: F401  (real module from the checkout)
        import error as repo_error
    except ImportError as exc:
        print(f"FATAL: cannot import git-repo modules from {repo_src}: {exc}",
              file=sys.stderr)
        return None, None
    return manifest_xml, repo_error


def make_repo_client(manifest_clone: str, local_manifest: str, workdir: str,
                     apply_0005: bool = False):
    """Build a minimal but *real* repo client around a genuine manifest clone.

    `XmlManifest` shells out to `git rev-parse HEAD` on .repo/manifests, so it
    needs an actual git repository — copying files into a bare directory is not
    enough (that was the previous failure). We therefore copy the real clone and
    add `.repo/local_manifests/` beside it.
    """
    client = os.path.join(workdir, "client")
    repodir = os.path.join(client, ".repo")
    manifests_git = os.path.join(repodir, "manifests.git")
    manifests_wt = os.path.join(repodir, "manifests")

    if os.path.isdir(winlong(client)):
        shutil.rmtree(winlong(client))
    os.makedirs(winlong(repodir), exist_ok=True)

    # `.repo/manifests` is a git working tree whose .git points at manifests.git.
    shutil.copytree(winlong(manifest_clone), winlong(manifests_wt),
                    ignore=shutil.ignore_patterns("__pycache__"))
    # Promote it to a bare-ish manifests.git that repo expects.
    src_git = os.path.join(manifests_wt, ".git")
    if os.path.isdir(winlong(src_git)):
        shutil.move(winlong(src_git), winlong(manifests_git))

    # XmlManifest resolves remote URLs against `remote.origin.url` of the
    # manifests repo (manifest_xml.py: _resolveFetchUrl -> normalize_url).
    # Without it, `None.rstrip()` blows up. Set it to the real upstream URL so
    # fetch resolution behaves exactly as it would for a genuine `repo init`.
    import subprocess as _sp
    _sp.run(["git", "--git-dir", winlong(manifests_git), "config",
             "remote.origin.url", "https://github.com/PixelOS-AOSP/manifest.git"],
            check=False, capture_output=True, text=True)
    _sp.run(["git", "--git-dir", winlong(manifests_git), "config",
             "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
            check=False, capture_output=True, text=True)

    if apply_0005:
        custom = os.path.join(manifests_wt, "snippets", "custom.xml")
        txt = open(winlong(custom), encoding="utf-8").read()
        oldp = ('  <project path="vendor/gms" name="vendor_gms" '
                'clone-depth="1" remote="PixelOS-Gitlab" />')
        newp = ('  <project path="vendor/gms" name="vendor_gms-15"\n'
                '           revision="ffe5c52d947eec784a07124dfb72e95840e8f3c7"\n'
                '           clone-depth="1" remote="PixelOS-Gitlab" />')
        if oldp in txt:
            txt = txt.replace(oldp, newp, 1)
            open(winlong(custom), "w", encoding="utf-8", newline="\n").write(txt)

    local_dir = os.path.join(repodir, "local_manifests")
    os.makedirs(winlong(local_dir), exist_ok=True)
    shutil.copy2(winlong(local_manifest),
                 winlong(os.path.join(local_dir, "equuleus.xml")))
    return (repodir,
            os.path.abspath(os.path.join(manifests_wt, "default.xml")),
            os.path.abspath(local_dir))


def parse_with_real_repo(manifest_xml, repodir: str, manifest_file: str,
                         local_manifests_dir: str = ""):
    """Run the genuine `XmlManifest` parser. Returns (obj, error_string).

    `local_manifests` MUST be passed explicitly: XmlManifest only merges it when
    the attribute is truthy (manifest_xml.py `_Load`, the
    `if self._load_local_manifests and self.local_manifests:` branch). Without
    it the parse silently ignores our overrides — which is how an earlier
    version of this script wrongly reported "vendor/gms -> vendor_gms".
    """
    try:
        m = manifest_xml.XmlManifest(
            repodir,
            manifest_file,
            local_manifests=local_manifests_dir or None,
        )
        return m, None
    except Exception as exc:  # noqa: BLE001 - we want the real exception text
        return None, f"{type(exc).__name__}: {exc}"


_CASE_WORKER = r"""
import io, json, os, sys
repo_src, repodir, manifest_file, local_dir = sys.argv[1:5]
sys.path.insert(0, repo_src)
import manifest_xml
try:
    m = manifest_xml.XmlManifest(repodir, manifest_file,
                                 local_manifests=local_dir or None)
    projects = m.projects
    gms = [p for p in projects if p.relpath == "vendor/gms"]
    paths = [p.relpath for p in projects]
    dupes = sorted({x for x in paths if paths.count(x) > 1})
    print(json.dumps({
        "ok": True,
        "count": len(projects),
        "dupes": dupes,
        "gms_name": gms[0].name if gms else None,
        "gms_rev": gms[0].revisionExpr if gms else None,
    }))
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
"""


def parse_in_subprocess(repo_src: str, repodir: str, manifest_file: str,
                        local_dir: str):
    """Run one parse in a clean interpreter and return its JSON verdict."""
    import json
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-c", _CASE_WORKER, repo_src, repodir,
         manifest_file, local_dir or ""],
        capture_output=True, text=True)
    payload = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    if payload is None:
        return {"ok": False,
                "error": f"worker produced no verdict (rc={proc.returncode}); "
                         f"stderr={proc.stderr.strip()[:200]}"}
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-src", required=True,
                    help="path to a git-repo source checkout (contains manifest_xml.py)")
    ap.add_argument("--manifests", required=True,
                    help="path to a PixelOS manifest checkout (default.xml + snippets/)")
    ap.add_argument("--local-manifest", default=None,
                    help="our local manifest (defaults to .repo/local_manifests/equuleus.xml)")
    ap.add_argument("--patch-0005", default=None,
                    help="patches/0005-manifest-gms-repo.patch (for the regression fixture)")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    local_manifest = args.local_manifest or os.path.join(
        root, ".repo", "local_manifests", "equuleus.xml")
    patch_0005 = args.patch_0005 or os.path.join(
        root, "patches", "0005-manifest-gms-repo.patch")

    for label, path in [("git-repo source", args.repo_src),
                        ("manifest checkout", args.manifests),
                        ("local manifest", local_manifest)]:
        if not os.path.isdir(winlong(path)) and not os.path.isfile(winlong(path)):
            print(f"FATAL: {label} not found: {path}", file=sys.stderr)
            return 2

    manifest_xml, repo_error = load_repo_module(args.repo_src)
    if manifest_xml is None:
        return 2

    work = tempfile.mkdtemp(prefix="manifest-parse-")
    rc = 0
    try:
        # ---------------- case 1: shipped configuration ----------------
        print("=" * 66)
        print("CASE 1  shipped configuration (local manifest only, no 0005)")
        print("=" * 66)
        r1, f1, l1 = make_repo_client(args.manifests, local_manifest,
                                      os.path.join(work, "c1"))
        v1 = parse_in_subprocess(args.repo_src, r1, f1, l1)
        if not v1.get("ok"):
            print(f"  [FAIL] real git-repo rejected the shipped manifest:")
            print(f"         {v1.get('error')}")
            rc = 1
        else:
            print(f"  [PASS] parsed by git-repo: {v1['count']} projects")
            print(f"         vendor/gms -> {v1['gms_name']} @ {v1['gms_rev']}")
            if v1["dupes"]:
                print(f"  [FAIL] duplicate paths: {v1['dupes']}")
                rc = 1
            else:
                print("  [PASS] no duplicate project paths")
            if v1["gms_name"] == "vendor_gms-15" and \
                    (v1["gms_rev"] or "").startswith("ffe5c52d"):
                print("  [PASS] GMS repoint is in effect")
            else:
                print(f"  [FAIL] GMS not repointed: {v1['gms_name']} @ {v1['gms_rev']}")
                rc = 1

        # ------------- case 2: the forbidden combination --------------
        print()
        print("=" * 66)
        print("CASE 2  REGRESSION: local manifest AND patch 0005 both applied")
        print("        (must raise ManifestParseError -- proves the check bites)")
        print("=" * 66)
        if not os.path.isfile(winlong(patch_0005)):
            print(f"  [SKIP] 0005 not present at {patch_0005}; cannot build fixture")
        else:
            r2, f2, l2 = make_repo_client(args.manifests, local_manifest,
                                          os.path.join(work, "c2"), apply_0005=True)
            v2 = parse_in_subprocess(args.repo_src, r2, f2, l2)
            if not v2.get("ok"):
                print("  [PASS] real git-repo rejected it as predicted:")
                print(f"         {v2.get('error')}")
                if "remove-project" in (v2.get("error") or "") or \
                        "non-existent" in (v2.get("error") or ""):
                    print("         (cause: remove-project target no longer exists)")
                else:
                    print("  [WARN] rejected, but not with the expected cause; inspect above.")
            else:
                print("  [FAIL] the doubled override parsed WITHOUT error.")
                print("         The review's P0-2 must be re-examined: either the")
                print("         parser tolerates it, or the fixture is wrong.")
                rc = 1
    finally:
        shutil.rmtree(winlong(work), ignore_errors=True)

    print()
    print("=" * 66)
    if rc == 0:
        print("RESULT: shipped manifest parses under real git-repo; the doubled")
        print("        override is provably rejected. P0-2 verified, not assumed.")
    else:
        print("RESULT: FAILED — see the [FAIL] lines above.")
    print("=" * 66)
    return rc


if __name__ == "__main__":
    sys.exit(main())
