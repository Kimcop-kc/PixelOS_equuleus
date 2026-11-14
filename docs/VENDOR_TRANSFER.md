# VENDOR_TRANSFER — getting the real blobs onto the cloud build machine

`B01_EXTRACTION_REPORT.json` describes the extraction. It is **not** the blobs.
A build machine given only that report has no proprietary binaries and cannot
link anything. This document is the transfer procedure for the actual files.

Measured facts (2026-11-12, this workspace):

| | |
| --- | --- |
| Files | **872** (equuleus 240, sdm845-common 632) |
| Uncompressed | **546,824,712 bytes** (521 MiB) |
| Empty files | **0** |
| Archive | `vendor-xiaomi-20261112.tar.xz` |
| Archive size | 194 MiB (xz, deterministic tar) |
| Archive SHA256 | `43d2e8536e5cbbe71da969293d9bf9be8d4144cf88274587ad27fb55e7851f01` |
| Volumes | 1 × 200 MiB (`part001`) |

---

## 1. Produce the archive

```bash
scripts/pack_vendor.sh --volume-mb 200
```

The script refuses to pack unless the tree looks like a real blob set:

* at least 800 files (a skeleton has a handful),
* at least 400 MB uncompressed,
* at most 5 empty files.

It then writes:

| File | Purpose |
| --- | --- |
| `MANIFEST.sha256` | SHA256 of every one of the 872 files, sorted, tree-relative |
| `vendor-xiaomi-<date>.tar.xz` | deterministic tar (sorted names, fixed mtime/owner) |
| `vendor-xiaomi-<date>.tar.xz.partNNN` | ≤200 MiB volumes for flaky links |
| `VOLUMES.sha256` | per-volume SHA256, so a bad volume is caught before reassembly |

Before finishing, the script **extracts its own archive into a temp directory and
re-verifies it against `MANIFEST.sha256`**. If that fails it refuses to hand you
"artifacts". A corrupt archive cannot leave this step silently.

## 2. Upload

Any method works; three that are safe and resumable:

```bash
# a) rsync over ssh — resumable, verifies per-block
rsync -avP out/vendor-archive/ user@host:/data/transfer/vendor-archive/

# b) scp the volumes individually
scp out/vendor-archive/*.part* user@host:/data/transfer/

# c) object storage + presigned download (no inbound ssh)
#    a tool of your choice; keep the SHA256 alongside the object
```

Each volume is at most 200 MiB, so a dropped connection costs one volume, not the
whole 194 MiB.

## 3. Receive and verify

```bash
cd /data/transfer
sha256sum -c VOLUMES.sha256            # 1. per-volume integrity
cat vendor-xiaomi-*.tar.xz.part* > v.tar.xz
sha256sum v.tar.xz                     # 2. must equal the archive hash above
tar -xJf v.tar.xz -C /data/pixelos15   # 3. extract into the synced tree
cd /data/pixelos15 && sha256sum -c /data/transfer/MANIFEST.sha256   # 4. per-file
```

Step 4 is the one that proves you have the same bytes. It must print no failures.

## 4. Re-run the real gate

The manifest proves the files arrived unchanged. It does **not** prove they are
the right files for the build. Only `verify_blobs.py` does that:

```bash
python3 scripts/verify_blobs.py /data/pixelos15 --strict --json blob-report.json
```

Expected result with the trees from this package:

```
OK=0  FAIL=0  RESIGNED=5  UNVERIFIABLE=0  SKIPPED=857
RESULT: every declared entry is present and every declared
        property was verified against the installed file.
```

`RESIGNED=5` is expected: five platform APKs are re-signed by LineageOS, so their
bytes differ from the hash pinned against the original firmware. They are
reported, not failed. This is a provenance difference, and it is also not proof
the APKs are correct.

### 4.1 What `SKIPPED=857` does and does not mean — read this before quoting it

Two different guarantees are involved, and conflating them overstates the
result:

