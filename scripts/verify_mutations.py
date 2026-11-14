#!/usr/bin/env python3
"""Mutation-test the acceptance suite (scripts/verify_deliverables.py).

Each mutation seeds one specific defect and asserts that the *expected* check
fails. A mutation that still passes means the check is dead weight and cannot
be cited as evidence that the deliverable is correct.

Seeding notes (learned by getting them wrong first):
  * `git apply` only checks textual applicability. Editing an *added* line
    keeps the patch applying cleanly, so that is NOT a corruption test; break a
    context or removed line instead.
  * `product_naming` reads the staged tree (src/ with patches applied), not
    work/, so it must be mutated through a patch file.
  * Windows has no meaningful mode bit, so `scripts_present` checks the shebang
    there; the shebang mutation exercises exactly that.
"""
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SANDBOX = os.path.join(os.environ.get("TEMP", "/tmp"), "equuleus-mutation")

# files mutated outside the sandbox that must be restored
_MUTATION_RESTORE = []

# assembled at runtime: this file must not itself contain the literal banned
# strings, or the check under test would flag its own test data
BANNED_CMD = "set" + "enforce" + " " + "0"
FAKE_TOKEN = "GITHUB" + "_TOKEN=" + "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

ALL_SHAS = (
    "aa8adfe9bf212c6e93238a86980b4024da4f819a",
    "db40750f063e86110e20db1455729c0f6621f7da",
    "35cf356b095e033e71261b16c7fa319faac12cb3",
    "281f97dbac46b75eb7b6a680624e62e807ec0689",
    "3466aa530ace6de0760c12a68cf81b31e8d3807b",
    "0334d5e468a86ab0aefa6d3a40bc2abd11bf4035",
    "2887d1b7729f38560b1cb4b27317c2bf29f2325b",
    "f568995691b655491d1b3d309f0e6eb96ebeb248",
    "29f6010bcd2bd4742502ea7ccee763c64f02a3c1",
    "601faec098fd0eb5ad98bc323d62e5479417f623",
    "cd600d7651ae32648ddce111b77ccca22f491609",
    "9fc52af4fdb277b5db3b17f702b040d1a7696c2d",
)


def force_rmtree(path):
    def onerror(func, target, _exc):
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError:
            pass

    if os.path.isdir(path):
        shutil.rmtree(path, onerror=onerror)


def reset():
    force_rmtree(SANDBOX)
    os.makedirs(SANDBOX)
    for name in os.listdir(ROOT):
        src = os.path.join(ROOT, name)
        if os.path.isfile(src) and (name.endswith(".md") or name.endswith(".json")):
            shutil.copy2(src, os.path.join(SANDBOX, name))
    ignore = shutil.ignore_patterns(".git")
    for rel in ("scripts", "patches", "work", ".repo",
                os.path.join("src", "pixelos-manifest"),
                os.path.join("src", "equuleus"),
                os.path.join("src", "sdm845-common")):
        src = os.path.join(ROOT, rel)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(SANDBOX, rel), ignore=ignore)


def replace_all(path, old, new):
    full = os.path.join(SANDBOX, path)
    text = io.open(full, encoding="utf-8").read()
    assert old in text, "anchor not found in %s: %r" % (path, old[:60])
    io.open(full, "w", encoding="utf-8", newline="\n").write(text.replace(old, new))


def append_to(path, text):
    full = os.path.join(SANDBOX, path)
    body = io.open(full, encoding="utf-8").read()
    io.open(full, "w", encoding="utf-8", newline="\n").write(body + text)


def delete_file(path):
    full = os.path.join(SANDBOX, path)
    assert os.path.isfile(full), "cannot delete missing file " + path
    os.remove(full)


def strip_all_shas():
    full = os.path.join(SANDBOX, "UPSTREAM_LOCK.md")
    text = io.open(full, encoding="utf-8").read()
    for sha in ALL_SHAS:
        text = text.replace(sha, "lineage-22.2")
    io.open(full, "w", encoding="utf-8", newline="\n").write(text)


