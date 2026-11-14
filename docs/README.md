# PixelOS 15 (fifteen) for Xiaomi Mi 8 Pro — `equuleus`

A device port package: **source-side ready, binary-side blocked.**

| | |
| --- | --- |
| Target ROM | PixelOS Android 15 (`PixelOS-AOSP/manifest@fifteen`, archived 2025-06-18) |
| LineageOS baseline | `lineage-22.2` |
| Device | Xiaomi Mi 8 Pro, codename `equuleus`, SDM845, non-A/B, dynamic partitions |
| Status | blobs extracted and verified; trees patched (7 build patches); **no ROM compiled, nothing flashed** |

> **Honest one-liner:** this repository gets the source tree to the point where a
> build *can* be attempted. It does not contain a working ROM, and it does not
> claim one. See `TEST_REPORT.md` — the third bucket ("not executed") is long.

## Current build state

| Item | State |
| --- | --- |
| B-01 proprietary blobs | **generated** — 872 files / 546,824,712 bytes across `vendor/xiaomi/{equuleus,sdm845-common}`; strict verification `FAIL=0`, 862/862 declared entries present (5 APKs `RESIGNED` by LineageOS re-signing) |
| Extraction method | this project's block-OTA extractor (`ota_extract.py` + `make_vendor_trees.py`), **not** upstream `extract-files.py` |
| `extract-files.py` cross-check | **NOT DONE** — needs a fully synced PixelOS tree for Soong name resolution |
| Patches applied by a normal build | **7**: 0001-0004, 0006, 0007, 0008. **0005 is archived and never applied** |
| ROM compiled | **NO** |
| Flashed / device-tested | **NO** |
| IR face unlock | **NOT VERIFIED ON DEVICE** — `camera_id=5` is inferred, never measured on hardware |
| MIUI IR blob analysis | done — OV9282 driver stack **byte-identical** to LineageOS, so nothing to port |
| IR illuminator control | **NOT VERIFIED** — mechanism undetermined; not inferred from files |
| First ROM build | **NOT EXECUTED** — needs a Linux host with ~165 GiB and Google source access; see `FIRST_BUILD_RUNBOOK.md` |
| FOD / camera / NFC | **NOT VERIFIED ON DEVICE** |


---

## Read in this order

| Document | What it answers |
| --- | --- |
| **`TEST_REPORT.md`** | What was actually run, what failed, what was never attempted. Start here. |
| **`KNOWN_BLOCKERS.md`** | tracked blockers with severity, evidence and status. B-01 (blobs) is closed for extraction; the open items all need hardware. |
| **`CLOUD_READINESS.md`** | Whether to rent an ECS box (16 vCPU / 64 GiB / 600 GiB SSD), and why the answer is "not yet". |
| **`UPSTREAM_LOCK.md`** | Every pinned commit SHA, and why each fork was chosen. §9 shows the 8 real `git clone`s whose HEAD equals each pin. |
| **`DEVICE_AUDIT.md`** | How FOD, camera and NFC are wired, and exactly what is unverified. |
| **`BLOB_EXTRACTION.md`** | The lawful path to `vendor/xiaomi/*`. The current, executed route is one official LineageOS OTA (see `B01_EXTRACTION_REPORT.json`); the legacy five-firmware-image route is retained as background only. |

---

## What is in the box

```
.repo/local_manifests/equuleus.xml   the 4 device-side projects + 1 extend-project, all SHA-pinned
patches/0001-equuleus-product-setup.patch
patches/0002-equuleus-drop-lineage-sdk-overlay.patch
patches/0003-sdm845-common-use-vendor-aosp.patch
patches/0004-sdm845-common-drop-lineage-overlays.patch
patches/0005-manifest-gms-repo.patch        ARCHIVED alternative for vendor/gms (NOT used in a normal build)
patches/0006..0008                          build patches: NFC path, IR camera id, aux allow-list
VENDOR_TRANSFER.md                          how to get the real blobs onto a build machine
FIRST_BUILD_RUNBOOK.md                      the cloud build sequence (NOT YET EXECUTED)
MIUI_IR_BLOB_INVENTORY.md                   what the factory MIUI firmware contains
MIUI_VS_LINEAGE_IR_DIFF.md                  byte-level MIUI vs LineageOS IR comparison
IR_FACE_UNLOCK_DEPENDENCIES.md              IR unlock dependency chain + device test plan
out/vendor-archive/                         verifiable blob archive + per-file SHA256 manifest
scripts/host-preflight.sh            stage 1/2: environment only (runs on an empty instance)
scripts/build-preflight.sh           stage 2/2: sources + blobs after sync
scripts/preflight.sh                 deprecated wrapper, dispatches to the stage above
scripts/verify_blobs.py              authoritative blob check (dst, renames, SONAME)
scripts/sync.sh                      pinned, resumable sync; never --force-sync
scripts/build.sh                     builds, then refuses to claim success without artifacts
scripts/verify_deliverables.py       the 24-check static acceptance suite
scripts/verify_mutations.py          mutation-tests that suite (28 seeded defects)
clones/                              real git clones proving every pin is a commit object
src/                                 pristine upstream snapshots used for patch verification
work/                                review commits the patches were exported from
logs/                                SHA table and captured command output
```

