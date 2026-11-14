# TEST_REPORT — what was actually executed

Report date: **2026-11-12** (round 3). Host: Windows 11, 16 logical CPUs,
13 GiB RAM, 200 GiB NTFS volume with ~48 GiB free, bash 5.3 (Git for Windows),
Python 3.12.4. No Linux build host. No phone connected. No ECS instance used.

> **Headline, stated plainly: no ROM was compiled. 未编译。**
> No `repo sync` completed, no `mka bacon` ran, no image was flashed, nothing was
> tested on a device. Bucket 1 is **static**: file contents, manifest parsing,
> real `git clone` HEAD comparison, patch application, script syntax, and
> behavioural probes of the blob parser. Compiling is not booting; booting is
> not working hardware.

Three buckets, as requested.

---

## 1. 已执行且通过 — executed and passed

### 1.1 Acceptance suite

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 1 | All 24 static deliverable checks | `python scripts/verify_deliverables.py` | **24/24 PASS**, exit 0 |
| 2 | Suite can actually fail (mutation test) | `python scripts/verify_mutations.py` | **28/28 seeded defects caught**, exit 0 |

### 1.2 P0-1 — GMS dependency (this round)

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 3 | `common.mk` inherits GMS **unconditionally** | `sed -n '1,12p' vendor/aosp/config/common.mk` | line 5 does `$(call inherit-product, vendor/gms/products/gms.mk)` — no `-if-exists` form |
| 4 | The chain reaches it from our product | read `common_full_phone.mk` → `common_mobile_full.mk` → `common_mobile.mk` → `common.mk` | each step is a plain `inherit-product`. **An earlier claim in this project that the `aosp_` product was GMS-independent was wrong; corrected in B-14.1** |
| 5 | `vendor_gms` has **no** `fifteen` branch | `git ls-remote --heads https://gitlab.com/PixelOS-AOSP/vendor_gms` | only `refs/heads/sixteen` = `68298e26…` |
| 6 | `vendor_gms-15` **does** have `fifteen` | `git ls-remote --heads https://gitlab.com/PixelOS-AOSP/vendor_gms-15` | `fifteen` = `ffe5c52d947eec784a07124dfb72e95840e8f3c7` (also `sixteen`) |
| 7 | That SHA is a real commit with history | `git clone --filter=blob:none --branch fifteen` | `HEAD` = `ffe5c52d…`, subject `gms: rro-utils: Move removal of empty xmls to beautify_rro` |
| 8 | The repo contains the file `common.mk` actually inherits | `git cat-file -e HEAD:products/gms.mk` | present; content is real GMS product config (`GoogleSettingsOverlay`, `ro.opa.eligible_device`, IME props) |
| 9 | Manifest patch applies to pristine upstream | `git apply --check` on a fresh clone of `PixelOS-AOSP/manifest@0334d5e4` | clean; rewrites only the `vendor/gms` line in `snippets/custom.xml` |
| 10 | Local manifest performs the same repoint | XML parse + the suite's "P0-1" check | `<remove-project name="vendor_gms">` plus `<project name="vendor_gms-15" revision="ffe5c52d…">` |

### 1.3 P0-2 — blob verification (this round)

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 11 | `extract-utils` grammar replicated from upstream source | read `extract_utils/file.py` | separators are `;` `:` and the pipe; `:` sets dst, `;` sets args, the pipe carries hash then fixup-hash, a leading `-` marks a package |
| 12 | Installed path uses `dst`, not `src` | read `extract_utils/module.py` | `vendor/<vendor>/<device>/proprietary/<File.dst>` |
| 13 | `FIX_SONAME` is applied **after** copy | read `module.py:748,766` | `blob_fixup().fix_soname().run(ctx, file, file_path)` on the installed path |
| 14 | Parser handles dst/args/hashes/package | behavioural probe inside the suite | 5 assertions, including a line with dst + `;FIX_SONAME` + two pipe hashes |
| 15 | ELF `DT_SONAME`/`DT_NEEDED` reader is correct | hand-built minimal ELF64 (no gcc on host) | returns the expected SONAME and NEEDED lists; returns `None` for text and missing files |
| 16 | A remapped blob is verified at its **dst** | synthetic tree probe | source name absent, dst present → correctly reported present; a genuinely missing blob → reported missing with its expected dst path |
| 17 | Firmware matrix is complete and counted | line-classification of both `proprietary-files.txt` | equuleus **235** lines / 1 source; sdm845-common **627** lines / **5** sources (beryllium 121, PNX 219, lemonadep 94, caymanslm 193) |

### 1.4 P0-3 — two-stage preflight (this round)

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 18 | Stage 1 runs with **no** sources or blobs present | `bash scripts/host-preflight.sh` | exit 1 on this host with 10 environment failures; it never mentions the blob tree or `proprietary-files.txt` (grep-verified — the only match is the sentence stating it does not check them) |
| 19 | Stage 1 checks the right things | same | x86_64, distro, 14 tools, JDK≥17, `repo`, ccache, nproc, RAM+swap, `df` free/total, filesystem type, 4 network probes, proxy vars, TLS handshake |
| 20 | Stage 2 requires sources **and** blobs | `bash scripts/build-preflight.sh <tree>` | requires `build/envsetup.sh`, `.repo`, 7 pinned project HEADs, 4 applied patches, `aosp_equuleus`, both `vendor/xiaomi/*` trees with `BoardConfigVendor.mk` / `*-vendor.mk` / `Android.bp`, and 100 GiB for `out/` |
| 21 | Patch state verified by **reverse** application | `git apply --reverse --check` | robust to later edits on top of a patch, unlike repeating the forward check |
| 22 | `build.sh` refuses to build on a failed gate | read + `bash -n` | runs stage 2 and `verify_blobs.py`; dies on non-zero |
| 23 | Old `preflight.sh` no longer duplicates logic | read | dispatches to stage 1 (no argument) or stage 2 (with a tree) |

### 1.5 P0-4 — revision lock (this round)

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 24 | `sync.sh` **executes** `repo manifest -r` | suite strips comment lines, then requires a real invocation | PASS — comment-only occurrences no longer satisfy the check (a real weakness found by mutation testing) |
| 25 | Lock artefacts persisted | read `sync.sh` | `MANIFEST_LOCK.xml` (stable copy), `MANIFEST_LOCK.tsv` (path/name/revision per project), plus a timestamped copy under `.repo/manifests-locks/` |
| 26 | A failed capture is not silent | read `sync.sh` | prints an explicit "NOT reproducible" warning with the manual re-run command |
| 27 | Unpinned projects are detected | read `sync.sh` | compares project count against 40-char-SHA count and warns if they differ |

### 1.6 Patch integrity and real clones

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 28 | All 8 patch files apply to real clones; 7 of them are part of a normal build (0005 is archived) | `git apply --check` then `git apply` on fresh copies of the three cloned repos | 8/8 clean; resulting `git status` shows exactly the intended edits. `sync.sh` applies 0001-0004 and 0006-0008. |
| 29 | Patches carry mail headers | suite | 5/5 carry a `From <sha>` line, `From:`, `Date:`, `Subject: [PATCH]`, `---` |
| 30 | Patches apply **in sequence** | fresh trees, 0001→0002 and 0003→0004 | clean, no fuzz |
| 31 | 9 pinned SHAs are real commit objects | `git cat-file -e <sha>^{commit}` in each real clone | 9/9 exit 0 |
| 32 | Clone HEADs equal the pins | `git rev-parse HEAD` | 9/9 character-for-character |
| 33 | Clones carry real history | `git rev-list --count HEAD` | 110–4,556 commits |

### 1.7 Manifest and environment

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 34 | Local manifest well-formed, 5 projects SHA-pinned | XML parse + suite | 5 pinned projects, 5 unique paths |
| 35 | No path collision with upstream | suite (parses `default.xml` plus 3 snippets, applies 127 upstream and 1 local removal) | 0 overlaps against 1,094 upstream paths |
| 36 | Remote attributes match upstream exactly | suite replicates `_XmlRemote.__eq__` | 3 remotes (`PixelOS`, `LineageOS`, `PixelOS-Gitlab`) compatible; no `already exists with different attributes` |
| 37 | `<extend-project>` resolves | suite | 1 entry resolves against the merged manifest |
| 38 | `<remove-project>` then re-add is accepted, not flagged as a clash | suite | the `vendor/gms` idiom passes the collision check |
| 39 | No forbidden destructive commands | suite | no `--force-sync`, nothing piped into a shell, no SELinux-disabling command |
| 40 | No credential-shaped strings | suite | 0 hits (mutation seeds are assembled at runtime so the suite does not match its own test data) |
| 41 | Scripts syntactically valid | `bash -n` on all 5 | clean |
| 42 | Scripts fail-fast | suite | all use `set -e`; the dispatcher is exempted from its *own* logging because the stage it execs logs |
| 43 | Kernel tree complete | 174,356,433-byte tarball of `aa8adfe9…` | `Makefile` 4.9.337; all 7 sdm845 defconfigs present |
| 44 | Kernel fragment is load-bearing | grep both configs | Goodix-TA, FTS-touch and MACH_XIAOMI_E1S options are absent from the base defconfig and present only in `equuleus.config` (closed B-04) |
| 45 | Lineage manifest snapshot untampered | fresh codeload fetch vs snapshot | `default.xml` and `snippets/lineage.xml` byte-identical |