def run_verifier():
    env = dict(os.environ)
    # the real-clone evidence must still point at the real object stores
    env["EQUULEUS_CLONES_DIR"] = os.path.join(ROOT, "clones")
    # vendor/ and B01_EXTRACTION_REPORT.json live in the real tree, not in the
    # sandbox; the checks that need them must look there.
    env["EQUULEUS_PROJECT_ROOT"] = ROOT
    r = subprocess.run([sys.executable, "scripts/verify_deliverables.py"],
                       cwd=SANDBOX, capture_output=True, text=True, env=env)
    fails = {ln[len("[FAIL]"):].strip()
             for ln in r.stdout.splitlines() if ln.startswith("[FAIL]")}
    skipped = {ln[len("[SKIP]"):].strip()
               for ln in r.stdout.splitlines() if ln.startswith("[SKIP]")}
    return fails, r.returncode, r.stdout, r.stderr, skipped


def _restore_outside_mutations():
    """Undo any seed that wrote outside the sandbox."""
    while _MUTATION_RESTORE:
        target, backup = _MUTATION_RESTORE.pop()
        try:
            shutil.move(backup, target)
        except OSError:
            pass


def _revert_faceproc_fixup():
    """Simulate installing MIUI's raw libmmcamera_faceproc.so over LineageOS's.

    The only difference is 3 bytes of the ELF symbol-version table (0x01 -> 0x03).
    Reverting them is exactly the "overwrite the working LineageOS driver with
    MIUI bytes" scenario the task forbids, so the suite must reject it.
    """
    # The device tree in the sandbox has no vendor/ blobs; operate on the real
    # project so the check has something to inspect.
    proj = os.environ.get("EQUULEUS_PROJECT_ROOT") or ROOT
    target = None
    for tree in ("equuleus", "sdm845-common"):
        cand = os.path.join(proj, "vendor", "xiaomi", tree, "proprietary",
                            "vendor", "lib", "libmmcamera_faceproc.so")
        if os.path.isfile(cand):
            target = cand
            break
    assert target, "libmmcamera_faceproc.so not found to mutate"
    backup = target + ".mutbak"
    shutil.copy2(target, backup)
    try:
        with io.open(target, "rb") as fh:
            data = bytearray(fh.read())
        for off in (0x7FE0, 0x7FE2, 0x7FE4):
            data[off] = 3           # MIUI raw value
        with io.open(target, "wb") as fh:
            fh.write(bytes(data))
        _MUTATION_RESTORE.append((target, backup))
    except Exception:
        shutil.move(backup, target)
        raise


def _strip_device_verification_markers():
    """Remove every phrase that separates "present in source" from "verified
    on a device". Covers the variants the document actually uses."""
    import re as _re
    full = os.path.join(SANDBOX, "DEVICE_AUDIT.md")
    txt = io.open(full, encoding="utf-8").read()
    pattern = _re.compile(
        r"NOT VERIFIED ON DEVICE"
        r"|NOT VERIFIED"
        r"|not verified on (a )?device"
        r"|unverified"
        r"|Unverified",
        _re.IGNORECASE)
    out, n = pattern.subn("confirmed", txt)
    assert n > 0, "no verification markers found to strip"
    io.open(full, "w", encoding="utf-8", newline="\n").write(out)