---

## Quick start (on a Linux host that can actually build)

```bash
# 1. gate the MACHINE first - runs on an empty instance, needs no sources
bash scripts/host-preflight.sh --tree /data/pixelos15

# 2. sync at the pinned revisions
bash scripts/sync.sh /data/pixelos15

# 3. obtain the proprietary blobs — see BLOB_EXTRACTION.md (this is the blocker)
#    vendor/xiaomi/equuleus and vendor/xiaomi/sdm845-common must both exist

# 4. gate the TREE, then build (build.sh re-runs both gates itself)
bash scripts/build-preflight.sh /data/pixelos15
python3 scripts/verify_blobs.py /data/pixelos15
bash scripts/build.sh /data/pixelos15 userdebug

# 5. static self-check of this deliverable at any time
python3 scripts/verify_deliverables.py
```

`lunch` target: **`aosp_equuleus-bp1a-userdebug`**
(`bp1a` comes from `vendor/aosp/vars/aosp_target_release`).

---

## What the four patches do

1. **0001 — product setup.** Rename `lineage_equuleus.mk` → `aosp_equuleus.mk`,
   inherit `vendor/aosp/config/common_full_phone.mk` instead of
   `vendor/lineage/…`, declare the real lunch choices. PixelOS' `envsetup.sh`
   requires the `aosp_` prefix for custom builds.
2. **0002 — drop a dead overlay.** `equuleus/overlay-lineage/lineage-sdk/`
   targets `lineage-sdk`, which PixelOS fifteen does not check out. An overlay
   with no target package aborts resource merging.
3. **0003 — build policy.** Point `sdm845-common` at
   `vendor/aosp/config/{device_framework_matrix.xml,BoardConfigReservedSize.mk}`
   and document, at the call site, the two ways these files are *weaker* than
   the LineageOS originals (B-06, B-07).
4. **0004 — drop two more dead overlays.** `lineage-sdk` and the LineageOS
   Dialer's `callrecord` resources do not exist in PixelOS' app set.

Each patch applies to the exact commit recorded in `UPSTREAM_LOCK.md` §4; that
is verified in `TEST_REPORT.md` §1 items 7–12.

---

## Environment constraints worth knowing before you start

* **Case-sensitive filesystem required** (ext4/xfs/btrfs). NTFS/exFAT will fail
  in confusing ways.
* **`android.googlesource.com` must be reachable.** It was *not* reachable from
  the machine this audit ran on, which alone makes `repo sync` impossible there.
* **`PixelOS-AOSP/vendor_gms` has no `fifteen` branch** (GitLab, `sixteen` only):
  the manifest's only `PixelOS-Gitlab` project cannot resolve at that revision
  (B-14). Whether that breaks the sync outright or only an unused subtree will
  be known on the first real sync; the AOSP product targeted here does not
  inherit GMS.
* **`repo` does not read `revision_lock.xml` automatically** (B-12). Pins live in
  `.repo/local_manifests/equuleus.xml` for that reason.

---

## Reproducing the static verification

```bash
python3 scripts/verify_deliverables.py
# expected: 24/24 checks passed
```

The suite re-derives its conclusions rather than trusting the prose: it parses
the local manifest against the real upstream `default.xml` + snippets, applies
all four patches to pristine `src/` copies in a temp dir, and re-runs every
product/BoardConfig assertion against *that patched tree* — so a patch that is
merely self-consistent cannot pass.

Its final line is deliberately blunt:

```
ALL STATIC CHECKS PASSED — this proves nothing about compiling or booting.
```

---

## What is explicitly *not* here

* No proprietary binaries, no `.so`, no firmware — nothing redistributable.
* No prebuilt or hosted `vendor/xiaomi` repository reference.
* Never `repo sync --force-sync`, never pipe `curl` into a shell, never
  destructive deletes.
* No SELinux permissive workarounds.
* No claim of a successful compile, boot, or working FOD/camera/NFC.