---

## 2. 已执行但失败 — executed and failed

| # | Check | Command | Observed | Meaning |
| --- | --- | --- | --- | --- |
| 1 | `host-preflight.sh` overall | `bash scripts/host-preflight.sh` | exit 1, 10 FAIL | **Correct behaviour.** This host cannot build: 13 GiB RAM, NTFS, 48 GiB free, and all three source hosts unreachable. |
| 2 | AOSP reachability | `curl https://android.googlesource.com/` | `curl: (28)` timeout after 20 s | `repo sync` is impossible from this network regardless of disk. |
| 3 | GitHub / GitLab reachability | `curl` both | timeout / connection reset | `repo sync` impossible; also why two clones failed (items 4–5). |
| 4 | `git clone LineageOS/android` | `git clone --depth 1`, 8 attempts | `Failed to connect to github.com:443` repeatedly | Manifest verified instead via codeload (HTTP 200) and byte-identical content against the snapshot. |
| 5 | `git clone` kernel, 3 attempts | `git clone` | connection failures | Verified by a 174 MB tarball download at the pinned SHA, which succeeded. |
| 6 | `git clone vendor_gms-15` (full) | `git clone --branch fifteen` | aborted after ~4.2 GB (large APK payload) | Succeeded with a `--filter=blob:none` metadata clone; `products/gms.mk` was then read with `git cat-file`, so content was still verified. |
| 7 | Kernel tarball attempts 1–3 | codeload | truncated at 7.8–10 MB | **Resolved on attempt 4** (174 MB, `gzip -t` clean). Kept here because the retry is what fixed it. |
| 8 | GitLab raw-file fetch | `curl .../raw/<sha>/products/gms.mk` | HTTP 403 (Cloudflare challenge) | Worked around with a git metadata clone; no data lost. |
| 9 | GitHub API during the audit | `api.github.com` | `403`, `remaining: 0` | Switched to `raw.githubusercontent.com` and `git ls-remote`. |
| 10 | gcc-built ELF for the SONAME reader test | `gcc -shared` | exit 127, no compiler on host | Built a minimal ELF64 by hand in Python instead — a stricter test because every byte is known. |
| 11 | `du`/`find` over the extracted kernel tree | `du -sh` | exceeded 2 minutes on NTFS | Killed; the audit data it was collecting had already been gathered. |
| 12 | Mutation seed for **P0-4**, first attempt | `verify_mutations.py` | the seed left `repo manifest -r` in comments, so the check still passed | **Exposed a real weakness**: the check matched comments. Fixed in the checker to require an executed command; the seed then correctly failed it. |
| 13 | Mutation seed for **P0-2**, first attempt | `verify_mutations.py` | the token-only check still passed after the separator constant changed | **Also a real weakness**: the check asserted string presence, not behaviour. Replaced with a five-assertion behavioural probe. |
| 14 | Several other mutation seeds | `verify_mutations.py` | seed failures / missed expectations | Seeds were wrong (one edited an *added* patch line, which `git apply` still accepts; others used anchors that did not exist). Fixed in the test, not by loosening the checks. |

---

## 3. 没有执行 — not executed

| # | Item | Why | What would be required |
| --- | --- | --- | --- |
| 1 | `repo init` against PixelOS fifteen | No Linux host, no case-sensitive FS, `android.googlesource.com` unreachable | Linux x86_64, ext4/xfs, ≥400 GiB |
| 2 | `repo sync` (any project) | Same | Same plus working network |
| 3 | **`repo manifest -r` on a real project tree** | Requires a completed sync | Run `sync.sh` on a real host; the code path is written and syntax-checked but has never executed against repo |
| 4 | Soong/make parse (`m nothing`) | Requires a full tree | First step of a real build |
| 5 | `lunch aosp_equuleus-bp1a-userdebug` | Same | Same |
| 6 | **`mka bacon` — the ROM build** | Same. **未编译：本次没有编译任何 ROM。** | 16 vCPU / 64 GiB / 600 GiB SSD, ~3–6 h |
| 7 | Kernel compilation | Same | Same |
| 8 | Running `extract-files.py` | Needs a full tree plus five firmware images | B-01 |
| 9 | Blob verification against a **real** blob tree | No blobs exist | After extraction, run `verify_blobs.py` |
| 10 | Flashing anything | Forbidden by the task; no phone | Unlocked bootloader |
| 11 | Boot test | No image | Built image plus device |
| 12 | FOD enrol/unlock | No image, no device | Device |
| 13 | Camera preview/photo/video/portrait | No image, no device | Device |
| 14 | NFC read / HCE / eSE / transit | No image, no device, no cards | Device plus cards |
| 15 | Wi-Fi, BT, audio, modem/VoLTE, GPS | No image, no device | Device |
| 16 | Charging, thermal, battery | No image, no device | Device plus hours |
| 17 | Widevine/DRM level, Play Integrity | No image, no device | Device plus account |
| 18 | Recovery boot, sideload, OTA | No image, no device | Device |
| 19 | `fastboot getvar` (TrustZone string) | No device | Device |
| 20 | GMS actually configuring (`m nothing` with vendor/gms) | Requires a synced tree | `repo sync` after patch 0005 |
| 21 | Both preflight stages on a compliant host | No compliant host exists here | Linux, 16 vCPU, 64 GiB, 600 GiB |
| 22 | `shellcheck` | Not installed | `apt-get install shellcheck` |
| 23 | Full kernel line-by-line review | Tree obtained, but no patch touches the kernel | Only if a kernel change is proposed |

---

## 4. Red → green timeline

| Stage | Passed | What was failing |
| --- | --- | --- |
| Baseline (no deliverables) | 2/18 | docs, scripts, patches, naming, BoardConfig, dangling paths, FOD/NFC, blockers, lock, report |
| Local manifest written | 3/18 | plus per-project SHA pinning |
| De-collided with platform | 4/18 | remote-conflict and path-collision — found the `<remote>` duplication hazard |
| XML comment fix (double hyphen is illegal in XML comments) | 6/18 | one parser error had been masked as three failures |
| Patches exported | 10/18 | apply plus mail headers, naming, BoardConfig, dangling paths |
| Docs written | 18/18 | — |
| `extend-project` validity check | 19/19 | a well-formed-but-wrong name/path would have passed |
| Real-clone verification | 20/20 | raised P0 evidence from "a tarball existed" to "this SHA is a commit object with history" |
| **Round 3: P0-1..P0-4 checks** | **24/24** | GMS resolution, dst-aware blob parsing, two-stage preflight, executed `repo manifest -r` |
| Mutation suite | **28/28 caught** | two checker weaknesses found and fixed (see §2 items 12–13) |

### 4.1 The final run is on record

| Artifact | Value |
| --- | --- |
| Command | `python scripts/verify_deliverables.py` |
| Result | **24 checks, 24 PASS, 0 FAIL, exit code 0** |
| Mutation suite | `python scripts/verify_mutations.py` → **28/28 caught**, exit 0 |
| Logs | `logs/verify-20261111T201528Z.log`, `logs/mutations-20261111T201528Z.log` |
| Hashes | `logs/final-state.sha256` |

A green suite alone is weak evidence — a suite that cannot fail is also green.
That is why the 28-defect mutation suite exists, and why the two weaknesses above
were found only by it.

### 4.2 The package was verified *from the ZIP*, not from the working tree

The strongest available check for a deliverable is: hand someone the archive,
and see whether they can reproduce the verdict. That was done.

| Step | Command | Result |
| --- | --- | --- |
| Extract to a clean directory | `python scripts/extract_package.py out/equuleus-pixelos15-port-20261111.zip /tmp/zt` | **4,684 files, no extraction failures** |
| Git recognises the shipped clones | `git -C clones/device-xiaomi-equuleus rev-parse HEAD` | `db40750f…` (a real repository, not a copied directory) |
| Acceptance suite, extracted copy | `python scripts/verify_deliverables.py` | **24/24 PASS**, exit 0 |
| Mutation suite, extracted copy | `python scripts/verify_mutations.py` | **28/28 caught**, exit 0 |

Three packaging defects were found **only** by doing this, and each would have
silently produced a useless archive:

1. **`.git` was excluded** from the archive, so every clone arrived without its
   object database and `git cat-file` could not verify a single pin.
2. **`vendor-gms-15` had no working tree** (it is a `--filter=blob:none` clone),
   so its directory shipped effectively empty.
3. **Empty directories are not representable in ZIP.** `git` refuses to open a
   repository whose `.git/refs` directory is missing — even when every ref lives
   in `packed-refs`. 18 explicit directory entries are now written, and
   `git -C <clone> rev-parse HEAD` succeeds after extraction.

