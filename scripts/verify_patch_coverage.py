#!/usr/bin/env python3
"""Verify every authored commit in work/ is fully represented by a patch."""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ROOT)  # project root

PAIRS = [
    ("equuleus", "fedf163", "0001-equuleus-product-setup.patch"),
    ("equuleus", "8261263", "0002-equuleus-drop-lineage-sdk-overlay.patch"),
    ("sdm845-common", "06d4447", "0003-sdm845-common-use-vendor-aosp.patch"),
    ("sdm845-common", "4334eeb", "0004-sdm845-common-drop-lineage-overlays.patch"),
]


def norm(text):
    return [l.rstrip() for l in text.splitlines() if l.strip()]


def main():
    # The review-sized archive ships patches/ but not work/. In that case there
    # is nothing to compare against; report that plainly instead of crashing.
    present = [r for r in {p[0] for p in PAIRS}
               if os.path.isdir(os.path.join(ROOT, "work", r, ".git"))]
    if not present:
        print("work/ not present in this tree (expected in the review-sized archive).")
        print("Skipping commit-vs-patch comparison: there are no local commits to check.")
        print()
        print("The patches themselves are still validated by verify_deliverables.py")
        print("(check: 'patches apply cleanly' / 'patches carry mail headers'), and by")
        print("applying them to real upstream clones per REPRODUCE.md section B.")
        return 0

    bad = 0
    for repo, sha, patch in PAIRS:
        work = os.path.join(ROOT, "work", repo)
        if not os.path.isdir(os.path.join(work, ".git")):
            print(f"SKIP    {patch}: work/{repo} is not a git checkout here")
            continue
        r = subprocess.run(["git", "show", "--format=", "--binary", sha],
                           cwd=work, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{patch}: cannot read {repo}@{sha}: {r.stderr.strip()}")
            bad += 1
            continue
        git_diff = r.stdout

        p = os.path.join(ROOT, "patches", patch)
        txt = io.open(p, encoding="utf-8").read()
        i = txt.find("diff --git")
        patched = txt[i:] if i >= 0 else txt

        a, b = norm(patched), norm(git_diff)
        if a == b:
            print(f"MATCH   {patch}  ==  {repo}@{sha}")
        else:
            bad += 1
            print(f"DIFFERS {patch}  vs  {repo}@{sha}  ({len(a)} vs {len(b)} non-blank lines)")
            for x in a:
                if x not in b:
                    print("   only in patch:", x[:100])
                    break
            for x in b:
                if x not in a:
                    print("   only in git  :", x[:100])
                    break
    print()
    print("all authored work/ commits are exported" if bad == 0
          else f"{bad} commit(s) NOT fully exported")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
