# CLOUD_READINESS — should you rent an ECS server yet?

Short answer: **yes, rent a pay-as-you-go instance to run the first build.**
B-01 (proprietary blobs) is **closed for extraction**: the two vendor trees were
generated from the official LineageOS OTA and pass strict verification. What is
still unknown is whether the tree *compiles* — which is precisely what the
instance is for. What remains NOT VERIFIED is anything needing the phone in
hand: boot, IR face unlock, FOD, camera, NFC.

This document separates three things that are routinely conflated:

1. Is the *source tree* ready to sync and build? (yes, for the device side)
2. Is the *build* going to succeed? (unknown — nothing was ever compiled)
3. Is the *result* going to be a usable phone? (very likely no, on the first
   attempt, for camera and blobs)

---

## 1. Gate condition — all four must be true before paying for anything

| Gate | Requirement | Current state |
| --- | --- | --- |
| **P0** | Every device-side dependency pinned to a full commit SHA, with a reviewable manifest | ✅ **MET** — `.repo/local_manifests/equuleus.xml`, 5 pinned projects + 1 `<remove-project>`/re-add for `vendor/gms`, `UPSTREAM_LOCK.md` §4 |
| **P1** | Device-tree changes expressed as patches that apply cleanly to the pinned upstream commits | ✅ **MET** — `sync.sh` applies **7** patches (0001-0004, 0006-0008). Patch 0005 exists and applies cleanly but is **archived and never applied**, because it conflicts with the local-manifest GMS override. All 8 verified with `git apply --check` against real clones. |
| **P2** | A lawful path to the proprietary blobs, with a concrete extraction procedure | ✅ **MET** — one official LineageOS 22.2 OTA (sha256-verified) yields both trees: **872 files / 546,824,712 bytes**, strict verification `FAIL=0`, 862/862 declared entries present. Shippable archive + per-file SHA256 in `VENDOR_TRANSFER.md`. The legacy five-firmware-image route is no longer needed. |
| **P3** | Reproducible revision capture | ✅ **MET** — `sync.sh` executes `repo manifest -r` and persists `MANIFEST_LOCK.xml` + `MANIFEST_LOCK.tsv`; a failed capture prints a loud warning instead of being silently skipped |
| **P4** | `sync.sh` and `build.sh` exist, are fail-fast, log, and refuse to report false success | ✅ **MET** — `build.sh` exits 3 if the ROM zip or `recovery.img` is missing; it runs both preflight stages and `verify_blobs.py` before compiling |

The GMS question (previously B-14) is resolved for *availability*:
`vendor/aosp/config/common.mk:5` inherits `vendor/gms/products/gms.mk`
unconditionally, and upstream's `vendor/gms` has no `fifteen` branch.

**How this project resolves it — one mechanism only:**

GMS 仓库替换：正式构建**只**通过 `.repo/local_manifests/equuleus.xml`
（`<remove-project name="vendor_gms"/>` + 重新加入 `vendor_gms-15`）。
`patches/0005-manifest-gms-repo.patch` **不参与正式构建**，仅作为备选方案归档；
两者互斥，同时启用会导致 `ManifestParseError`。

Anyone re-deriving the tree by hand must use the same one mechanism; applying
0005 on a tree that already carries the local manifest will fail to parse.

**Verdict: P0, P1, P2, P3, P4 all pass.** Buying a 64 GiB instance today would
let you sync ~100 GiB and then stop at the blob step with a tree that cannot be
built. The ordering that actually saves money is: **rent → sync → extract with
the phone attached over USB → build**, or **extract locally first, then rent**.

### 1.1 The honest recommendation

* If you want to know whether it compiles: **rent a pay-as-you-go instance**,
  run stage 1, sync, receive the blob archive, build. Expect 2–4 failed builds.
  The blob work needs **one** LineageOS OTA, already extracted; the five
  legacy firmware images are no longer required.
* If what you want is *device-verified* features: **do not rent anything.** No
  cloud server can verify IR unlock, FOD, camera or NFC — those need the phone.
  Renting buys a compile result, nothing more.