A fourth issue is environmental rather than logical: several AIDL snapshot paths
exceed Windows' 260-character `MAX_PATH`, so both the packer and the unpacker now
route every filesystem call through the `\?\` long-path prefix. Before that
fix, 18 files were silently dropped from `src/`; `make_package.py` now exits
non-zero if any walk error occurs, so this class of loss cannot pass unnoticed.

---

---

## 6. Independent review round (2026-11-12) — 8 findings, all fixed and regression-tested

An external reviewer audited the previous review-sized archive and reported
6 defects plus 2 process gaps. **Every finding was reproduced independently
before being accepted**; none was taken on trust. Each fix now has a check that
fails if the defect is reintroduced, and a mutation seed proving that check
actually bites.

| ID | Finding | Reproduced how | Fix | Regression guard |
| --- | --- | --- | --- | --- |
| **P0-1** | `sync.sh` uses `${PYTHON}` under `set -euo pipefail` but never assigns it → aborts before `repo sync` | `bash -c 'set -euo pipefail; echo "${PYTHON}"'` → `PYTHON: unbound variable` | resolve `python3`/`python`, requiring it to actually execute (a bare `command -v` is not enough: this host's `python3` is a dead store shim) | check `sync.sh defines PYTHON before use (P0-1)` compares the first-assignment line number against the first-use line number; mutation erases every assignment → **CAUGHT** |
| **P0-2** | local manifest `<remove-project name="vendor_gms">` **and** `sync.sh` applying `patches/0005` are two mutually-exclusive overrides; together git-repo aborts | **real git-repo parser** (`manifest_xml.py`): `ManifestParseError: remove-project element specifies non-existent project: <remove-project name="vendor_gms"/>` | adopted the review's option 1: local manifest stays, `sync.sh` no longer applies 0005, and now *refuses* if 0005 is already present | check `GMS overrides are mutually exclusive (P0-2)`; mutation re-adds the `apply_patch ... 0005` line → **CAUGHT** |
| **P1-1** | retry loop reads `$?` after `fi`, where it is always 0 | `bash -c 'if false; then :; fi; echo $?'` → `0`; with `else rc=$?` → `1` | moved `rc=$?` inside the `else` branch | check parses the loop and requires `rc=$?` after `else`; mutation moves it back outside → **CAUGHT** |
| **P1-2** | ZIP stores `create_system=0`, mode `0o666`; on Linux scripts are not executable, and `build.sh` gated the preflight on `-x`, silently skipping it | `zipfile.ZipInfo.external_attr >> 16` on every `.sh` → `0o666` | packer writes `create_system=3` + `external_attr=0o100755<<16`; `build.sh` uses `[[ -f ]]` + `bash script` instead of `-x` | check `build gates are not skippable`; mutation restores `[[ -x ]]` → **CAUGHT** |
| **P1-3** | `REPRODUCE.md` referenced `scripts/extract_audit_package.py`, which was not in the ZIP; and a meaningless `cp file file` | `grep` the archive listing | extractor added to the shipped set; docs now say `python -m zipfile -e ...` + `chmod +x`; self-copy removed | file-presence check + docs regenerated by the packer |
| **P1-4** | `build.sh` degraded a missing `verify_blobs.py` to a WARNING, though blobs are the top blocker | read the else-branch | now `die 1 "…refusing to build unverified blobs"` | check forbids the skip path; mutation restores the warning → **CAUGHT** |
| **P1-5** | manifest drift only printed a NOTE; `repo manifest -r` failure only warned | read the code | both are now fatal (`die`), so an unreviewed manifest cannot ship | present in the same checks; the lock step is asserted by `manifest lock workflow present (P0-4)` |
| **process** | author claimed validation but only via re-implemented rules | — | added `scripts/verify_manifest_parse.py`, which imports the **genuine** `manifest_xml.py` from a git-repo checkout | see §6.1 |

### 6.1 Verification with the real git-repo parser (not an emulation)

All earlier manifest claims in this project came from *re-implementing*
`manifest_xml.py` rules after reading them. That is reasoning, not evidence.
`scripts/verify_manifest_parse.py` now imports the real module and drives
`XmlManifest` directly.

```
$ python scripts/verify_manifest_parse.py \
      --repo-src <git-repo checkout> --manifests clones/pixelos-manifest

CASE 1  shipped configuration (local manifest only, no 0005)
  [PASS] parsed by git-repo: 1099 projects
         vendor/gms -> vendor_gms-15 @ ffe5c52d947eec784a07124dfb72e95840e8f3c7
  [PASS] no duplicate project paths
  [PASS] GMS repoint is in effect

CASE 2  REGRESSION: local manifest AND patch 0005 both applied
  [PASS] real git-repo rejected it as predicted:
         ManifestParseError: remove-project element specifies non-existent
         project: <remove-project name="vendor_gms"/>
```

Two things made this trustworthy rather than decorative:

* **The cases run in separate processes.** Parsing case 1 first made case 2
  return *no* error in the same interpreter, because `manifest_xml` carries
  state across `XmlManifest` instances. Isolating the cases changed a false
  "the review is wrong" into the correct rejection. Had I not isolated them, I
  would have reported the opposite conclusion.
* **`local_manifests` must be passed explicitly.** `XmlManifest` only merges it
  when the attribute is truthy (`if self._load_local_manifests and
  self.local_manifests:`). Before I did that, the parse reported
  `vendor/gms -> vendor_gms @ refs/heads/fifteen` — i.e. it silently ignored
  our override and would have "confirmed" the wrong thing.

`fetch_clones.sh` / `REPRODUCE.md` explain how to obtain the git-repo checkout
and manifest clone this test needs. Without them the script exits 2 (clearly,
rather than passing vacuously).

### 6.2 Round-5 totals

| Suite | Result |
| --- | --- |
| `verify_deliverables.py` | **28/28 runnable checks** (was 24; +4 regression checks) |
| `verify_mutations.py` | **34/34 judged mutations caught** (was 28; +6 seeds, one per new guard) |
| `verify_manifest_parse.py` | CASE 1 pass, CASE 2 reject — both with the real parser |
| `bash -n` on all shell scripts | clean |

### 6.3 Still not executed (unchanged, and must stay stated)

`repo sync`, `repo manifest -r` on a real project tree, `lunch`, Soong/Make,
the kernel build, flashing, and every hardware test. **No ROM was compiled.
未编译。** The two-stage preflight and the blob verifier have still never run
against a real synced tree with real blobs.

---

---

## 7. Review round 6 — blob verification was passing on failure (2026-11-12)

The reviewer found that `verify_blobs.py` reported a `DT_SONAME` mismatch and
still exited 0. **That was true, and it was the most serious defect in the
project to date**: it is precisely the class of bug that lets a broken blob
tree reach a build while the tooling says "verified".

### 7.1 Root cause

Two independent holes:

| Hole | Detail |
| --- | --- |
| exit status ignored its own findings | `soname_suspect` was *collected* into the report but never folded into `report["ok"]`, so only `missing` could fail the run |
| hashes were counted, not checked | `info["hashed"] += 1` incremented a counter; no digest was ever computed against the installed file |

### 7.2 What the verifier does now

| Aspect | Behaviour |
| --- | --- |
| SONAME mismatch | **FAIL → exit 1** (was exit 0) |
| ELF unreadable / no `.dynamic` | **FAIL → exit 1**, explicitly reported ("cannot confirm DT_SONAME") |
| non-ELF carrying `FIX_SONAME` | **FAIL → exit 1** |
| pre-fixup `hash` vs post-fixup `fixup_hash` | distinguished, per upstream semantics (below) |
| properties that cannot be confirmed | **UNVERIFIABLE → exit 3**, never 0 |
| `--strict` | turns UNVERIFIABLE into exit 1; `build.sh` always uses it |

**Upstream semantics were read from source, not guessed.** In
`extract_utils/module.py::process_pinned_file`:

* `hash` is checked against `file_path_sha1()` **before** fixups;
* `fixup_hash` is checked **after** fixups;
* declaring a `fixup_hash` with **no** fixup function returns `BAD_FIXUP`;
* declaring only a pre-fixup `hash` while a fixup runs means the post-fixup
  digest is unknown — upstream prints it in red and expects it to be added.

Because `verify_blobs.py` inspects the *installed* (post-fixup) artefact, it can
check `fixup_hash` directly but **cannot** re-derive a pre-fixup `hash`. It now
says so (UNVERIFIABLE) instead of quietly passing.

### 7.3 Fault-injection tests — the actual proof

`scripts/test_verify_blobs.py` drives the real script as a subprocess and
asserts on **exit codes**, not on output text that happens to contain a word.

```
$ python scripts/test_verify_blobs.py
  [PASS] missing file                     rc=1
  [PASS] wrong SONAME                     rc=1   <- was rc=0 before this round
  [PASS] wrong hash                       rc=1
  [PASS] correct file                     rc=0
  [PASS] fixup hash without fixup         rc=1   (upstream BAD_FIXUP)
  [PASS] pre-fixup hash only + fixup      rc=3   (UNVERIFIABLE, not success)
  [PASS] post-fixup hash matches          rc=0
  [PASS] non-ELF with FIX_SONAME          rc=1
  [PASS] ELF without .dynamic             rc=1
all 9 cases behaved as required
```

The four cases the review required (missing / wrong SONAME / wrong hash /
correct) are the first four; five more cover the hash-semantics branches.

**A remembered reproduction of the original bug.** Building the exact fixture
the reviewer described (installed file whose `DT_SONAME` still names the source)
against the current verifier:

```
1 SONAME FAILURE(S):
  DT_SONAME 'fingerprint.goodix_fod.so' != installed basename 'fingerprint.goodix_fod.sdm845.so'
  the FIX_SONAME rewrite did not happen, or a wrong file was installed
