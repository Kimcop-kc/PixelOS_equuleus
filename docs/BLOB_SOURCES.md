# LineageOS 22.2 OTA — verified source record

Machine-readable companion: `blob_sources.json`. This file explains what was
**actually verified** versus what still requires the download to run.

Records current: **2026-11-12**.

---

## 1. Why this route exists

`BLOB_EXTRACTION.md` originally described reconstructing the blob set from
**five** historical firmware images (beryllium / PNX / lemonadep / caymanslm /
equuleus). That is expensive and fragile.

The LineageOS wiki documents a simpler path
([extracting blobs from zips](https://lineageos.github.io/lineage_wiki/extracting_blobs_from_zips.html),
fetched and read 2026-11-12):

> Move to the directory of your device:
> `cd ~/android/lineage/device/vendor_name/device_name/`
> If the device directory contains `extract-files.py`, run it with:
> `./extract-files.py path/to/lineage-*.zip`

So `extract-files.py` accepts a **LineageOS installation ZIP** directly. If an
official equuleus build exists, one OTA can supply both trees — because that
build was itself produced from the very device trees this project pins.

## 2. Device and build availability — verified

`GET https://download.lineageos.org/api/v2/devices/equuleus` → **HTTP 200**:

```json
{"dependencies":["android_device_xiaomi_equuleus",
                 "android_device_xiaomi_sdm845-common",
                 "android_hardware_xiaomi",
                 "android_kernel_xiaomi_sdm845"],
 "model":"equuleus","name":"Mi 8 Pro","oem":"Xiaomi","versions":["22.2"]}
```

The dependency list is **exactly** the four repositories this project pins in
`.repo/local_manifests/equuleus.xml`. That is the strongest available evidence
that an official OTA is the right blob source for our trees.

`GET .../devices/equuleus/builds` → **HTTP 200**, three most recent builds:

| Date | Version | File | Size | SHA256 |
| --- | --- | --- | --- | --- |
| 2026-11-10 | 22.2 | `lineage-22.2-20261110-nightly-equuleus-signed.zip` | 1,223,204,572 | `2ebd3d4bb7168135353c8b543bb79da4e53a1efccf32fd91c498e9fa9fe365ee` |
| 2026-11-03 | 22.2 | `lineage-22.2-20261103-nightly-equuleus-signed.zip` | 1,223,240,764 | `36df2643b7253df00419fc2b553bd2756f7b5cee95ea31b55ef70a277efa0d8a` |
| 2026-10-27 | 22.2 | `lineage-22.2-20261027-nightly-equuleus-signed.zip` | 1,223,203,279 | `7ed6cfefc572b41e32adda3c5698ec6769657d5cdf4b9aa0c3a60d69166a54d3` |

**Chosen pin: the 2026-11-10 build** (newest at time of audit).

* SHA1 `acea844fc41bc06a0cc59e5550dee698b9f54d14`
* OS patch level `2026-10-01`, SDK level 35 (Android 15) — matches `fifteen`
* URL: `https://mirrorbits.lineageos.org/full/equuleus/20261110/lineage-22.2-20261110-nightly-equuleus-signed.zip`

### 2.1 Download reachability — verified

```
HTTP/1.1 302 Found
Location: https://mirrors.ustc.edu.cn/lineageos/full/equuleus/20261110/lineage-22.2-20261110-nightly-equuleus-signed.zip
HTTP/1.1 200 OK
Content-Length: 1223204572
Accept-Ranges: bytes
```

Range requests are supported, which is what the preflight script uses to inspect
the OTA header without downloading 1.2 GB.

## 3. OTA format — verified by reading it

The first 1 MiB was fetched with a range request (`HTTP 206`, 1,048,576 bytes)
and parsed:

| Property | Observed |
| --- | --- |
| Magic | `PK\x03\x04` — a standard ZIP |
| `META-INF/com/android/metadata` | present at offset 30, i.e. the first stored entry |
| `ota-type` | `BLOCK` |
| `pre-device` | **`equuleus`** |
| `post-build` | `Xiaomi/equuleus/equuleus:8.1.0/OPM1.171019.026/V9.6.6.0.OECCNFD:user/release-keys` |
| `post-sdk-level` | `35` (Android 15) |
| `post-security-patch-level` | `2026-10-01` |
| `post-build-incremental` | `4ce3f00d23` |
| `ota-required-cache` | `0` |

Full `META-INF/com/android/metadata` as read from the range request:

```
ota-property-files=metadata:69:336,metadata.pb:473:219
ota-required-cache=0
ota-type=BLOCK
post-build=Xiaomi/equuleus/equuleus:8.1.0/OPM1.171019.026/V9.6.6.0.OECCNFD:user/release-keys
post-build-incremental=4ce3f00d23
post-sdk-level=35
post-security-patch-level=2026-10-01
post-timestamp=1794296705
pre-device=equuleus
```

`ota-type=BLOCK` matters: the payload is a block-based `payload.bin`, not
per-file `system.new.dat` images. `extract-utils` handles this through its
`extract_super_retrofit` / `lp.py` / `sparse_img.py` modules, but the extraction
needs the **whole** file (the payload is in the middle), so a full download is
mandatory.

## 4. What this record does NOT claim

* **The OTA has not been fully downloaded here.** Only the first 1 MiB was
  fetched to prove format and device assertion. `vendor/xiaomi/equuleus` and
  `vendor/xiaomi/sdm845-common` are **not generated**.
* `extract-files.py` has **not** been run against it — that needs a synced
  PixelOS tree (the extractors import Soong modules to resolve names).
* No claim is made that one OTA covers all 862 declared blob lines. Section 6 of
  this document explains why some lines may still need another source, and how
  the script reports them instead of inventing files.

## 5. How to complete it on a machine with the tree

```bash
# 1. verify the download against the pinned hash
scripts/fetch_lineage_ota.sh --dest /data/ota

# 2. generate both vendor trees (order matters: sdm845-common first)
scripts/extract_blobs_from_ota.sh /data/pixelos15 /data/ota/lineage-22.2-20261110-nightly-equuleus-signed.zip

# 3. strict verification with a machine-readable report
python3 scripts/verify_blobs.py /data/pixelos15 --strict --json /data/pixelos15/blob-report.json
```

Step 2 prints an explicit **MISSING / NEEDS-OTHER-SOURCE** list for anything the
OTA does not supply. Those entries are reported, never fabricated.

## 6. Expected gaps, stated in advance

The device tree's `proprietary-files.txt` files were written against a
*superset* assembled over years. An official OTA supplies what the ROM ships.
Known classes of possible shortfall:

| Class | Why | Handling |
| --- | --- | --- |
| `system_ext/...` entries | LineageOS moves some blobs to `system_ext`; a `-signed.zip` may store them under a different path than the list expects | reported as MISSING with the expected path |
| Recovery-only blobs | present in `recovery.img`, not in the OTA payload | second source (`recovery.img`) documented per row |
| Files removed upstream | the tree may still list a blob LineageOS dropped | reported; the list needs trimming, not a substitute file |
| `;FIX_SONAME` targets | extraction renames them, so the *source* name legitimately does not exist | handled by `verify_blobs.py`, which checks `<dst>` |

Any of these is a **finding**, not a failure of the method. The script's job is
to produce an exact, auditable list.