* Do **not** buy a reserved/committed instance. This is a prototype on an
  archived ROM branch (B-03).

---

### 1.2 Round-5 update — what the independent review changed

The reviewer's verdict was **NO-GO**, and it was correct at the time. Three of
its findings were hard blockers for a spend:

| Finding | Effect on the purchase decision | Now |
| --- | --- | --- |
| `sync.sh` aborted on an unset `${PYTHON}` under `set -euo pipefail` | the sync could never start, so any rented instance would burn hours and fail immediately | fixed, with a line-ordering regression check |
| local manifest and `patches/0005` both repointed `vendor/gms` | git-repo raises `ManifestParseError`, so the sync would die at manifest parse | fixed: one mechanism only (local manifest), 0005 archived as an alternative, guarded, verified with the real parser |
| ZIP lost the Unix execute bit | `build.sh` skipped its preflight gate, so a broken tree looked buildable | fixed in the packer **and** in `build.sh` (no longer gates on `-x`) |

Additionally, a failed `repo manifest -r` and an unreviewed manifest HEAD are
now **fatal** rather than advisory, so an un-reproducible tree cannot be
mistaken for a good one.

**However, the gate that still blocks a purchase is unchanged: P2.** No
proprietary blob has been obtained, and `sdm845-common` needs **five** firmware
images. Cloud hardware cannot fix that. (Superseded: the blobs now come from one
run a cheap network-only preflight first is consistent with this document:
`scripts/host-preflight.sh` (stage 1) needs no sources and no blobs.

**Revised recommendation.**
* Do **not** buy the 16 vCPU / 64 GiB instance yet — P2 is still open.
* If you want to de-risk the network before committing: run
  `bash scripts/host-preflight.sh --tree /data/pixelos15` on a **small**
  pay-as-you-go instance. It exits non-zero on an unusable host and touches
  nothing else. That is cheap and answers the googlesource-reachability
  question the audit host could not.
* The full-size instance makes sense once you want a *complete* build rather
  than a compile check, because the blobs are already in hand.

---

### 1.3 Round-6 update — a cheap network preflight is now a supported mode

`scripts/host-preflight.sh --network-only` checks **only** connectivity and TLS:

```bash
bash scripts/host-preflight.sh --network-only
```

It skips platform, toolchain, CPU/RAM and disk entirely (those sections are
inside an `if (( ! NETWORK_ONLY ))` guard), so it runs on the smallest
pay-as-you-go instance you can rent — or on a container, or a laptop. It probes
real git transport against github.com, gitlab.com and android.googlesource.com,
plus curl-level HTTPS and a CA/TLS check.

**Measured on the audit host:** `NETWORK NOT READY — 5 failures`, exit 1.
`android.googlesource.com` is unreachable from here while GitHub and GitLab
answer normally. Since `repo` fetches the AOSP base from googlesource, this
single fact means **no instance behind this network can complete a sync**,
regardless of CPU, RAM or disk.

That is the whole point of the mode: it converts a 165 GiB / ~¥100 experiment
into a five-minute one.

**Recommended sequence, unchanged in substance but now cheaper to start.**

1. Rent the *smallest* pay-as-you-go Linux x86_64 instance in a candidate
   region. Run `--network-only`. If it fails on `android.googlesource.com`,
   change region or provider; do not rent the big machine.
2. Only once the network gate passes does `host-preflight.sh` (full mode) make
   sense — it needs 16 vCPU / 64 GiB / 400 GiB free.
3. The purchase is still gated on **P2**: blobs. No amount of network or CPU
   produces the two vendor trees (already done; kept for re-derivation).

**Verdict: GO for a pay-as-you-go compile check.** The full-size instance is
justified once a first build succeeds. As before, nothing about B-01 (proprietary
blobs) closes. A network-only instance is a different, much smaller spend and is
now explicitly supported.

---

### 1.4 Round-7 update — artifact integrity, and what it does not mean

The build script now refuses to report a result unless the ROM zip is **newer
than the build start time**, the archive passes `unzip -t`, `recovery.img` is
present and fresh, and the OTA asserts `pre-device=equuleus`. All of those were
warnings or absent before; a stale zip could be presented as this run's output.

This matters for a paid instance in one specific way: a long build that fails
late previously left earlier artifacts in `out/`, and a careless re-run could
"confirm" success with them. The freshness gate removes that. It does **not**
make a build more likely to succeed.

**What is still unproven, and drives the verdict.** Nothing below has ever run
against a real tree:

* `repo sync` of the ~1,095-project manifest;
* `repo manifest -r` producing a real lock;
* `lunch` / Soong / `mka bacon`;
* the artifact gate itself, because no build has produced artifacts to check.

So the **NO-GO for the 16 vCPU / 64 GiB instance stands**, and the only
recommended spend remains the small `--network-only` preflight from §1.3.

The docs' patch count was also corrected: `sync.sh` applies **0001-0004**;
patch 0005 is archived and never applied. A negative test now fails the suite if
any document drifts from that.

---

### 1.5 Round-8 update — B-01 has a single 1.2 GiB source now

The blob blocker no longer requires hunting five historical firmware images. The
official LineageOS 22.2 equuleus OTA supplies both `vendor/xiaomi` trees,
because that build is produced from the same four repositories this project
pins. Source, SHA256 and verified format facts: `BLOB_SOURCES.md`.

**This changes the economics of the first real build**, and only that:

| | Before | Now |
| --- | --- | --- |
| Firmware to obtain | 5 images, several from third-party mirrors | **1 official LineageOS ZIP**, 1.2 GiB, published SHA256 |
| Provenance risk | mixed, partly unverifiable | signed build from the LineageOS download API |
| Extraction order | manual, per group | one script, `sdm845-common` then `equuleus` |

**What has NOT changed.** The 1.2 GiB download has not been performed here; the
OTA was only range-read (first 1 MiB) to verify its format and device
assertion. `extract-files.py` has not run, both `vendor/xiaomi/*` trees are
still absent, and `verify_blobs.py --strict` has never seen a real blob.

So the purchase gate is unchanged in substance: the full 16 vCPU / 64 GiB
instance is still **NO-GO until the extraction actually completes and strict
verification passes on the machine that owns the tree**. The difference is that
the remaining work is now a two-command step with a known input, rather than a
research task.

**Recommended order on a rented instance**

1. `scripts/host-preflight.sh --network-only` — cheapest gate; confirms
   `android.googlesource.com` is reachable from that region.
2. Full `host-preflight.sh` — 16 vCPU / 64 GiB / 400 GiB free.
3. `scripts/sync.sh` — repo sync + patches 0001-0004 (0005 archived).
4. `scripts/fetch_lineage_ota.sh` — download and verify the OTA.
5. `scripts/extract_blobs_from_ota.sh` — generate both trees.
6. `python3 scripts/verify_blobs.py --strict --json blob-report.json`
7. Only then `scripts/build.sh`.

Step 5 is the one that decides whether the purchase was worth it; everything
before it is cheap or reversible.

---

### 1.6 Round-12 update — the blobs now exist, and they can be shipped

B-01 is no longer a plan. The vendor trees were generated from the official
LineageOS 22.2 OTA and verified:

| | |
| --- | --- |
| Files | 872 |
| Size | 546,824,712 bytes (521 MiB) |
| Strict verification | `FAIL=0`, 862/862 declared entries present |
| Archive | 194 MiB `tar.xz`, per-file SHA256 manifest, 200 MiB volumes |

Transfer procedure, checksums and failure modes: `VENDOR_TRANSFER.md`.

**What this changes about renting a machine.** The last unknown that justified
waiting — "we have no blobs to build with" — is gone. A rented instance can now
receive a verified, self-checking archive in minutes. What remains unproven is
whether the tree *compiles*, and that is exactly what the instance is for.

**What it does not change.** Still true:

* no ROM has been compiled;
* `extract-files.py` has never cross-checked these trees (our extractor took a
  different code path);
* IR face unlock, FOD, camera and NFC are unverified on hardware.

**A normal build applies 7 patches** (0001-0004, 0006-0008). Patch 0005 is
archived and is never applied — applying it conflicts with the local-manifest
GMS repoint.

**Sequence on a rented instance**

1. `scripts/host-preflight.sh --network-only` — cheapest gate; confirms
   `android.googlesource.com` is reachable from that region.
2. `scripts/host-preflight.sh` — full environment check.
3. `scripts/sync.sh` — repo sync + the 7 patches.
4. `VENDOR_TRANSFER.md` — receive and verify the blob archive.
5. `python3 scripts/verify_blobs.py <tree> --strict` — the real blob gate.
6. `scripts/build.sh` — re-runs all gates, then compiles.

---

## 2. Recommended machine

| Resource | Recommendation | Why exactly this |
| --- | --- | --- |
| **vCPU** | **16** | AOSP's Soong/kati phase is heavily parallel; PixelOS' own build docs assume 16. 8 vCPU roughly doubles wall time and, worse, makes OOM more likely during `dex2oat`/`clang` spikes. |
| **RAM** | **64 GiB** | This is the binding constraint, not CPU. Linking `libLLVM`, `dex2oat` on a full framework image, and `soong_build` on a 100k-target graph all spike. 32 GiB builds usually die with `internal compiler error: Killed (program cc1plus)`, which looks like a compiler bug and is not one. 16 GiB will not finish. |
| **Disk** | **600 GiB SSD** | Breakdown: source tree ~110 GiB, `.repo` ~55 GiB, `out/` 90–130 GiB, ccache (optional) 30–50 GiB, tarballs/blobs ~20 GiB, headroom. ext4/xfs/btrfs — **must be case-sensitive**. 400 GiB works if you skip ccache and build once; it is not comfortable across 3+ iterations. |
| **OS** | **Ubuntu 22.04 or 24.04 LTS, x86-64** | These are the configurations PixelOS/AOSP document. ARM instances cannot build AOSP (no prebuilt host toolchain). |
| **Filesystem** | ext4 or xfs | NTFS/exFAT break file modes and symlinks; AOSP will fail in ways that look like source bugs. |
| **Swap** | 8–16 GiB, low swappiness | Cheap insurance against a single link-step spike killing a 4-hour build. |
| **Billing** | **pay-as-you-go / spot, shut down after each build** | A full build is 3–6 h on 16 vCPU. A 24/7 instance is pure waste between iterations. |
| **Network** | Unrestricted HTTPS egress to `github.com`, `android.googlesource.com`, `gitlab.com` | `android.googlesource.com` is the hard requirement — it was unreachable from the audit host, which is the single strongest argument for renting. |
| **Region** | Any with good RTT to those hosts; CN-mainland regions often throttle googlesource | Test with `curl -o /dev/null -w '%{http_code}' https://android.googlesource.com/` before committing to a region. |

Concrete instance classes that fit (any provider): 16 vCPU / 64 GiB / 600 GiB
SSD is roughly `ecs.g7.4xlarge` + ESSD, `c6i.4xlarge`, or equivalent. Nothing
here is provider-specific — the requirement is the numbers, not the brand.

---

## 3. What to run, in order — two distinct gates

The checks are deliberately split, because they answer different questions at
different times. Stage 1 can and should run on a **brand-new instance with an
empty disk**, before you pay for storage or download 165 GiB.

### Stage 1 — `host-preflight.sh` (environment only)

```bash
bash scripts/host-preflight.sh --tree /data/pixelos15
```

Checks: x86_64, Linux, Ubuntu family, JDK >= 17, `git/curl/python3/unzip/zip/
bc/bison/flex/make/gcc/g++/lz4/rsync`, `repo`, **16 vCPU / 64 GiB RAM / swap /
400 GiB free / case-sensitive FS**, and reachability of
`android.googlesource.com`, `github.com`, `gitlab.com`, plus proxy/TLS sanity.

It checks **nothing** about sources, patches or blobs. That is intentional: a
fresh ECS instance has none of them. Exit 0 = the machine is adequate.

### Between the stages

```bash
bash scripts/sync.sh /data/pixelos15        # ~1-2 h, 165 GiB, applies 0001-0004 + 0006-0008
                                            # (0005 is archived, NOT applied);
                                            # runs `repo manifest -r` (P0-4)
# then obtain firmware and follow BLOB_EXTRACTION.md (the actual blocker)
```

### Stage 2 — `build-preflight.sh` (sources + blobs only)

```bash
bash scripts/build-preflight.sh /data/pixelos15
python3 scripts/verify_blobs.py /data/pixelos15     # authoritative blob check
```

Checks: tree skeleton, the 7 pinned project HEADs (including `vendor/gms`), each
patch applied (verified by *reverse* application), the `aosp_equuleus` product,
`vendor/xiaomi/*` trees with `BoardConfigVendor.mk` / `*-vendor.mk` /
`Android.bp`, and free space for `out/`. It does not re-check CPU/RAM/FS.

`build.sh` runs both gates automatically before compiling and refuses to
proceed if either fails.

`scripts/preflight.sh` is now a thin deprecated wrapper that dispatches to
stage 1 (no argument) or stage 2 (with a tree).

### Why this split is not cosmetic

The old single script mixed both questions. On a fresh instance it failed for
"missing blobs" reasons that are *expected at that point*, which trains the
operator to ignore failures. After the split, a stage-1 `[FAIL]` always means
"this machine cannot do the job", and a stage-2 `[FAIL]` always means
"an input is missing or the wrong revision".

## 4. Cost realism (order of magnitude, not a quote)

* 16 vCPU / 64 GiB pay-as-you-go: roughly **¥4–12 per hour** depending on
  provider, region and disk class.
* One build attempt: 4–6 h including sync amortisation ≈ **¥20–70**.
* Expect **3–5 attempts** to get from first sync to a bootable image (camera and
  blobs will each cost at least one). Budget **¥100–350** for the source-to-boot
  phase, plus ¥20–50 of storage per month if you keep the tree between sessions.
* Keeping a 600 GiB SSD online 24/7 for a month is *more expensive than the
  builds themselves* — snapshot the disk and destroy the instance instead.

The expensive part is not the compute. It is the **firmware/blob reconstruction
(B-01)**, which needs a physical phone and cannot be outsourced to a server.

---

## 5. What a successful build would and would not prove

| Would prove | Would NOT prove |
| --- | --- |
| The device trees are syntactically and semantically consistent with PixelOS fifteen | That the ROM boots |
| No missing `include`/`inherit-product` path | That the display comes up |
| The kernel compiles with the chosen clang | That FOD works |
| A ROM zip and `recovery.img` were produced | That the camera works |
| Artifacts are reproducible from the pinned SHAs | That NFC works |
| Nothing | Anything about battery, thermal, modem, calls, DRM |

**Compile ≠ boot ≠ FOD/camera/NFC working.** Three separate milestones, each
with its own failure modes. Any claim that skips a milestone is false.

After a successful compile, the real work starts: flashing, `logcat`, `dmesg`,
`avc` denial triage, and the per-subsystem verification list in
`TEST_REPORT.md` §3.

---

## 6. Decision table

| Situation | Do this |
| --- | --- |
| Phone available, firmware obtainable, want to try | Rent pay-as-you-go 16/64/600, run the 6 steps in §3 |
| Phone available, firmware not obtainable | Do not rent. Resolve firmware provenance first; a rented server cannot fix B-01 |
| No phone | Do not rent. The deliverable is complete as far as static work goes; stop here |
| Want a daily driver | Do not use this build. PixelOS fifteen is archived (B-03); wait for a maintained branch port |
| Want to contribute upstream | Send the 7 build patches to LineageOS/PixelOS review, not a rented server |

---

## 7. Bottom line

The source-side work is finished, pinned, and mechanically verified. The
machine spec is **16 vCPU / 64 GiB / 600 GiB SSD, Ubuntu x86-64,
pay-as-you-go**. But the gate that is still closed is **P2 — the blobs**, and no
amount of cloud hardware opens it.