RESULT: FAILED - do not build.     (exit 1)
```

### 7.4 `build.sh` now refuses to compile

`build.sh` invokes the verifier with `--strict` and maps exit codes to hard
failures (1 = defect, 3 = unverifiable, 2 = cannot run). The status is captured
**inside** an `if`/`else`, because under `set -e` a bare call terminates before
`$?` can be read — the same trap class as the P1-1 retry bug.

### 7.5 Round-6 totals (all actually executed)

| Suite | Command | Result | Exit |
| --- | --- | --- | --- |
| static acceptance | `python scripts/verify_deliverables.py` | **34/34** runnable checks | 0 |
| mutation suite | `python scripts/verify_mutations.py` | **41/41** judged mutations caught | 0 |
| blob fault injection | `python scripts/test_verify_blobs.py` | **9/9** cases behaved as required | 0 |
| network-only preflight | `bash scripts/host-preflight.sh --network-only` | **NETWORK NOT READY**, 5 failures | 1 |

The network-only failure is a genuine property of the audit host, not a bug:
`android.googlesource.com` is unreachable here, so `repo sync` cannot work from
this machine. That is exactly the question the mode exists to answer.

### 7.6 P1-1 — one GMS policy, stated once

Formal builds replace GMS **only** through `.repo/local_manifests/equuleus.xml`
(`<remove-project name="vendor_gms"/>` + re-add `vendor_gms-15`).
`patches/0005-manifest-gms-repo.patch` is **archived as an alternative** and is
not applied in a normal build; enabling both raises `ManifestParseError`.
This is now stated identically in `build.sh`, `CLOUD_READINESS.md`, `README.md`,
`REPRODUCE.md` (via its generator) and `KNOWN_BLOCKERS.md`, and the acceptance
suite fails if any of them drifts back to the old wording.

### 7.7 P1-2 — `--network-only`

```
$ bash scripts/host-preflight.sh --network-only
--- 5. network reachability ---
--- 6. proxy / TLS sanity ---
```

Sections 1-4 (platform, toolchain, CPU/RAM, disk) are inside a
`if (( ! NETWORK_ONLY ))` guard, so the mode is independent of machine size and
can run on a minimum-spec instance before any commitment. It probes real git
transport (`git ls-remote`) against github.com, gitlab.com **and**
android.googlesource.com, plus curl-level HTTPS and a TLS/CA check that names
interception as the cause rather than advising anyone to disable verification.

**Still not executed, unchanged:** `repo sync`, `lunch`, Soong/Make, the kernel
build, flashing, and every hardware test. **No ROM was compiled. 未编译。**

---

---

## 8. Review round 7 — stale artifacts, stale docs, and `.git` assumptions

Three findings, all reproduced before being fixed.

### 8.1 Artifacts could be leftovers (P1)

**Reproduced.** `build.sh` asked only "does `PixelOS_*.zip` exist?" — so a zip
from an earlier attempt satisfied it. The device assertion was a `WARNING`, and
`ROM_ZIPS[0]` came from `sort` **by filename**, not by time.

**Fixed.** The build start time is captured before `mka`, and the artifact gate
now requires **all** of:

| Gate | Enforcement |
| --- | --- |
| ROM zip newer than build start | `find -newermt @${BUILD_STARTED_EPOCH}`; if nothing matches, the stale files are listed and the build exits 3 |
| `recovery.img` present and not stale | mtime compared against the build start |
| archive is structurally valid | `unzip -t` must pass |
| OTA asserts `equuleus` | `pre-device=equuleus` in `META-INF/com/android/metadata`, falling back to a legacy `assert(...)` in `updater-script` |
| no device assertion at all | **exit 3** — this used to be `[WARN]` |

The newest zip is chosen by **mtime**, not by filename.

**Proof (fault injection, `scripts/test_build_artifacts.py`):**

```
  [PASS] stale zip only -> reject                 exit=3 accepted=False
  [PASS] fresh zip+recovery, correct device       exit=0 accepted=True
  [PASS] fresh zip asserting different device     exit=3 accepted=False
  [PASS] fresh zip with no device assertion       exit=3 accepted=False
  [PASS] fresh zip is a corrupt archive           exit=3 accepted=False
  [PASS] fresh zip but no recovery.img            exit=3 accepted=False
  [PASS] two zips, stale one sorts first          exit=0 accepted=True
  [PASS] legacy updater-script assert             exit=0 accepted=True
all 8 cases behaved as required
```

The seventh case is the interesting one: a **stale zip whose filename sorts
first** must not shadow the fresh one. The old code would have picked it.

### 8.2 Documents still said "5 patches" (P2)

At the time of round 7, `sync.sh` applied **0001-0004** only, and two places still said "applies 5 patches". (Round 12 raised the real number to 7; see section 13.)

**Fixed**, and more importantly a **negative test now exists**, because the
reviewer correctly noted the previous consistency check had a blind spot: it
searched for the word "0005" but never compared a *count* against what the code
does.

`patch_count_matches_sync_script` counts the actual `apply_patch` invocations in
`sync.sh` and scans every shipped document for a contradicting `<n> patches`
claim (accepting "5" only when the same line says archived/not applied).

**That check immediately found a third stale line** — in `TEST_REPORT.md`
itself, which I had not noticed. That is the point of a negative test: it caught
the author, not just the reviewer's example.

### 8.3 `.git` was probed as a directory (P1)

**Reproduced.** git-repo may materialise a project as `path/.git/` (directory),
a `.git` **file** containing `gitdir: ...`, or a symlink. `[[ -d path/.git ]]`
reports the latter two as "not a git checkout".

Measured directly:

```
  d  is-inside=true   (directory layout)
  f  is-inside=true   (gitdir-file layout)
  d: -d .git = TRUE
  f: -d .git = FALSE   <-- false negative
```

**Fixed.** `build-preflight.sh` now asks git:

```bash
inside="$(git -C "$TREE/$path" rev-parse --is-inside-work-tree 2>/dev/null)"
[[ "$inside" == "true" ]]
```

and the `.repo` check validates `manifests.git` has a real HEAD instead of just
testing the directory exists.

### 8.4 An environment trap worth recording

While building the artifact test I hit a failure mode that cost several
iterations and is worth writing down, because it produced **three false PASSes**:

* `subprocess.run(["bash", ...])` on this host resolves to the **WSL** bash
  (`C:\Windows\System32\bash.exe`), which sees drives as `/mnt/c/...` and
  **cannot write** to the Windows tree. Every fixture `mkdir` failed with
  "Permission denied".
* With `set -e`, that made the harness exit 127, and because "not ACCEPTED"
  equals "rejected", three genuinely-failing cases looked like correct
  rejections.

Both are now impossible: the test resolves an explicit POSIX bash
(`C:/Program Files/Git/bin/bash.exe`) and treats exit 126/127 as a **test bug**,
never as a verdict. This mirrors the `find_bash()` logic already in
`verify_deliverables.py`.

### 8.5 Round-7 totals (all executed)

| Suite | Command | Result | Exit |
| --- | --- | --- | --- |
| static acceptance | `python scripts/verify_deliverables.py` | **37/37** runnable checks | 0 |
| mutation suite | `python scripts/verify_mutations.py` | **45/45** judged mutations caught | 0 |
| blob fault injection | `python scripts/test_verify_blobs.py` | **9/9** cases | 0 |
| artifact fault injection | `python scripts/test_build_artifacts.py` | **8/8** cases | 0 |

Logs: `logs/{verify,mutations,blobtest,arttest}-20261112T054128Z.log`.

### 8.6 Unchanged, and still not done

`repo sync`, `repo manifest -r` on a real tree, `lunch`, Soong/Make, the kernel
build, flashing, hardware. **No ROM was compiled. 未编译.** The artifact gate
above verifies what a *successful* build must produce — it has never run against
a real build, because there has never been one.

---

---

## 9. Review round 8 — two more false-pass paths in the artifact gate

Both were reproduced before being fixed, and both are now covered by the
project's own fault-injection suite.

### 9.1 Stale `recovery.img` accepted (P1-1)

**The bug.** The freshness test was an AND of two conditions:

```bash
if [[ ! "$RECOVERY_IMG" -nt "$TREE/build/envsetup.sh" ]] && \
   [[ "$(stat -c %Y "$RECOVERY_IMG")" -lt "$BUILD_STARTED_EPOCH" ]]; then
    die 3 "STALE"
fi
```

`build/envsetup.sh` comes from the sync, not from the build, so any recovery
image produced after the sync is "newer than envsetup.sh". The first test is
then false and the AND short-circuits — **a recovery.img older than the build
start was accepted**. Measured directly:

```
recovery mtime=1794457016  started=1794458816  envsetup=1794455216
  OLD: ACCEPTED  <-- stale recovery accepted because it is newer than envsetup.sh
  NEW: REJECTED
```

**Fix.** One criterion only — the build start marker:

```bash
RECOVERY_MTIME="$(stat -c '%Y' "${RECOVERY_IMG}")"
if (( RECOVERY_MTIME < BUILD_STARTED_EPOCH )); then
    die 3 "recovery.img is STALE: ..."
fi
```

### 9.2 Substring device match accepted `not_equuleus` (P1-2)

**The bug.** The legacy fallback used

```bash
grep -qE 'assert.*equuleus|getprop\("ro\.product\.device"\)\s*==\s*"equuleus"'
```

The first alternative is a substring match: it also matches
`assert(getprop("ro.product.device") == "not_equuleus")`. Measured:

```
script: assert(getprop("ro.product.device") == "not_equuleus");
  OLD: ACCEPTED  <-- matched not_equuleus
  extracted literal: [not_equuleus]
  NEW: REJECTED
