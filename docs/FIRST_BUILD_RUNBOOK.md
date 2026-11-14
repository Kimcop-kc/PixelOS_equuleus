# FIRST_BUILD_RUNBOOK — the sequence to run on Alibaba Cloud ECS

**Status of everything in this document: NOT EXECUTED by this project.**
No `repo sync` has run, no Soong/Make check has run, and no ROM has been
compiled. This runbook is the sequence to execute on a real Ubuntu 22.04 build
host; it is not a report of results.

The development host is Windows 11 (16 vCPU, 13 GiB RAM, 16 GiB free disk, no
`repo` tool, `android.googlesource.com` unreachable). A full PixelOS sync needs
~165 GiB and the Google source endpoint, so the build cannot be performed here.
That is the reason to rent an instance, and the only honest way to get a build
result.

---

## 0. Why a build host is required

| Requirement | This host | ECS |
| --- | --- | --- |
| free disk | **16 GiB** | **≈600 GiB** data disk (see §1) |
| `repo` tool | absent | installable |
| `android.googlesource.com` reachable | **blocked** | depends on region — test first |
| Bash on Linux with GNU toolchain | Git-bash emulation | native |

## 1. Provision the instance, then gate on network before spending hours

### 1.1 What to buy

| Resource | Size | Why |
| --- | --- | --- |
| vCPU | 16 | Soong saturates cores; fewer makes the build much slower |
| RAM | 64 GiB | linking and `soong_build` peak well above 32 GiB |
| **Data disk** | **≈600 GiB on `/data`** | source ~110 GiB + `.repo` ~55 GiB + `out/` 90–130 GiB + ccache 30–50 GiB + blobs/tarballs ~20 GiB + headroom |
| OS disk | default is fine | **build on the data disk, never the system disk** |

A 400 GiB data disk is the hard floor (`build.sh` refuses below 100 GiB *free* at
build time, but the source tree itself needs far more than that). 600 GiB is the
recommended size so that 3+ build iterations and ccache both fit.

**Do not put the sources on `/` (the ~40 GiB system disk).** A review caught this
exact mistake: `host-preflight.sh` was documented without `--tree`, so it audited
the small system disk, passed, and the sync then ran out of space hours later.

Mount and use `/data` for everything:

```bash
lsblk                                   # find the data disk, e.g. /dev/vdb
sudo mkfs.ext4 /dev/vdb                 # DESTROYS that disk; confirm the device first
sudo mkdir -p /data && sudo mount /dev/vdb /data
echo '/dev/vdb /data ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
df -h /data                             # must show ~600G available
```

The filesystem **must be case-sensitive** (ext4/xfs/btrfs). A case-insensitive
mount produces confusing duplicate-file errors during the build.

### 1.2 Get the project onto the instance

The project directory (`/opt/port`) is the **tooling**: scripts, patches, docs,
manifests. It is not the Android source tree — that goes on `/data`.

Deploy by uploading the review ZIP, which is self-contained and has no network
dependency beyond your own upload:

```bash
# on your workstation
scp PixelOS_equuleus_AUDIT_PACKAGE.zip user@<ecs-ip>:/tmp/
ssh user@<ecs-ip>
sudo mkdir -p /opt/port && sudo chown "$USER" /opt/port
cd /opt/port
unzip -q /tmp/PixelOS_equuleus_AUDIT_PACKAGE.zip
# the ZIP extracts one top-level directory; flatten it into /opt/port
shopt -s dotglob && mv PixelOS_equuleus_AUDIT_PACKAGE/* . && rmdir PixelOS_equuleus_AUDIT_PACKAGE
ls scripts/sync.sh scripts/build.sh      # both must exist
# the shipped manifests let you confirm the archive was not altered in transit
sha256sum -c evidence/blob-archive/VOLUMES.sha256
```

If the ZIP cannot be used, `git clone` the project repository — but **verify the
clone succeeded**. Never write `git clone … || true`: that hides a failed
download and leaves you running stale or absent tooling, which is exactly how a
"successful" build turns out to have used the wrong scripts.

```bash
git clone <the real, existing URL> /opt/port
rc=$?
[ "$rc" -eq 0 ] || { echo "project clone FAILED (rc=$rc); stop"; exit 1; }
[ -x /opt/port/scripts/sync.sh ] || { echo "clone is missing scripts/; stop"; exit 1; }
```

### 1.3 Network gate — cheapest possible check

```bash
cd /opt/port
bash /opt/port/scripts/host-preflight.sh --network-only
```

If `--network-only` fails, **stop**. No amount of local work fixes an unreachable
source endpoint; change region or use a mirror. Everything after this point costs
hours.

### 1.4 Full environment check — **always pass `--tree`**

```bash
bash /opt/port/scripts/host-preflight.sh --tree /data/pixelos15
```

Without `--tree`, the script audits whatever filesystem the current directory is
on — on a fresh ECS that is the small system disk, so it passes while the build
disk is the one that matters. `--tree` makes it judge `/data`.

## 2. Sync the sources — one command, no manual steps

`sync.sh` does the entire initialisation: `repo init` against the pinned manifest
branch, installs the local manifest (5 pinned projects, `vendor/gms` repoint),
runs a resumable `repo sync`, applies the **7** build patches (0001-0004,
0006-0008), verifies the patched content, and captures `MANIFEST_LOCK.xml`/`.tsv`.

Do **not** run `repo init` or `repo sync` by hand first. Doing both is how trees
end up half-initialised with a stale manifest; and a hand-run `repo sync` after
`sync.sh` would not re-apply the patches.

```bash
mkdir -p /data/pixelos15
cd /opt/port
bash /opt/port/scripts/sync.sh /data/pixelos15
```