| Guarantee | Provided by | Covers |
| --- | --- | --- |
| **Transport integrity** — the bytes that arrived are the bytes that were sent | `MANIFEST.sha256` (step 4) and `VOLUMES.sha256` (step 1) | **all 872 files**, individually hashed |
| **Declared-property verification** — the file is where the blob list says, has the architecture/SONAME the list declares, and matches any hash the list pins | `verify_blobs.py --strict` | only the properties each line actually declares |

`SKIPPED=857` means: **857 of the 862 declared entries pin no hash in
`proprietary-files.txt`, so their content was not authenticated against any
recorded digest.**

It does **not** mean "857 files failed", and equally it must **not** be read as
"857 files were content-verified". They were checked for:

* presence at the declared path,
* ELF class / machine / `DT_SONAME` where the line declares a fixup,
* hash, **only** for the 5 entries that pin one.

For those 857 entries, **whether the bytes are the original factory binaries is
not established by this tool at any point.** What *is* established about them is
narrower and should be stated in exactly these terms:

> All 872 shipped files arrived byte-identical to the manifest, and all 862
> declared entries are present with their declared structural properties
> satisfied. Five APKs are re-signed. For 857 entries no digest is pinned, so
> their content provenance is unverified.

The MIUI comparison (`MIUI_VS_LINEAGE_IR_DIFF.md`) independently establishes
byte-identity for the 12 IR-critical blobs against Xiaomi's own md5-verified
firmware — that is a content-provenance result, but only for those 12 paths, and
it is a separate piece of evidence from anything `verify_blobs.py` reports.

## 4.2 `BUILD READY` is printed only when all three checks pass

`cloud_vendor_transfer.sh receive` prints `BUILD READY` **only** after:

1. every volume matches `VOLUMES.sha256`,
2. every extracted file matches `MANIFEST.sha256`,
3. `verify_blobs.py --strict` exits 0 **and** the JSON report shows `FAIL=0`.

If the verifier cannot run — missing from the project, device trees absent, or
any non-zero exit — the script **exits non-zero and does not print
`BUILD READY`**. There is no SKIP path. This was a real defect: an earlier
revision printed SKIP and success when the target tree lacked
`scripts/verify_blobs.py`, so a tree with no verification at all reported ready.

## 5. What is deliberately NOT sent

| Excluded | Why |
| --- | --- |
| The 5 extracted partition images (4.7 GB) | only needed to regenerate the trees; the trees are the deliverable |
| `out/vendor-archive/*.tar.xz` un-split copy | duplicate of the volumes; removing it halves the transfer |
| Any `.git` data | the vendor trees are not git repositories by design |

## 6. If the archive is rejected

| Symptom | Meaning |
| --- | --- |
| `pack_vendor.sh` refuses at preconditions | the tree is a skeleton, not blobs — re-run the B-01 extraction |
| `sha256sum -c VOLUMES.sha256` fails | that volume was corrupted in transfer; re-upload only it |
| `sha256sum -c MANIFEST.sha256` fails after extraction | extraction was truncated or the archive was altered — start again from the volume check |
| `verify_blobs.py` reports `FAIL>0` | files are present but wrong (missing, bad SONAME, hash mismatch) — read the report; do not build |
| `verify_blobs.py` reports `UNVERIFIABLE>0` | a declared property could not be confirmed; treat as not verified |

## 7. The honest position

The archive in this package was produced from a real extraction and passed the
self-verification described above. What has **not** happened:

* the trees were generated by this project's own block-OTA extractor, **not** by
  upstream `extract-files.py`, because that requires a fully synced PixelOS tree
  for Soong name resolution. The output is verified against the same blob lists,
  but the code path differs and should be cross-checked on a real tree.
* no ROM has been compiled from these trees.
* nothing has been flashed, and IR face unlock, FOD, camera and NFC remain
  unverified on hardware.