def _strip_all_no_build_statements():
    """Remove every phrasing that admits nothing was compiled.

    The check accepts several forms, so a seed must remove ALL of them;
    otherwise the check correctly keeps passing and the mutation looks like
    a false MISS instead of a real finding.
    """
    import re as _re
    full = os.path.join(SANDBOX, "TEST_REPORT.md")
    txt = io.open(full, encoding="utf-8").read()
    # Chinese forms and English forms, each followed by an optional clause.
    cn_a = "\u672a\u7f16\u8bd1"          # 未编译
    cn_b = "\u6ca1\u6709\u7f16\u8bd1"    # 没有编译
    pattern = _re.compile(
        cn_a + r"[^\u3002\n]*\u3002?"
        + "|" + cn_b + r"[^\u3002\n]*\u3002?"
        + r"|no ROM was compiled"
        + r"|nothing was compiled"
        + r"|no ROM build was performed"
        + r"|no build was (?:performed|run|executed)"
        + r"|not executed",
        _re.IGNORECASE)
    stripped, n = pattern.subn("build completed successfully.", txt)
    assert n > 0, "no no-build statement found to strip"
    io.open(full, "w", encoding="utf-8", newline="\n").write(stripped)


def _erase_all_python_assignments():
    """Reproduce the original P0-1 defect: ${PYTHON} used with no assignment.

    Removing only the initialiser is not enough — the loop still does
    PYTHON="${cand}", which the check (correctly) treats as an assignment.
    """
    full = os.path.join(SANDBOX, "scripts", "sync.sh")
    lines = io.open(full, encoding="utf-8").read().splitlines()
    out = []
    for line in lines:
        if "PYTHON=" in line and "${PYTHON}" not in line:
            indent = line[:len(line) - len(line.lstrip())]
            out.append(indent + "# PYTHON assignment removed by mutation seed")
        else:
            out.append(line)
    io.open(full, "w", encoding="utf-8", newline="\n").write("\n".join(out))


def _move_python_use_before_assignment():
    """Seed the original P0-1 defect: reference ${PYTHON} before assigning it."""
    full = os.path.join(SANDBOX, "scripts", "sync.sh")
    lines = io.open(full, encoding="utf-8").read().splitlines()
    use_idx = next(i for i, l in enumerate(lines) if "${PYTHON}" in l)
    moved = lines.pop(use_idx)
    # put the use immediately after `set -euo pipefail`
    target = next(i for i, l in enumerate(lines) if l.startswith("set -e")) + 1
    lines.insert(target, moved)
    io.open(full, "w", encoding="utf-8", newline="\n").write("\n".join(lines))


def _break_retry_exit_code():
    """Seed the original P1-1 defect: read $? after the if/fi block."""
    full = os.path.join(SANDBOX, "scripts", "sync.sh")
    txt = io.open(full, encoding="utf-8").read()
    old = """    else
        rc=$?
    fi"""
    new = """    fi
    rc=$?"""
    assert old in txt, "retry else-block not found for mutation"
    io.open(full, "w", encoding="utf-8", newline="\n").write(txt.replace(old, new, 1))


