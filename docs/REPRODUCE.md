# REPRODUCE

How to go from a clean machine to a verified verdict, for both this audit
archive and the full upstream-backed tree.

**This package contains no ROM. Nothing here was compiled, flashed or booted.**
`repo sync`, Soong/Make, the kernel build and all hardware testing remain
unexecuted — see `TEST_REPORT.md` §3.

---

## 0. What you need for each level

| Level | Needs | Time | What it proves |
| --- | --- | --- | --- |
| A. Audit this archive | Python 3, git, bash | < 1 min | our patches/manifest/scripts are self-consistent |
| B. Apply patches to real upstream | + network | ~5 min | the patches apply to the exact pinned commits |
| C. Full static evidence | + 9 git clones (~800 MB) | ~15 min | pins are real commit objects |
| D. Build attempt | + Ubuntu host, 16 vCPU/64 GiB/600 GiB | hours | **still not** that the ROM works |

---

## A. Verify this archive in place

```bash
# Run from the directory that CONTAINS the zip:
python3 -m zipfile -e PixelOS_equuleus_AUDIT_PACKAGE.zip /tmp/audit
cd /tmp/audit/PixelOS_equuleus_AUDIT_PACKAGE
chmod +x scripts/*.sh     # a ZIP built on Windows does not carry the +x bit

# 1. every authored change is represented by a patch
python3 scripts/verify_patch_coverage.py
#    -> expects "all authored work/ commits are exported" when work/ is present;
#       in this archive work/ is intentionally absent, so it reports that instead.

# 2. the acceptance suite
python3 scripts/verify_deliverables.py
#    -> the checks that need upstream source / clones FAIL here by design.
#       Checks that pass standalone include: docs present, scripts executable,
#       bash -n, fail-fast, no forbidden commands, no credentials,
#       manifest well-formed/SHA-pinned/remotes/remove-project, patch headers,
#       P0-1..P0-4 logic checks.

# 3. prove the suite can actually fail
python3 scripts/verify_mutations.py
#    -> seeds 28 defects; several need clones and will be reported as such.
```

Expected: no failures caused by a *missing file we authored*. Failures are
confined to evidence that requires the upstream tree.

---

## B. Apply the patches to real upstream commits

**Which patches are part of a normal build, and which is archived.**

正式构建只用局部 Manifest 做 GMS 替换：
the authoritative mechanism is `.repo/local_manifests/equuleus.xml`
(`<remove-project name="vendor_gms"/>` + re-add `vendor_gms-15`), installed
**before** `repo sync`. `patches/0005-manifest-gms-repo.patch` is **archived as
an alternative** and is NOT applied in a normal build. The two are mutually
exclusive: enabling both makes git-repo raise

```
ManifestParseError: remove-project element specifies non-existent project
```

So patches 0001-0004 are always applied; 0005 is applied **only** if you are
deliberately choosing the patch-based flow **instead of** the local manifest.


```bash
git clone --branch fifteen https://github.com/PixelOS-AOSP/manifest.git mf
git -C mf checkout 0334d5e468a86ab0aefa6d3a40bc2abd11bf4035
git -C mf apply --check ../patches/0005-manifest-gms-repo.patch

git clone --branch lineage-22.2 https://github.com/LineageOS/android_device_xiaomi_equuleus eq
git -C eq checkout db40750f063e86110e20db1455729c0f6621f7da
git -C eq apply --check ../patches/0001-equuleus-product-setup.patch
git -C eq apply --check ../patches/0002-equuleus-drop-lineage-sdk-overlay.patch

git clone --branch lineage-22.2 https://github.com/LineageOS/android_device_xiaomi_sdm845-common cm
git -C cm checkout 35cf356b095e033e71261b16c7fa319faac12cb3
git -C cm apply --check ../patches/0003-sdm845-common-use-vendor-aosp.patch
git -C cm apply --check ../patches/0004-sdm845-common-drop-lineage-overlays.patch
```

Order matters within each repository: 0001 before 0002, 0003 before 0004.
0005 targets the **manifest** repository (`snippets/custom.xml`), not a device tree.

---

## C. Rebuild the full evidence base

The full working tree is a separate, larger artefact (~683 MiB) containing
`src/` snapshots and real git clones. To recreate it from scratch:

```bash
# 1. the nine pinned clones, with HEAD compared to each pin
scripts/fetch_clones.sh --dest ./clones

# 2. the local manifest
# The local manifest is already at .repo/local_manifests/equuleus.xml in this
# archive; scripts/sync.sh installs it into the real repo tree. No copy needed.

# 3. full acceptance
python3 scripts/verify_deliverables.py
#    -> 24/24 expected once src/ + clones/ exist
```

`fetch_clones.sh` fails loudly if any clone's HEAD differs from its pin.

---

## D. Build attempt (not performed here)

```bash
bash scripts/host-preflight.sh --tree /data/pixelos15   # stage 1: environment
bash scripts/sync.sh /data/pixelos15                    # repo sync + patches 0001-0004
                                                        # (0005 archived, NOT applied)
#   ... obtain the five firmware images and run BLOB_EXTRACTION.md ...
bash scripts/build-preflight.sh /data/pixelos15         # stage 2: sources + blobs
python3 scripts/verify_blobs.py /data/pixelos15
bash scripts/build.sh /data/pixelos15 userdebug
```

`build.sh` refuses to report success unless a `PixelOS_*.zip` **and**
`recovery.img` exist, and it re-runs both preflight stages plus
`verify_blobs.py` before compiling.

**Compiling is not booting. Booting is not working hardware.**

---

## E. Environment notes

* Several AIDL paths exceed Windows' 260-character `MAX_PATH`. Both the packer
  and `extract_audit_package.py` route filesystem calls through the `\\?\`
  long-path prefix. Plain `unzip`/`zipfile.extractall()` **will fail** on those
  entries.
* The archive is written with `
` line endings and validated to be
  byte-identical after a round trip.