Notes on what it deliberately does **not** do:

* **no `--force-sync`** — it discards local commits in every project, which would
  destroy the 7 patches on any later re-run;
* **no `|| true` on any network step** — a failed init or sync aborts with a
  non-zero exit instead of continuing against an incomplete tree.

Expected end state:

```
  [APPLIED] 0001 … 0008                 7 patches
  [OK] vendor/xiaomi/equuleus present
  [OK] vendor/xiaomi/sdm845-common present
  wrote /data/pixelos15/MANIFEST_LOCK.xml
```

If the blob trees show `[MISSING]`, that is expected on a fresh sync — do §3.
If a patch reports it applies neither forward nor in reverse, the tree is not at
the pinned base: stop and investigate rather than forcing it.

### 2.1 Soong/Make configuration check (before a full compile)

```bash
cd /data/pixelos15
source build/envsetup.sh
lunch aosp_equuleus-bp1a-userdebug
m nothing
```

`lunch aosp_equuleus-bp1a-userdebug` — the **`-bp1a-`** release segment is
required; `aosp_equuleus-userdebug` does not resolve, because this port sets
`aosp_target_release=bp1a`. `m nothing` resolves the whole product graph and
parses every `Android.bp` without compiling, so a broken dependency or a bad
`BoardConfig` shows up in minutes instead of hours.

## 3. Deliver the blobs

Either receive the prepared archive (fastest, checksum-verified):

```bash
cd /data/transfer
sha256sum -c VOLUMES.sha256
cat vendor-xiaomi-*.tar.xz.part* > vendor.tar.xz
sha256sum vendor.tar.xz            # must equal the value from 'prepare'
tar -xJf vendor.tar.xz -C /data/pixelos15
cd /data/pixelos15 && sha256sum -c /data/transfer/MANIFEST.sha256
```

or regenerate them from the official OTA:

```bash
cd /opt/port
bash /opt/port/scripts/extract_vendor_full.sh \
     --ota lineage-22.2-*-equuleus-signed.zip --tree /data/pixelos15
```

Then run the real blob gate:

```bash
python3 /opt/port/scripts/verify_blobs.py /data/pixelos15 --strict --json blob-report.json
```

Expected: `OK=0 FAIL=0 RESIGNED=5 UNVERIFIABLE=0 SKIPPED=857`.
`RESIGNED=5` is expected — LineageOS re-signs five platform APKs.

## 4. First build

```bash
cd /opt/port
bash /opt/port/scripts/build.sh /data/pixelos15
```

`build.sh` runs, in order, and aborts on any failure:

| # | Gate | Fails when |
| --- | --- | --- |
| 1 | preconditions | tree/config missing |
| 2 | stage-1 host preflight | environment wrong |
| 3 | stage-2 dependency preflight | a required package is absent |
| 4 | blob tree verification (`verify_blobs.py --strict`) | blobs missing or malformed |
| 5 | **IR face unlock static acceptance** | camera id / aux list / OV9282 / ParanoidSense missing |
| 6 | resource check | < 100 GiB free |
| 7 | envsetup + lunch | product `aosp_equuleus` does not resolve |
| 8 | `mka bacon` | the compile fails |
| 9 | artifact verification | zip / `recovery.img` missing or stale |

Expect **2-4 failed builds** on the first attempt. That is normal for a new
device tree; the point is that each failure is caught by a gate that names the
problem rather than producing a subtly wrong zip.

## 5. Report the result honestly

Record, with the actual output:

| Item | Where |
| --- | --- |
| Build duration and exit code | `logs/build-<stamp>.log` |
| Which gate failed first, if any | the same log |
| ROM zip + `recovery.img` presence and size | `build.sh` artifact step |
| `MANIFEST_LOCK.xml` | the tree root |

**Do not report a build as successful unless `build.sh` exited 0 and the
artifact step passed.** A zip that exists but is stale, or a `mka` that returned
0 without producing a package, is a failure — `build.sh` treats both as such.

## 6. What stays NOT VERIFIED even after a successful build

A compiled ROM does not verify hardware behaviour. Unchanged by any build:

* **IR face unlock** — never observed; `camera_id=5` remains NOT VERIFIED ON DEVICE
* **IR illuminator control** — mechanism unknown (see `MIUI_IR_BLOB_INVENTORY.md` §2.4)
* FOD, camera, NFC, modem, Wi-Fi/BT, audio, charging, thermal

Those require the phone and the device test plans in `TEST_REPORT.md` §12 and
`IR_FACE_UNLOCK_DEPENDENCIES.md` §8.

## 7. Commands this project has actually run

For contrast with the above, here is what *has* been executed on the
development host, all of it static or extraction work:

| Executed | Result |
| --- | --- |
| Full official LineageOS OTA download + sha256 | verified |
| Block-OTA extraction, 5 partitions | 5/5 valid ext4 |
| `debugfs` dump | 8,268 files |
| Blob list resolution | 862/862 present |
| Vendor tree generation | 872 files / 546,824,712 bytes |
| `verify_blobs.py --strict` | FAIL=0 |
| MIUI firmware download, `gzip -t`, md5 vs Xiaomi manifest | match |
| MIUI vendor extraction | 2,070 files |
| MIUI vs LineageOS comparison | 12/18 byte-identical |
| Vendor archive + self-verification | 194 MiB, 872 files matched |
| Receive-side rehearsal | volume → manifest → blob gate all pass |
| Static suites | 46/46 acceptance, 58/58 mutations |

**Never executed:** `repo sync`, `envsetup`/`lunch`, `mka`, any flash, any
on-device test.
