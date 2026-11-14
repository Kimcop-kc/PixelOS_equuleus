#!/usr/bin/env python3
"""Split each staged commit into a reviewable, apply-checkable patch file.

The upstream device trees are the *base*; every patch here applies on top of
the exact LineageOS lineage-22.2 commits recorded in UPSTREAM_LOCK.md.
"""

import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHES = os.path.join(ROOT, "patches")

# (work repository, base-commit range start, output file name, subject)
GROUPS = [
    (
        "equuleus",
        ["fedf163", "HEAD~1"],
        "eq_product",
    ),
]

AUTHOR_EQUULEUS = 'From: equuleus port <port@example.invalid>\n'
AUTHOR_COMMON = 'From: sdm845 port <port@example.invalid>\n'


def run(cwd, *args, **kwargs):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, **kwargs)


def main():
    os.makedirs(PATCHES, exist_ok=True)

    definitions = [
        # (repo, commit hash, filename, From line, description)
        (
            "equuleus",
            "fedf163",
            "0001-equuleus-product-setup.patch",
            AUTHOR_EQUULEUS,
            "equuleus: add PixelOS product definition\n"
            "\n"
            "Rename lineage_equuleus.mk to aosp_equuleus.mk, switch the common\n"
            "product inheritance from vendor/lineage to vendor/aosp, and declare\n"
            "the real PixelOS lunch target (aosp_equuleus-bp1a-<variant>).\n"
            "\n"
            "vendor/aosp/config/common_full_phone.mk exists at\n"
            "PixelOS-AOSP/vendor_aosp@fifteen and aosp_target_release is bp1a\n"
            "(vendor/aosp/vars/aosp_target_release).\n",
        ),
        (
            "equuleus",
            "8261263",
            "0002-equuleus-drop-lineage-sdk-overlay.patch",
            AUTHOR_EQUULEUS,
            "equuleus: drop overlay subtree without a PixelOS target\n"
            "\n"
            "equuleus/overlay-lineage/lineage-sdk/ overrides resources of\n"
            "lineage-sdk, which PixelOS fifteen does not check out at all.\n"
            "Keeping the directory only produces an unresolved overlay target\n"
            "during resource merging, so remove it and document in device.mk\n"
            "why the two surviving subtrees are kept.\n",
        ),
        (
            "sdm845-common",
            "06d4447",
            "0003-sdm845-common-use-vendor-aosp.patch",
            AUTHOR_COMMON,
            "sdm845-common: switch build policy to vendor/aosp\n"
            "\n"
            "Replace the two LineageOS-only build inputs with the PixelOS\n"
            "equivalents that exist in PixelOS fifteen:\n"
            "  vendor/lineage/config/device_framework_matrix.xml\n"
            "    -> vendor/aosp/config/device_framework_matrix.xml\n"
            "  vendor/lineage/config/BoardConfigReservedSize.mk\n"
            "    -> vendor/aosp/config/BoardConfigReservedSize.mk\n"
            "\n"
            "The replaced framework matrix is NOT identical: PixelOS' copy is\n"
            "older and lacks the AIDL vendor.lineage.livedisplay and\n"
            "vendor.lineage.touch HAL declarations. That is recorded as a\n"
            "blocker (KNOWN_BLOCKERS.md B-07) because it governs VINTF\n"
            "compatibility checking, not the build itself.\n"
            "\n"
            "The replaced reserved-size file is also weaker: it reserves no\n"
            "space for system/system_ext/product. Recorded as B-06.\n",
        ),
        (
            "sdm845-common",
            "4334eeb",
            "0004-sdm845-common-drop-lineage-overlays.patch",
            AUTHOR_COMMON,
            "sdm845-common: drop overlays without a PixelOS target\n"
            "\n"
            "overlay-lineage/lineage-sdk/ targets lineage-sdk (absent from the\n"
            "PixelOS manifest) and overlay-lineage/packages/apps/Dialer/\n"
            "targets the LineageOS Dialer fork, whereas PixelOS uses\n"
            "platform/packages/apps/Dialer, whose callrecord resources do not\n"
            "exist. Both would abort resource merging, so remove them and stop\n"
            "adding the directory to DEVICE_PACKAGE_OVERLAYS.\n",
        ),
    ]

    written = []
    for repo, commit, filename, author, subject in definitions:
        work = os.path.join(ROOT, "work", repo)
        r = run(work, "git", "show", "--binary", "--format=", commit)
        if r.returncode != 0:
            print(f"failed to read {repo}@{commit}: {r.stderr}", file=sys.stderr)
            return 1
        body = r.stdout
        # The leading hash in a mail-style patch is the object name of the
        # commit the patch would create. These patches are exported from local
        # review commits, so we stamp a deterministic hash of the patch body
        # rather than inventing a commit id. `git am` only needs 40 hex chars.
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
        header = (
            f"From {digest} Mon Sep 17 00:00:00 2001\n"
            f"{author}"
            "Date: Wed, 12 Nov 2026 00:00:00 +0800\n"
            f"Subject: [PATCH] {subject.splitlines()[0]}\n"
            "\n" + "\n".join(subject.splitlines()[1:]).lstrip("\n") + "\n"
            "---\n"
        )
        path = os.path.join(PATCHES, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(header)
            fh.write(body)
        written.append(filename)
        print(f"wrote {filename} ({len(body.splitlines())} body lines)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