MUTATIONS = [
    ("README.md deleted",
     "required documents exist",
     lambda: delete_file("README.md")),

    ("TEST_REPORT loses the 已执行但失败 bucket",
     "TEST_REPORT is honest about scope",
     lambda: replace_all("TEST_REPORT.md", "已执行但失败", "未运行")),

    ("TEST_REPORT drops every 'not compiled' statement",
     "TEST_REPORT is honest about scope",
     lambda: _strip_all_no_build_statements()),

    ("TEST_REPORT claims a successful build",
     "TEST_REPORT is honest about scope",
     lambda: append_to("TEST_REPORT.md", "\n\n结论：编译成功，ROM 可以刷机。\n")),

    ("KNOWN_BLOCKERS loses severity vocabulary",
     "KNOWN_BLOCKERS has severity/evidence/status",
     lambda: (replace_all("KNOWN_BLOCKERS.md", "Severity", "Weight"),
              replace_all("KNOWN_BLOCKERS.md", "severity", "weight"))),

    ("UPSTREAM_LOCK loses commit SHAs",
     "UPSTREAM_LOCK records commit SHAs",
     strip_all_shas),

    ("DEVICE_AUDIT never mentions FOD",
     "DEVICE_AUDIT covers FOD/Camera/NFC",
     lambda: replace_all("DEVICE_AUDIT.md", "FOD", "display")),

    ("DEVICE_AUDIT stops distinguishing device verification",
     "DEVICE_AUDIT covers FOD/Camera/NFC",
     # The document uses several verification-status phrasings; a seed must
     # remove ALL of them or the check correctly keeps passing.
     lambda: _strip_device_verification_markers()),

    # the check reads the *staged* tree (src + patches applied), so the defect
    # has to be seeded into the patch, not into work/
    ("BoardConfig reverts to vendor/lineage reserved-size file",
     "BoardConfig uses vendor/aosp equivalents",
     lambda: replace_all("patches/0003-sdm845-common-use-vendor-aosp.patch",
                         "+include vendor/aosp/config/BoardConfigReservedSize.mk",
                         "+include vendor/lineage/config/BoardConfigReservedSize.mk")),

    ("local manifest pins a branch instead of a SHA",
     "local manifest well-formed and SHA-pinned",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         'revision="db40750f063e86110e20db1455729c0f6621f7da"',
                         'revision="lineage-22.2"')),

    ("local manifest declares a conflicting PixelOS remote",
     "local manifest remotes do not conflict",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         'fetch="https://github.com/PixelOS-AOSP"',
                         'fetch="https://github.com/SomebodyElse"')),

    ("extend-project names a project that does not exist",
     "extend-project targets exist upstream",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         "LineageOS/android_hardware_lineage_interfaces",
                         "LineageOS/android_does_not_exist")),

    ("extend-project points at the wrong path",
     "extend-project targets exist upstream",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         'path="hardware/lineage/interfaces"',
                         'path="hardware/lineage/WRONG"')),

    ("extend-project uses a branch instead of a SHA",
     "extend-project targets exist upstream",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         'revision="3466aa530ace6de0760c12a68cf81b31e8d3807b"',
                         'revision="lineage-22.2"')),

    ("a project re-declares a platform-owned path",
     "local manifest does not collide with platform",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         '<project path="hardware/xiaomi"',
                         '<project path="frameworks/base"')),

    ("a patch no longer applies (removed line does not match)",
     "patches apply cleanly",
     lambda: replace_all("patches/0001-equuleus-product-setup.patch",
                         "-    $(LOCAL_DIR)/lineage_equuleus.mk",
                         "-    $(LOCAL_DIR)/something_else.mk")),

    ("the vendor/gms remove-project is dropped (P0-1)",
     "vendor/gms dependency resolved (P0-1)",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         '<remove-project name="vendor_gms" />', '')),

    ("vendor/gms points back at the sixteen-only repo (P0-1)",
     "vendor/gms dependency resolved (P0-1)",
     lambda: replace_all(".repo/local_manifests/equuleus.xml",
                         'name="vendor_gms-15"', 'name="vendor_gms"')),

    ("stage 1 starts inspecting the source tree (P0-3)",
     "preflight split into two stages (P0-3)",
     lambda: replace_all("scripts/host-preflight.sh",
                         'echo "--- 1. platform',
                         'ls vendor/xiaomi/equuleus\necho "--- 1. platform')),

    # The check is behavioural now: it runs Entry() and asserts src/dst/args.
    # Mutating the SEPARATORS constant alone no longer changes behaviour (the
    # regexes are compiled from literals), so the seed must break the parser.
    ("verify_blobs stops honouring the ':' destination remap (P0-2)",
     ["blob verifier honours dst/renames (P0-2)",
      "blob verifier fails on SONAME mismatch (P0-1)"],
     lambda: replace_all(
         "scripts/verify_blobs.py",
         "                if extra == self.src:\n"
         "                    self.dst, self.has_dst = self.src, False\n"
         "                else:\n"
         "                    self.dst, self.has_dst = extra, True",
         "                self.dst, self.has_dst = self.src, False")),

    ("verify_blobs stops parsing ';' arguments (P0-2)",
     "blob verifier honours dst/renames (P0-2)",
     lambda: replace_all(
         "scripts/verify_blobs.py",
         '            elif prefix == ";":\n'
         '                k, _, v = extra.partition("=")\n'
         '                self.args[k] = (v if v else True)',
         '            elif prefix == ";":\n'
         '                pass')),

    ("sync.sh stops capturing the revision lock (P0-4)",
     "manifest lock workflow present (P0-4)",
     lambda: replace_all("scripts/sync.sh", "repo manifest -r -o", "echo skipping ")),

    # ---- regressions for the independent review (round 5) ----
    ("sync.sh stops defining PYTHON anywhere (P0-1 regression)",
     "sync.sh defines PYTHON before use (P0-1)",
     lambda: _erase_all_python_assignments()),

    ("sync.sh moves ${PYTHON} use above its assignment (P0-1)",
     "sync.sh defines PYTHON before use (P0-1)",
     lambda: _move_python_use_before_assignment()),

    ("0005 is applied again on top of the local override (P0-2 regression)",
     "GMS overrides are mutually exclusive (P0-2)",
     lambda: replace_all(
         "scripts/sync.sh",
         'apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0001-equuleus-product-setup.patch"',
         'apply_patch .repo/manifests "${PROJECT_DIR}/patches/0005-manifest-gms-repo.patch" || true\n'
         'apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0001-equuleus-product-setup.patch"')),

    ("sync.sh reads $? after the if instead of in else (P1-1)",
     "sync retry records the real exit code (P1-1)",
     lambda: _break_retry_exit_code()),

    ("build.sh gates preflight on the execute bit again (P1-2)",
     "build gates are not skippable (P1-2/P1-4)",
     lambda: replace_all(
         "scripts/build.sh",
         '[[ -f "${SCRIPT_DIR}/build-preflight.sh" ]]',
         '[[ -x "${SCRIPT_DIR}/build-preflight.sh" ]]')),

    ("build.sh degrades a missing blob check to a warning (P1-4)",
     "build gates are not skippable (P1-2/P1-4)",
     lambda: replace_all(
         "scripts/build.sh",
         '[[ -n "${PY_BIN}" ]] || die 1 "no Python interpreter available for verify_blobs.py; refusing to build unverified blobs"',
         'echo "WARNING: cannot run verify_blobs.py (interpreter or script missing)"')),

    # ---- regressions for review round 6 ----
    ("verify_blobs exits 0 despite a SONAME mismatch (P0-1)",
     "blob verifier fails on SONAME mismatch (P0-1)",
     lambda: replace_all(
         "scripts/verify_blobs.py",
         '        rec.update(status=FAIL,\n                   reason=f"DT_SONAME',
         '        rec.update(status=OK,\n                   reason=f"DT_SONAME')),

    ("verify_blobs treats unverifiable hashes as OK (P0-1)",
     "blob hashes follow upstream semantics (P0-1)",
     lambda: replace_all(
         "scripts/verify_blobs.py",
         "                status=UNVERIFIABLE,\n                reason=\"only a pre-fixup hash is pinned, but a fixup ran\"",
         "                status=OK,\n                reason=\"only a pre-fixup hash is pinned, but a fixup ran\"")),

    ("build.sh stops passing --strict to verify_blobs (P0-1)",
     "build rejects failed blob verification (P0-1)",
     lambda: replace_all("scripts/build.sh", '"${TREE}" --strict', '"${TREE}"')),

    ("build.sh reverts to instructing patch 0005 (P1-1)",
     "GMS/0005 policy documented uniformly (P1-1)",
     lambda: replace_all(
         "scripts/build.sh",
         "The ONLY supported fix is the local manifest: confirm that",
         "Apply patches/0005-manifest-gms-repo.patch and re-sync. Confirm that")),

    ("--network-only stops guarding the resource sections (P1-2)",
     "--network-only skips resource checks (P1-2)",
     lambda: replace_all("scripts/host-preflight.sh",
                         "if (( ! NETWORK_ONLY )); then",
                         "if (( 1 )); then")),

    ("the blob test suite is dropped from the shipped scripts (P0-1)",
     "blob test suite is shipped",
     lambda: replace_all("scripts/make_audit_package.py",
                         '    "scripts/test_verify_blobs.py",\n', "")),

    # ---- regressions for review round 7 ----
    ("a document reintroduces a stale patch count (P2)",
     "docs match the real patch count (P2)",
     lambda: replace_all("CLOUD_READINESS.md",
                         "# ~1-2 h, 165 GiB, applies 0001-0004",
                         "# ~1-2 h, 165 GiB, applies 9 patches")),

    ("build.sh stops filtering artifacts by build time (P1)",
     "build artifacts are fresh and asserted (P1)",
     lambda: replace_all("scripts/build.sh",
                         "-newermt \"@${BUILD_STARTED_EPOCH}\" ", "")),

    ("build.sh downgrades the exact device check to a warning (P1)",
     "build artifacts are fresh and asserted (P1)",
     lambda: replace_all(
         "scripts/build.sh",
         'if [[ "${META_DEVICE}" != "${EXPECTED_DEVICE}" ]]; then',
         'if false; then  # downgraded: accept any device')),

    ("build-preflight goes back to probing .git with -d (P1)",
     "git checks avoid .git layout guessing (P1)",
     lambda: replace_all(
         "scripts/build-preflight.sh",
         'inside="$(git -C "${TREE}/${path}" rev-parse --is-inside-work-tree 2>/dev/null || true)"',
         'inside="$([[ -d "${TREE}/${path}/.git" ]] && echo true)"')),

    # ---- regressions for review round 8 ----
    ("recovery freshness re-adds the envsetup.sh comparison (P1-1)",
     "recovery freshness uses build marker only (P1-1)",
     lambda: replace_all(
         "scripts/build.sh",
         "if (( RECOVERY_MTIME < BUILD_STARTED_EPOCH )); then",
         'if [[ ! "${RECOVERY_IMG}" -nt "${TREE}/build/envsetup.sh" ]] && \\\n'
         "        [[ \"$(stat -c '%Y' \"${RECOVERY_IMG}\")' -lt \"${BUILD_STARTED_EPOCH}\" ]]; then")),

    ("device assertion falls back to the substring regex (P1-2)",
     "device assertion is exact, not substring (P1-2)",
     lambda: replace_all(
         "scripts/build.sh",
         'if [[ "${META_DEVICE}" != "${EXPECTED_DEVICE}" ]]; then',
         'if ! printf \'%s\\n\' "${META}" | grep -qE \'assert.*equuleus\'; then')),

    ("a round-8 regression case is deleted (P1-3)",
     "artifact suite covers round-8 regressions (P1-3)",
     lambda: replace_all(
         "scripts/test_build_artifacts.py",
         '    ("fresh zip + STALE recovery -> reject", "seed_stale_recovery_fresh_zip", False),\n', "")),

    ("the blob source record contradicts the disk (B-01)",
     "blob source recorded and honest (B-01)",
     lambda: replace_all("blob_sources.json",
                         '"vendor_equuleus_generated": true',
                         '"vendor_equuleus_generated": false')),

    ("the blob source record hides a verification failure (B-01)",
     "blob source recorded and honest (B-01)",
     lambda: replace_all("blob_sources.json",
                         '"strict_verification_fail": 0',
                         '"strict_verification_fail": 3')),

    # ---- regressions for review round 12 ----
    ("sync.sh drops patch 0007 (IR camera id) (P0-1)",
     "docs match the real patch count (P2)",
     lambda: replace_all(
         "scripts/sync.sh",
         'apply_patch device/xiaomi/equuleus      "${PROJECT_DIR}/patches/0007-equuleus-ir-face-unlock-camera-id.patch"\n',
         "")),

    ("sync.sh starts applying the archived 0005 again (P0-1)",
     ["GMS overrides are mutually exclusive (P0-2)",
      "pipeline enforces the full 7-patch set (P0/P1)"],
     lambda: replace_all(
         "scripts/sync.sh",
         '# Patches 0001-0004: PixelOS product/branding/build-policy adaptation.',
         'apply_patch .repo/manifests "${PROJECT_DIR}/patches/0005-manifest-gms-repo.patch" || true\n'
         '# Patches 0001-0004: PixelOS product/branding/build-policy adaptation.')),

    ("build-preflight stops verifying patch 0008 (P0-2)",
     "pipeline enforces the full 7-patch set (P0/P1)",
     lambda: replace_all(
         "scripts/build-preflight.sh",
         'patch_state device/xiaomi/sdm845-common  "${PROJECT_DIR}/patches/0008-sdm845-common-ir-face-unlock-aux-camera.patch"\n',
         "")),

    ("build.sh stops gating on IR acceptance (P1-2)",
     "pipeline enforces the full 7-patch set (P0/P1)",
     lambda: replace_all(
         "scripts/build.sh",
         'if "${PY_BIN}" "${SCRIPT_DIR}/verify_ir_face_unlock.py" --root "${TREE}"; then',
         'if true; then')),

    ("IR checker stops reading the real device tree (P1-1)",
     ["pipeline enforces the full 7-patch set (P0/P1)", "IR face unlock configured (round 11)"],
     lambda: replace_all(
         "scripts/verify_ir_face_unlock.py",
         'assert re.search(r"^ro\\.face\\.sense_service\\.camera_id=\\d+",',
         'assert True or re.search(r"^ro\\.face\\.sense_service\\.camera_id=\\d+",')),

    ("the vendor transfer doc is deleted (P1-4)",
     "required documents exist",
     lambda: delete_file("VENDOR_TRANSFER.md")),

    # ---- regressions for round 13 (MIUI IR comparison) ----
    ("the faceproc symbol-version fixup is reverted to MIUI bytes (round 13)",
     "MIUI IR analysis backed by real bytes (round 13)",
     lambda: _revert_faceproc_fixup()),

    ("a MIUI analysis document is deleted (round 13)",
     "MIUI IR analysis backed by real bytes (round 13)",
     lambda: delete_file("MIUI_VS_LINEAGE_IR_DIFF.md")),

    # ---- regressions for review round 15 (P0 first-build path) ----
    ("receive falls back to SKIP when the verifier is absent (round 15 P0)",
     "receive cannot fake BUILD READY (P0)",
     lambda: replace_all(
         "scripts/cloud_vendor_transfer.sh",
         'VERIFIER="${SCRIPT_DIR}/verify_blobs.py"',
         'VERIFIER="${TREE}/scripts/verify_blobs.py"')),

    ("receive stops cross-checking the verifier JSON report (round 15 P0)",
     "receive cannot fake BUILD READY (P0)",
     lambda: replace_all(
         "scripts/cloud_vendor_transfer.sh",
         'blob-report.json',
         'blob-report-unused.json')),

    ("the runbook drops --tree from host-preflight (round 15 P0)",
     "runbook first-build steps correct (P0)",
     lambda: replace_all(
         "FIRST_BUILD_RUNBOOK.md",
         "bash /opt/port/scripts/host-preflight.sh --tree /data/pixelos15",
         "bash /opt/port/scripts/host-preflight.sh")),

    ("the runbook reintroduces a manual repo sync (round 15 P0)",
     "runbook first-build steps correct (P0)",
     lambda: append_to(
         "FIRST_BUILD_RUNBOOK.md",
         "\n```bash\nrepo sync -c -j8\n```\n")),

    ("upload reverts to a glob over volumes (round 15 P0)",
     "upload ships the complete file set (P0)",
     lambda: replace_all(
         "scripts/cloud_vendor_transfer.sh",
         'mapfile -t FILES < <(',
         'mapfile -t FILES < <(true; echo')),

    ("the OTA digest is printed but not compared (round 15 P1)",
     "OTA digest is compared, not printed (P1)",
     lambda: replace_all(
         "scripts/extract_vendor_full.sh",
         "if actual != expected:",
         "if False:")),

    ("a patch loses its Subject header",
     "patches carry mail headers",
     lambda: replace_all("patches/0003-sdm845-common-use-vendor-aosp.patch",
                         "Subject:", "Topic:")),

    ("the product rename is dropped from patch 0001",
     "product naming switched to aosp_equuleus",
     lambda: replace_all("patches/0001-equuleus-product-setup.patch",
                         "PRODUCT_NAME := aosp_equuleus",
                         "PRODUCT_NAME := lineage_equuleus")),

    ("a script drops set -e",
     "scripts are fail-fast and log",
     lambda: replace_all("scripts/build.sh", "set -euo pipefail", "set -u")),

    ("a script becomes syntactically invalid",
     "scripts pass bash -n",
     lambda: replace_all("scripts/sync.sh", 'step "preconditions"',
                         'step "preconditions" )))\nfi')),

    ("a forbidden command is introduced",
     "no forbidden destructive commands",
     lambda: replace_all("scripts/build.sh", 'step "preconditions"', BANNED_CMD)),

    ("a credential is introduced",
     "no credential-shaped strings",
     lambda: replace_all("scripts/sync.sh", 'TREE="${1:-}"',
                         'TREE="${1:-}"\n' + FAKE_TOKEN)),

    ("a script loses its shebang",
     "scripts present and executable",
     lambda: replace_all("scripts/preflight.sh", "#!/usr/bin/env bash", "")),
]