```

**Fix.** Two-stage, exact:

1. `META-INF/com/android/metadata` is now **required** for a PixelOS 15 OTA,
   and `pre-device` must equal `equuleus` exactly. Missing metadata is fatal —
   the old code would fall back to a weaker legacy check.
2. If a legacy `updater-script` is also present, every device literal in a
   `getprop(...ro.product.device...) == "..."` comparison is **extracted and
   compared**, not grepped. `not_equuleus` and `equuleus_pro` are both rejected,
   and a legacy assertion that *contradicts* correct metadata is rejected too.

### 9.3 Regression coverage (P1-3)

`scripts/test_build_artifacts.py` went from 8 to **14 cases**. The two the
review asked for, plus three variants of the same class:

| New case | Expected |
| --- | --- |
| fresh zip + **STALE recovery** (newer than envsetup.sh) | reject |
| legacy assert **`not_equuleus`** | reject |
| legacy assert `equuleus_pro` (substring) | reject |
| metadata `pre-device` wrong | reject |
| legacy-only zip, no metadata | reject |
| metadata correct **but legacy contradicts** | reject |

```
  [PASS] fresh zip + STALE recovery -> reject     exit=3 accepted=False
  [PASS] legacy assert not_equuleus -> reject     exit=3 accepted=False
  [PASS] legacy assert equuleus_pro -> reject     exit=3 accepted=False
  [PASS] metadata pre-device wrong -> reject      exit=3 accepted=False
  [PASS] legacy-only zip, no metadata -> reject   exit=3 accepted=False
  [PASS] metadata ok but legacy contradicts       exit=3 accepted=False
all 14 cases behaved as required
```

### 9.4 Reverse verification — the new tests fail on the OLD code

This is the part that makes the fix credible. The old logic was reconstructed in
a sandbox (`work/` copy with the AND-condition and the loose regex restored) and
the **new** suite was run against it:

```
  [FAIL] fresh zip asserting different device     exit=0 accepted=True expected=reject
  [FAIL] fresh zip with no device assertion       exit=0 accepted=True expected=reject
  [FAIL] metadata ok but legacy contradicts       exit=0 accepted=True expected=reject
  [FAIL] fresh zip + STALE recovery -> reject     exit=0 accepted=True expected=reject
  [FAIL] legacy assert not_equuleus -> reject     exit=0 accepted=True expected=reject
  [FAIL] legacy assert equuleus_pro -> reject     exit=0 accepted=True expected=reject
  [FAIL] metadata pre-device wrong -> reject      exit=0 accepted=True expected=reject
  [FAIL] legacy-only zip, no metadata -> reject   exit=0 accepted=True expected=reject