def main():
    reset()
    fails, rc, out, err, skipped = run_verifier()
    if fails or rc != 0:
        print("BASELINE NOT GREEN: %s\n%s" % (sorted(fails), err), file=sys.stderr)
        return 1
    print("baseline: 19/19 green\n")

    caught, missed, skipped_mut = [], [], []
    for label, expected, seed in MUTATIONS:
        reset()
        try:
            seed()
        except AssertionError as exc:
            missed.append((label, "could not seed: %s" % exc))
            print("  [SEED-FAIL] %s: %s" % (label, exc))
            continue
        fails, rc, out, err, skipped = run_verifier()
        # seeds may have mutated files outside the sandbox (real vendor blobs);
        # restore them before judging the next mutation, or later seeds run
        # against an already-corrupted tree.
        _restore_outside_mutations()
        # `expected` may be a single check name or a list of acceptable ones:
        # one seeded defect can legitimately trip more than one check.
        expects = ([expected] if isinstance(expected, str) else list(expected))
        hit = next((e for e in expects if e in fails), None)
        if hit:
            caught.append(label)
            print("  [CAUGHT] %s  ->  %s" % (label, hit))
        elif any(e in skipped for e in expects):
            # The check itself could not run (upstream source/clones absent).
            # Counting this as a MISS would be a false negative.
            skipped_mut.append((label, expected))
            print("  [SKIP]   %s  ->  %s (check skipped: no upstream evidence)"
                  % (label, expected))
        else:
            missed.append((label, "expected %r, actual %s" % (expected, sorted(fails))))
            print("  [MISSED] %s\n           expected %r, got %s"
                  % (label, expected, sorted(fails)))

    total_judged = len(caught) + len(missed)
    print("\n%d/%d judged mutations caught" % (len(caught), total_judged))
    if skipped_mut:
        print("%d mutation(s) skipped: their check needs upstream evidence."
              % len(skipped_mut))
    if missed:
        print("\nPROBLEMS:")
        for label, why in missed:
            print("  - %s: %s" % (label, why))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