8 CASE(S) REGRESSED
```

Eight cases turn red on the old code, including both the reviewer's
reproductions. On the fixed code all 14 pass.

### 9.5 Round-8 totals (all executed)

| Suite | Command | Result | Exit |
| --- | --- | --- | --- |
| static acceptance | `python scripts/verify_deliverables.py` | **41/41** runnable checks | 0 |
| mutation suite | `python scripts/verify_mutations.py` | **49/49** judged mutations caught | 0 |
| blob fault injection | `python scripts/test_verify_blobs.py` | **9/9** cases | 0 |
| artifact fault injection | `python scripts/test_build_artifacts.py` | **14/14** cases | 0 |

---

## 10. B-01 — proprietary blob source switched to the official LineageOS OTA

This section records a **source decision and verified format facts**, not an
extraction. `vendor/xiaomi/*` is still absent. Full detail: `BLOB_SOURCES.md`
and `blob_sources.json`.

### 10.1 The route

The LineageOS wiki (fetched 2026-11-12) documents that `extract-files.py`
accepts a LineageOS installation ZIP directly. Since the official equuleus build
is produced from the same four repositories this project pins, **one** OTA can
replace the five historical firmware images previously described.

### 10.2 Verified facts

| Fact | Evidence |
| --- | --- |
| LineageOS ships 22.2 for equuleus | `GET /api/v2/devices/equuleus` → HTTP 200, `versions:["22.2"]` |
| Its dependencies are our four pinned repos | `device_xiaomi_equuleus`, `device_xiaomi_sdm845-common`, `hardware_xiaomi`, `kernel_xiaomi_sdm845` |
| Three builds available | 2026-11-10 / 11-03 / 10-27, each with published SHA256 |
| Download reachable, ranged | HTTP 302 → 200, `Content-Length: 1223204572`, `Accept-Ranges: bytes` |
| Range request works | first 1,048,576 bytes fetched, HTTP **206** |
| It is a standard ZIP | magic `PK\x03\x04` |
| Its metadata asserts equuleus | `pre-device=equuleus`, `ota-type=BLOCK`, `post-sdk-level=35`, patch `2026-10-01` |

### 10.3 Delivered tooling

| Script | Purpose |
| --- | --- |
| `scripts/fetch_lineage_ota.sh` | download with resume, verify published SHA256, then read the OTA's own `pre-device` and refuse anything else |
| `scripts/extract_blobs_from_ota.sh` | run `extract-files.py` twice in the mandatory order (sdm845-common → equuleus), regenerate makefiles, run `verify_blobs.py --strict --json`, and print an explicit MISSING list |

Both were syntax-checked and their error paths exercised:

```
$ scripts/fetch_lineage_ota.sh --build 99999999      -> exit 2 (no recorded hash)
$ scripts/fetch_lineage_ota.sh --check-only --dest /tmp/emptyota -> exit 2
$ scripts/extract_blobs_from_ota.sh                  -> exit 2 (usage)
```

The metadata-validation logic was tested against three synthetic OTAs built from
the real metadata block: correct device → ACCEPT, `dipper` → REJECT, no metadata
→ REJECT.

### 10.4 What was NOT done

| Step | Status | Why |
| --- | --- | --- |
| Full 1.2 GiB OTA download | **not done** | only the 1 MiB header was fetched, to prove format and device assertion |
| `extract-files.py` run | **not done** | needs a synced PixelOS tree (hundreds of GiB) for Soong name resolution |
| `vendor/xiaomi/equuleus` generated | **NOT GENERATED** | — |
| `vendor/xiaomi/sdm845-common` generated | **NOT GENERATED** | — |
| `verify_blobs.py --strict` on real blobs | **not run** | no blobs to verify |

`blob_sources.json` carries these as explicit `false` flags, and the acceptance
suite fails if any of them is ever flipped to `true` without the work having
happened.

**B-01 remains S1 / OPEN.** No binary was fabricated. The exact remaining steps
are in `BLOB_SOURCES.md` §5.

### 10.5 Still not done anywhere in this project

`repo sync`, `repo manifest -r` on a real tree, `lunch`, Soong/Make, the kernel
build, flashing, and every hardware test. **No ROM was compiled. 未编译。**
Screen fingerprint, camera and NFC are **unverified** — static interface
configuration is not hardware validation.

---

---

## 11. B-01 executed for real — OTA to verified vendor trees

Earlier rounds stopped at "source identified, tooling written". This one actually
ran the extraction. Every number below comes from a command that executed on
2026-11-12.

### 11.1 The OTA

| | |
| --- | --- |
| File | `lineage-22.2-20261110-nightly-equuleus-signed.zip` |
| Size | 1,223,204,572 bytes |
| SHA256 | `2ebd3d4bb7168135353c8b543bb79da4e53a1efccf32fd91c498e9fa9fe365ee` |
| vs published | **match** |
| `pre-device` | `equuleus` |
| `ota-type` | `BLOCK` |

### 11.2 Partition extraction

The OTA is a classic block OTA (`<part>.new.dat.br` + `.transfer.list`), not a
`payload.bin` image. The transfer list is the **command form**:

```
4
161531                    <- blocks the "new" commands will write
0
0
new 2,0,1024              <- kind, op, then half-open destination ranges
new 2,1024,2048
```

Two format facts had to be established empirically rather than assumed, because
a wrong reading silently produces a corrupt image:

1. For `vendor` the header (**161531**) equals the block count of the `new`
   ranges *and* the size of `.new.dat` / 4096.
2. For `product`, `system_ext` and `system` the header is **larger** than both.
   Measured: `product` header 135344, `new` ranges 128136, `.dat` 128136 blocks.
   The header counts the writer's expected total including `erase` fill; it is
   **not** an integrity check. The trustworthy invariant is
   `new-range blocks == dat_size/4096`, which held for **5/5** partitions.

Validation now asserts that invariant, so a mis-parsed list fails loudly instead
of emitting garbage.

| Partition | Blocks written | Image size | Left zero | Files dumped |
| --- | ---: | ---: | ---: | ---: |
| vendor | 161,531 | 661,630,976 | 0 | 1,463 |
| product | 128,136 | 2,522,021,888 | 487,592 | 501 |
| system_ext | 104,076 | 528,396,288 | 24,927 | 3,572 |
| system | 242,820 | 1,106,661,376 | 27,361 | 2,715 |
| odm | 375 | 1,536,000 | 0 | 17 |

All five validate as ext filesystems (magic `0xEF53`, labels `vendor`,
`product`, `system_ext`, `/`, `odm`). Dumps were produced with
`debugfs -R 'rdump / …'`, which is read-only; the source images were never
modified and no root or loop mount was used.

### 11.3 Blob-list resolution — 862 entries

| | equuleus | sdm845-common | total |
| --- | ---: | ---: | ---: |
| entries | 235 | 627 | **862** |
| source path hit | 233 | 589 | 822 |
| destination already present | 1 | **35** | 36 |
| found by rename | 1 | 3 | 4 |
| **missing** | **0** | **0** | **0** |

The 35 destination-only entries are one class: the list names `product/…` or
`system/…`, LineageOS ships them under `system_ext/…`. All 35 were installed at
their declared `dst` and verified present.

### 11.4 `libpn553_fw.so` — the architecture question

| | |
| --- | --- |
| List requests | `vendor/lib/libpn553_fw.so` (32-bit path) |
| OTA contains | only `vendor/lib64/libpn553_fw.so` |
| Size | 37,490 bytes |
| Class | **ELF64**, machine **183** (`EM_AARCH64`) |
| `DT_SONAME` | none |
| `DT_NEEDED` | none |
| Reference | `libnfc-nxp.conf: NXP_FW_NAME="libpn553_fw.so"` |
| Sibling | `vendor/firmware/libpn553_rec.so`, same size |

It is NFC **firmware in an ELF container**, loaded by filename, so no 32-bit ABI
applies. A 64-bit ELF placed at a `lib/` path would make a 32-bit consumer fail
to map it — worse than absent. The list is corrected by
`patches/0006-equuleus-fix-pn553-fw-path.patch` (verified with
`git apply --check`), and the file installs at `lib64/`.

### 11.5 Fixups were deliberately not re-run

The OTA already carries upstream's fixups. Proof:
`vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so` has
`DT_SONAME == fingerprint.goodix_fod.sdm845.so`, i.e. the rename is already
applied. Re-running `FIX_SONAME` would double-patch.

This exposed a **bug in `verify_blobs.py`**, found by the real data: it reported
`BAD_FIXUP` for entries that declare a `fixup_hash` with no fixup function, even
when the hash matched exactly. Four files showed `expected == actual` and were
still failed. Corrected semantics:

* `fixup_hash` matches → **OK** (the source ROM already applied the fixup);
* `fixup_hash` differs → **FAIL**.

`scripts/test_verify_blobs.py` now covers both halves of that branch.

### 11.6 Strict verification of the generated trees

```
[sdm845-common] 627/627 declared entries present
[equuleus]      235/235 declared entries present
OK=0  FAIL=0  RESIGNED=5  UNVERIFIABLE=0  SKIPPED=857
RESULT: every declared entry is present and every declared
        property was verified against the installed file.
```

| Check | Result |
| --- | --- |
| ELF32 under `lib/` | 273, all correct |
| ELF64 under `lib64/` | 351, all correct |
| wrong-directory architecture | **0** |
| `DT_SONAME` == installed basename | 538 |
| `DT_SONAME` mismatching | **0** |

**5 APKs are `RESIGNED`.** `dpmserviceapp`, `PowerOffAlarm`, `WfdService`, and
two `HotwordEnrollment*WCD9340` APKs hash differently from their pinned values
because LineageOS re-signs platform APKs. They are reported with both hashes, as
neither a pass nor a defect. This is honest but incomplete: without the original
unsigned build there is no way here to prove the code inside is unchanged.

### 11.7 Deliverables produced

| Path | Size | Files |
| --- | --- | --- |
| `vendor/xiaomi/equuleus` | 248 MiB | 240 |
| `vendor/xiaomi/sdm845-common` | 277 MiB | 632 |

Each contains `Android.bp`, `Android.mk`, `BoardConfigVendor.mk`,
`<module>-vendor.mk` and `EXTRACTION_REPORT.json`.
Full record: `B01_EXTRACTION_REPORT.json`.

### 11.8 New scripts (all executed, not just written)

| Script | Role |
| --- | --- |
| `scripts/ota_extract.py` | block-OTA → ext4 images, with the source-vs-spec integrity check |
| `scripts/img_extract.sh` | `debugfs` dump, read-only |
| `scripts/blob_audit.py` | resolve all 862 entries, classify each |
| `scripts/make_vendor_trees.py` | copy, relocate, emit makefiles, refuse 64-bit-in-lib |
| `scripts/extract_vendor_full.sh` | the whole pipeline in one command |

### 11.9 What this does NOT establish

**No ROM was compiled.** `repo sync`, `lunch`, Soong and `mka bacon` have never
run. Nothing was flashed. **Screen fingerprint, camera and NFC remain
unverified on hardware** — having the right blob files is a prerequisite, not
evidence.

Also: the trees came from a purpose-built extractor, not upstream
`extract-files.py`, which needs a synced tree for Soong name resolution. The
output is verified against the same lists, but the code path differs and should
be cross-checked on a real synced tree.

---

---

## 12. IR face unlock — static acceptance passed, device tests NOT RUN

**Verdict: NOT VERIFIED.** The configuration is in place and mechanically
checked; no part of this feature has been observed working.

### 12.1 What was verified statically

`python scripts/verify_ir_face_unlock.py` → **9/9 checks pass**:

| # | Check | Result |
| --- | --- | --- |
| 1 | ParanoidSense source still reads `ro.face.sense_service.camera_id` | pass |
| 2 | device sets that property to an aux id (5) | pass |
| 3 | `vendor.camera.aux.packagelist` contains `co.aospa.sense` | pass (5 entries) |
| 4 | all 4 original packagelist entries preserved | pass |
| 5 | OV9282 IR sensor + module + tuning data present | pass |
| 6 | camera HAL + `libcamxfdengine.so` present | pass |
| 7 | no reliance on the RGB front-camera fallback | pass |
| 8 | both patches apply to pinned upstream commits | pass |
| 9 | upstream ParanoidSense tree unmodified | pass |

### 12.2 Negative tests — the checks actually bite

Each of these was applied to a scratch copy and the suite re-run:

| Seeded defect | Expected | Observed |
| --- | --- | --- |
| remove `ro.face.sense_service.camera_id` | fail | 7/9, checks 2 and 7 red |
| drop `co.aospa.sense` from packagelist | fail | 8/9, check 3 red |
| set `camera_id=0` (primary RGB — the "RGB pretending to be IR" case) | fail | 7/9, checks 2 and 7 red |
| delete `com.qti.sensor.ov9282.so` | fail | 8/9, check 5 red |

The third case is the important one: it is exactly the substitution this task
forbids, and the suite refuses it.

### 12.3 Device test plan — NOT RUN

Nothing below has been executed. No build exists, so there is nothing to flash.

**Prerequisites:** a built ROM, an unlocked bootloader, and a dark room.

| # | Test | Method | Pass criterion |
| --- | --- | --- | --- |
| 1 | Camera identity | `adb shell 'getprop ro.face.sense_service.camera_id'`; `adb shell dumpsys media.camera \| grep -E "Facing\|Camera [0-9]"` | property is set AND the referenced id is the OV9282/IR device, not a `LENS_FACING_FRONT` RGB camera |
| 2 | App presence | `adb shell pm list packages \| grep co.aospa.sense`; `adb shell dumpsys package co.aospa.sense \| grep -i camera` | installed as a privileged app with CAMERA permission |
| 3 | Aux exposure | `adb shell 'getprop vendor.camera.aux.packagelist'`; confirm the app can actually open the aux id (logcat for `CameraAccessException` or an id clamp) | no clamp, no access exception |
| 4 | Face enrolment | Settings → Security → Face unlock; enrol in a **normally lit** room | completes; `adb logcat \| grep -i sense` shows no Megvii errors |
| 5 | Daylight unlock | lock, raise, unlock, 10 attempts | ≥ 9/10, and logcat shows the IR id being opened |
| 6 | Dim light | ~5 lux (a dimmed room), 10 attempts | ≥ 8/10 |
| 7 | **Complete darkness** | 0 lux, screen off, 10 attempts | ≥ 8/10 — **this is the test that separates IR from RGB**; an RGB fallback scores ~0 here |
| 8 | Reboot persistence | `adb reboot`, then unlock without re-enrolling, 5 attempts | enrolled face survives; ≥ 4/5 |
| 9 | Failure and retry | unlock with eyes closed / face partially covered / from > 1 m | fails without unlocking, offers retry, does not lock out spuriously |
| 10 | Wrong person | a different face, 10 attempts | 0/10 unlocks |
| 11 | **Photo spoof** | a printed photo of the enrolled face and a phone-screen photo | both rejected. `config_face_intro_show_require_eyes` is `false`, so eyes-open checking may be off — if a photo unlocks, this is a **security defect**, not a pass |
| 12 | IR vs RGB discrimination | cover the IR emitter/illuminator, then retry in the dark | unlock fails. If it still succeeds in complete darkness with the illuminator blocked, the pipeline is not using IR |

Test 7 and test 12 together are what prove the feature is genuinely IR. Without
them, "face unlock works" is an unsupported claim.

### 12.4 Recording results

For each run record: build fingerprint (`adb shell getprop ro.build.fingerprint`),
the camera id in effect, lux estimate, attempt count, and the relevant logcat
excerpt. Until that exists, this section stays **NOT VERIFIED**.

---

---

## 13. Round 12 — build pipeline now applies the full patch set

### 13.1 The gap that was closed

`sync.sh` applied only 0001-0004. Patches 0006 (NFC firmware path), 0007 (IR
camera id) and 0008 (aux camera allow-list) existed but were never applied by a
normal sync, so a build would have silently shipped:
an NFC service looking for `vendor/lib/libpn553_fw.so` that does not exist, and
ParanoidSense falling back to the RGB front camera.

### 13.2 What is now enforced

| Gate | Where | Effect |
| --- | --- | --- |
| 7 patches applied, idempotently | `sync.sh` | second run reports `[SKIP] … already applied`; a non-applying patch aborts |
| post-apply content checks | `sync.sh` | after applying, it greps the tree for the camera id, the corrected NFC path and `co.aospa.sense`; a misplaced hunk fails |
| 7 patches verified present | `build-preflight.sh` | `patch_state` on each, forward-or-reverse |
| resulting content verified | `build-preflight.sh` | NFC path, no stale 32-bit path, camera id, aux list, and all 4 original package names |
| IR static acceptance | `build.sh` | runs `verify_ir_face_unlock.py` before the expensive phase; failure stops the build |

### 13.3 Measured: patch idempotency

Two consecutive runs against fresh clones of the two device trees:

```
=== PASS 1 (fresh tree) ===
  [APPLIED] 0001 … 0002 … 0003 … 0004 … 0006 … 0007 … 0008
rc=0

=== PASS 2 (same tree) ===
  [SKIP]    0001 … 0002 … 0003 … 0004 … 0006 … 0007 … 0008 (already applied)
rc=0
```

All seven apply once and are recognised as applied thereafter.

### 13.4 Measured: content verification bites

Removing `ro.face.sense_service.camera_id` from a fully patched tree:

```
[FAIL] camera id missing -> ParanoidSense would use RGB
```

Removing the two device-tree changes while **keeping both patch files on disk**:

```
[FAIL] device sets ro.face.sense_service.camera_id
[FAIL] vendor.camera.aux.packagelist contains co.aospa.sense
[FAIL] no reliance on the RGB front-camera fallback
[FAIL] device tree reflects the patches (not just the files)
6/10 checks passed
```

The last line is the point of P1-1: patch files on disk are not evidence. The
check reads the device tree.

### 13.5 Vendor archive produced and self-verified

| | |
| --- | --- |
| Files | 872 (equuleus 240, sdm845-common 632) |
| Uncompressed | 546,824,712 bytes |
| Empty files | 0 |
| Archive | `vendor-xiaomi-20261112.tar.xz`, 194 MiB |
| SHA256 | `43d2e8536e5cbbe71da969293d9bf9be8d4144cf88274587ad27fb55e7851f01` |

`pack_vendor.sh` extracts its own archive and re-checks all 872 files against
`MANIFEST.sha256` before reporting success. Receive-side workflow was exercised
end to end: volume checksum OK, reassembled hash matches, extraction yields 872
files all matching the manifest. Procedure: `VENDOR_TRANSFER.md`.

### 13.6 Unchanged

No ROM has been compiled. `extract-files.py` has never cross-checked these trees.
**IR face unlock is NOT VERIFIED ON DEVICE** — `camera_id=5` is inferred from the
OV9282 sensor being the only monochrome part and from the established sdm845
adaptation, not measured on hardware. FOD, camera and NFC are likewise unverified.

---

---

## 14. MIUI factory firmware — IR blob comparison (round 13)

### 14.1 Firmware verified before use

| Step | Result |
| --- | --- |
| File | `equuleus_images_V12.5.2.0.QECCNXM_20211118.0000.00_10.0_cn_4ce136c735.tgz`, 3,199,269,356 B |
| `gzip -t` | rc=0 — the whole 2.98 GB stream decompresses cleanly |
| Layout | MIUI **fastboot** package: `images/*.img`, `md5sum.xml`, flash scripts |
| `vendor.img` md5 | `d6f41fa1d7303393b5a7760a02064160` — **matches Xiaomi's own manifest** |

The md5 match is what makes everything below meaningful: the bytes compared are
what Xiaomi shipped, not an unverified mirror.

### 14.2 Extraction actually performed

| Step | Tool | Result |
| --- | --- | --- |
| Sparse → raw | `scripts/simg2img.py` (new) | 262,144 × 4096 = 1,073,741,824 B; 14 raw + 13 don't-care chunks; exact size match |
| Dump | `debugfs -R 'rdump / …'` | **2,070 files**, read-only, no root |

### 14.3 Comparison result

`scripts/compare_ir_blobs.py` over 18 IR-relevant paths, comparing SHA256,
ELF class, machine, `DT_SONAME` and `DT_NEEDED`:

| Verdict | Count |
| --- | ---: |
| **IDENTICAL** | **12** |
| DIFFERS | 1 |
| MIUI-ONLY | 2 |
| ABSENT-BOTH | 3 |

The OV9282 IR stack and the camera HAL are all **byte-identical**:

```
com.qti.sensor.ov9282.so          28,288 B  ELF32 machine=40  SONAME/NEEDED equal
com.qti.sensormodule.ov9282.bin   39,101 B  identical
com.qti.tuned.ofilm_ov9282.bin   379,825 B  identical
lib/hw/camera.qcom.so          3,275,248 B  ELF32 machine=40  identical
camxoverridesettings.txt             856 B  identical
```

### 14.4 The one difference, measured

`lib/libmmcamera_faceproc.so` differs by **exactly 3 bytes**, at offsets
`0x7FE0`, `0x7FE2`, `0x7FE4`, values `0x03 0x03 0x03` (MIUI) vs `0x01 0x01 0x01`
(LineageOS). That is the ELF symbol-version table, and upstream
`extract-files.py` declares `clear_symbol_version` for exactly three symbols
(`__aeabi_memcpy`, `__aeabi_memset`, `__gnu_Unwind_Find_exidx`).

Conclusion: it is LineageOS's own fixup applied to the same MIUI blob, not a
version difference. The LineageOS copy is the corrected one and must be kept.

### 14.5 Static acceptance: 11/11

`scripts/verify_miui_ir_analysis.py`:

| # | Check | Result |
| --- | --- | --- |
| 1 | three MIUI analysis documents delivered | pass |
| 2 | LineageOS IR stack present | pass |
| 3 | OV9282 driver is ELF32/EM_ARM | pass |
| 4 | IR blobs re-verified **live**, not from cache | pass |
| 5 | LineageOS faceproc fixup still intact (`[1,1,1]`) | pass |
| 6 | comparison recorded and coherent (18 rows) | pass |
| 7 | faceproc differs by exactly 3 bytes at the documented offsets | pass |
| 8 | upstream fixup explains those 3 bytes | pass |
| 9 | MIUI aux mechanism documented (XML list, not the AOSP property) | pass |
| 10 | no patch installs MIUI binaries over LineageOS blobs | pass |
| 11 | NOT VERIFIED markings present | pass |

### 14.6 Negative tests that caught real gaps

Two seeds were applied to a scratch copy:

| Seeded defect | Expected | Actually observed |
| --- | --- | --- |
| tamper one byte of the LineageOS OV9282 driver | fail | **first attempt passed 9/9 — a real defect** |
| reinstate MIUI's raw `0x03` faceproc bytes | fail | fail (2 checks red) |
| delete `logs/miui-ir-compare.json` | fail | fail |

The first row is worth recording: the original check trusted the cached
comparison JSON, so tampering with the actual blob was invisible. It was fixed by
re-hashing live on every run, plus a dedicated check that the fixup bytes are
still `[1,1,1]`. Both seeds now fail correctly.

### 14.7 Verdict

**No MIUI component needs adding; no blob patch was emitted.** Adding one would
overwrite correct LineageOS blobs with uncorrected MIUI ones.

**Camera id: still NOT VERIFIED ON DEVICE.** MIUI's `device_features/equuleus.xml`
does not declare an IR camera id at all — MIUI resolves it inside its own
`com.xiaomi.biometric` service. So the factory firmware does not corroborate
`camera_id=5`, and the previous round's conclusion stands unchanged.

**IR face unlock remains NOT VERIFIED.** No ROM built, nothing flashed, no IR
frame ever captured. Device test plan: `IR_FACE_UNLOCK_DEPENDENCIES.md` §8,
including the two tests that actually discriminate IR from RGB (dark-room unlock
and emitter-blocked retry).

---

---

## 15. Round 14 — review fixes, and why no build was run here

### 15.1 The four reported defects, fixed and now guarded

| # | Defect | Fix | Guard |
| --- | --- | --- | --- |
| 1 | `MIUI_IR_BLOB_INVENTORY.md` gave the 32-bit `libcamxfdengine.so` as 110,912 B (the 64-bit value) | corrected to **86,480 B** | new check parses every size row and compares against `logs/miui-ir-compare.json` — **10 sizes cross-checked** |
| 2 | IR illuminator control was described as if known | rewritten as **NOT VERIFIED**, with an explicit table separating an IR *blaster* (absent on this device) from the face-unlock *illuminator* (control path unknown) | new check rejects the old over-confident wording and requires the blaster/illuminator distinction |
| 3 | README / CLOUD_READINESS claimed B-01 still blocked everything | updated: B-01 closed for extraction, 872 files / 546,824,712 B, `FAIL=0`; P2 now MET; verdict changed to GO for a pay-as-you-go compile check | existing doc-consistency checks |
| 4 | `sync.sh` ended by telling the reader the trees were "intentionally absent" and to extract from a MIUI package | replaced with a live check of both blob trees, pointing at the LineageOS-OTA route and `VENDOR_TRANSFER.md` | the message now branches on reality, so it cannot go stale silently |

Round-14 static suites: **46/46 acceptance**, **13/13 MIUI**, **12/12 IR**,
**9/9 blob**, **14/14 artifact**; 12 shell scripts parse on GNU bash.

### 15.2 Transfer rehearsal, end to end

A receive was simulated on a clean directory:

```
1. per-volume checksums     part001: OK
2. reassemble               sha256 43d2e853…851f01
3. extract into the tree    OK
4. per-file manifest        all 872 files match
5. verify_blobs.py --strict  FAIL=0  RESIGNED=5  862/862 present
Transfer verified. The tree is ready for scripts/build.sh.
```

That rehearsal found two real bugs, both fixed:

* the `receive` mode reported a bare "blob verification failed" when the device
  trees were absent, which reads like corrupt blobs. It now names the missing
  `device/xiaomi/<name>/proprietary-files.txt` and states that the blobs
  themselves did match the manifest.
* the script's interpreter probe accepted `python3` on Windows, where that name
  is the Microsoft Store stub that exits non-zero. It now probes the interpreter
  with a real expression before trusting it.

A third bug was found in the new portability checker itself: `bash -n` on a
Windows path silently failed for all 12 scripts. Fixed by resolving Git-bash's
`bash.exe` explicitly and converting paths to forward slashes.

### 15.3 Why the build was NOT run

The instruction was to proceed to `repo sync`, Soong/Make checks and the first
compile. That was attempted to the extent this host allows, and it cannot be done
here:

| Requirement | This host |
| --- | --- |
| free disk for a full sync (~165 GiB) | **16 GiB** |
| `repo` tool | **absent** |
| `android.googlesource.com` reachable | **unreachable** |

Renting the instance is the user's decision and is prohibited by an earlier
standing constraint, so no instance was created. Instead the exact sequence is
written out in `FIRST_BUILD_RUNBOOK.md`, including the cheapest first gate
(`host-preflight.sh --network-only`) and a Soong/Make sanity pass
(`m nothing`) that catches configuration errors before a multi-hour compile.

**No build result is reported, because none exists.** `repo sync`, `envsetup`,
`lunch`, `mka` and every flash and device test remain **NOT EXECUTED**.

### 15.4 What a successful build still would not verify

IR face unlock (`camera_id=5` provisional), illuminator control, FOD, camera,
NFC, modem, Wi-Fi/BT, audio, charging, thermal — all need the phone. Device test
plans: `TEST_REPORT.md` §12 and `IR_FACE_UNLOCK_DEPENDENCIES.md` §8.

---

---

## 16. Round 15 — the BUILD READY bypass, and six faults that now fail closed

> **No ROM was compiled.** `repo sync`, `envsetup`, `lunch`, `mka` and every flash
> and device test were not executed on any host.

### 16.1 The reported P0, reproduced before it was fixed

The review described one condition precisely: *device tree present, blobs present,
target source tree has no `scripts/verify_blobs.py`*. Reproduced on the actual
script:

```
5. the real gate: verify_blobs.py --strict
  [SKIP] scripts/verify_blobs.py not present in the tree
         run it from the project checkout against /tmp/p0repro/tree

Transfer verified. The tree is ready for scripts/build.sh.
=== EXIT CODE: 0 ===
```

The bypass was structural: the receive step looked for the verifier **inside the
target tree**, and treated its absence as a skip rather than a failure. A tree
with no verification whatsoever reported ready.

**Fix.** The verifier is always `${SCRIPT_DIR}/verify_blobs.py` — it belongs to
this project, not to the PixelOS source tree. Three failure modes now all exit
non-zero and never print `BUILD READY`:

| Condition | Behaviour |
| --- | --- |
| verifier missing from the project | `die`, exit 1, "project-integrity failure" |
| device trees absent (cannot know what to check) | `die`, exit 1, names the missing `proprietary-files.txt` |
| verifier exits non-zero | `die`, exit 1, prints the last 12 lines of its output |
| verifier exits 3 (UNVERIFIABLE) | `die`, exit 1, distinguished from a hard failure |
| exit 0 but JSON report shows `FAIL>0` | `die`, exit 1 — the exit code alone is not trusted |

`BUILD READY` prints only after the transfer hash, the per-file manifest **and**
the strict blob verification all pass.

### 16.2 Measured before/after

```
before:  rc=0   "the tree is ready for scripts/build.sh"   [SKIP] no verifier
after:   rc=1   "cannot verify: ... is missing"            no BUILD READY
```

### 16.3 Fault injection — 7/7

`scripts/test_first_build_flow.py` seeds real conditions and asserts exit codes:

| Case | Result |
| --- | --- |
| verifier missing from the project | rc=1, no BUILD READY |
| archive volume corrupted (bit-rot) | rc=1, no BUILD READY |
| `MANIFEST.sha256` missing | rc=1, names MANIFEST |
| too little free space | `build.sh` has the guard |
| wrong lunch target | target asserted |
| stale volume from another date | rc=1, no BUILD READY |
| happy path | rc=0, BUILD READY present |

Writing this suite caught two bugs in the tests themselves, both of which had made
a broken script look fine:

* case 2 corrupted the extracted tree, but `receive` re-extracts from the archive
  in step 3, silently undoing it. It now corrupts the **archive volume**, which is
  both what real bit-rot looks like and not undone by extraction.
* case 1 asserted on error wording rather than the contract (non-zero + no BUILD
  READY), so it failed for cosmetic reasons.

### 16.4 The other five P0/P1 items

| # | Defect | Fix |
| --- | --- | --- |
| 2.1 | runbook never passed `--tree` to `host-preflight.sh`, so it audited the ~40 GiB system disk | every invocation now `--tree /data/pixelos15`; §1.1 explains why the build disk must be `/data` |
| 2.2 | runbook said "≥300 GiB" while `build.sh` and `CLOUD_READINESS.md` imply otherwise | unified on **≈600 GiB data disk**, with 400 GiB stated as the hard floor |
| 2.3 | runbook duplicated `repo init`/`repo sync` by hand as well as `sync.sh` | manual sequence deleted; §2 is one `sync.sh` call, and documents why it deliberately omits the force-sync flag, which would discard local commits |
| 2.4 | deployment used `git clone … \|\| true`, hiding a failed download | replaced with an upload-the-ZIP procedure plus an explicit `rc` check; the runbook now warns against `\|\| true` |
| 2.5 | verification scripts addressed as if inside the PixelOS tree | all calls pinned to `/opt/port/scripts/…` |
| 2.6 | `lunch aosp_equuleus-userdebug` | corrected to **`aosp_equuleus-bp1a-userdebug`**; the runbook explains the release segment is required |
| 3 | `scp … *.part*` shipped neither manifest and could concatenate old volumes | explicit file list: every volume of **one date** + `VOLUMES.sha256` + `MANIFEST.sha256`; stale dates refused on both upload and receive; volume count cross-checked against `VOLUMES.sha256`; single shared directory |
| P1 | `extract_vendor_full.sh` printed the OTA sha256 without comparing it | now compares against `EXPECTED_OTA_SHA256` (default = the verified digest) and aborts on mismatch |

### 16.5 `SKIPPED=857` — the wording that was overclaiming

`VENDOR_TRANSFER.md` now separates two guarantees that were being blurred:

| Guarantee | Mechanism | Coverage |
| --- | --- | --- |
| transport integrity | `MANIFEST.sha256` + `VOLUMES.sha256` | **all 872 files**, individually |
| declared-property verification | `verify_blobs.py --strict` | only what each line declares |

`SKIPPED=857` means 857 entries pin **no hash**, so their **content provenance is
unverified**. It does not mean they failed, and it must not be read as "857 files
were content-verified". The defensible statement is now written out in the doc.

The MIUI comparison is the separate evidence that 12 IR-critical blobs are
byte-identical to Xiaomi's md5-verified firmware — but only for those 12 paths.

### 16.6 Static suites after round 15

**50/50 acceptance** (4 new checks for this round), **7/7 first-build fault
injection**, 13/13 MIUI, 12/12 IR, 9/9 blob, 14/14 artifact.

Two new checks initially failed for the right reason — they were too weak:

* the `--tree` assertion matched the flag anywhere, including on the
  `extract_vendor_full` call, so removing it from `host-preflight` still passed;
* the upload assertion matched the string `mapfile -t FILES`, which the seeded
  no-op variant still contains.

Both were bound to the specific invocation and re-verified against the seeds.

### 16.7 Still not done

The build itself. This host has 16 GiB free, no `repo`, and no route to
`android.googlesource.com`. `FIRST_BUILD_RUNBOOK.md` is now correct enough to
execute, but **executing it is still pending**, and no compile result exists.

---

## 5. What a reader should conclude

* The **source and tooling side** is complete and mechanically verified: pins are
  real commits, all five patches apply to real clones, the GMS dependency is
  identified and repointed with evidence, and the blob verifier parses the real
  grammar rather than guessing from basenames.
* The **binary side is untouched**: no blob, no ROM, no boot.
* Therefore: **not flashable, not testable, not working.**
* Still unverified and explicitly so: `repo sync`, `repo manifest -r` on a real
  tree, Soong/Make, the kernel build, and every hardware subsystem.
