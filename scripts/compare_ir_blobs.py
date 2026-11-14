#!/usr/bin/env python3
"""compare_ir_blobs.py — diff MIUI vs LineageOS IR-related blobs.

Purpose: decide, with evidence, whether PixelOS/ParanoidSense can reuse the
OV9282 drivers already extracted from LineageOS, or whether an MIUI component
must be added. Guessing here risks a build that compiles and then cannot drive
the IR camera.

For every file in the interest set it reports:
  * presence in each tree
  * SHA256 (so "identical" is byte-exact, not "same filename")
  * size
  * ELF class / machine (32 vs 64-bit, AArch64)
  * DT_SONAME and DT_NEEDED for ELF files

Usage:
    python3 compare_ir_blobs.py <miui_vendor_dump> <lineage_vendor_root> [--json out]

<lineage_vendor_root> is the tree containing vendor/xiaomi/{equuleus,sdm845-common}/proprietary.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

# The files that matter for IR face unlock, expressed as MIUI-vendor-relative
# paths. LineageOS stores them under vendor/xiaomi/equuleus/proprietary/vendor/...
INTEREST = [
    "lib/camera/com.qti.sensor.ov9282.so",
    "lib/camera/com.qti.sensormodule.ov9282.bin",
    "lib/camera/com.qti.tuned.ofilm_ov9282.bin",
    "lib/camera/com.qti.sensor.imx363.so",
    "lib/camera/com.qti.sensor.s5k3m3.so",
    "lib/camera/com.qti.sensor.s5k3t1.so",
    "lib/hw/camera.qcom.so",
    "lib64/hw/camera.qcom.so",
    "lib/libcamxfdengine.so",
    "lib64/libcamxfdengine.so",
    "lib/libcamxfdalgov7.so",
    "lib64/libcamxfdalgov7.so",
    "lib/libmmcamera_faceproc.so",
    "lib64/libmmcamera_faceproc.so",
    "etc/camera/camxoverridesettings.txt",
    "etc/camera/ov9282.bin",
    "bin/hw/android.hardware.camera.provider@2.4-service",
    "bin/hw/vendor.qti.hardware.camera.provider@1.0-service",
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def elf_info(path: str) -> dict:
    """Return {'class':..., 'machine':..., 'soname':..., 'needed':[...]} or {}."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return {}
    if len(data) < 0x40 or data[:4] != b"\x7fELF":
        return {"kind": "not-elf"}
    cls = {1: "ELF32", 2: "ELF64"}.get(data[4], "?")
    machine = int.from_bytes(data[18:20], "little")
    endian = "<" if data[5] == 1 else ">"
    info = {"kind": "elf", "class": cls, "machine": machine}
    try:
        if data[4] == 2:
            shoff, = struct.unpack_from(endian + "Q", data, 0x28)
            shentsize, shnum = struct.unpack_from(endian + "HH", data, 0x3A)
            shstrndx, = struct.unpack_from(endian + "H", data, 0x3E)
            sh_fmt, dyn_fmt = endian + "IIQQQQIIQQ", endian + "qQ"
        else:
            shoff, = struct.unpack_from(endian + "I", data, 0x20)
            shentsize, shnum = struct.unpack_from(endian + "HH", data, 0x2E)
            shstrndx, = struct.unpack_from(endian + "H", data, 0x32)
            sh_fmt, dyn_fmt = endian + "IIIIIIIIII", endian + "iI"
        secs = [struct.unpack_from(sh_fmt, data, shoff + i * shentsize)
                for i in range(shnum)]
        shstr_off = secs[shstrndx][4]

        def sname(i):
            st = secs[i][0]
            e = data.find(b"\x00", shstr_off + st)
            return data[shstr_off + st:e].decode("ascii", "replace")

        for i, sec in enumerate(secs):
            if sname(i) != ".dynamic":
                continue
            doff, dsize = sec[4], sec[5]
            entsize = struct.calcsize(dyn_fmt)
            tags = []
            for pos in range(doff, min(doff + dsize, len(data)), entsize):
                tags.append(struct.unpack_from(dyn_fmt, data, pos))
            strtab = None
            needed, soname = [], None
            for tag, val in tags:
                if tag == 0:
                    break
                if tag == 5:
                    strtab = val
                elif tag == 1:
                    needed.append(val)
                elif tag == 14:
                    soname = val
            if strtab is None:
                break
            # vaddr -> file offset
            off = None
            for s2 in secs:
                if s2[3] and s2[3] <= strtab < s2[3] + s2[5]:
                    off = s2[4] + (strtab - s2[3])
                    break
            if off is None:
                break

            def rd(rel):
                st = off + rel
                e = data.find(b"\x00", st)
                return data[st:e].decode("ascii", "replace") if e > 0 else ""

            info["needed"] = [rd(r) for r in needed]
            info["soname"] = rd(soname) if soname is not None else None
            break
    except (struct.error, IndexError):
        pass
    return info


def lineage_path(root: str, rel: str) -> str | None:
    """Map a MIUI vendor-relative path into the LineageOS vendor layout."""
    for tree in ("equuleus", "sdm845-common"):
        cand = os.path.join(root, "vendor", "xiaomi", tree, "proprietary",
                            "vendor", rel)
        if os.path.isfile(cand):
            return cand
    return None


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    miui = os.path.abspath(sys.argv[1])
    los = os.path.abspath(sys.argv[2])
    out_json = None
    if "--json" in sys.argv:
        out_json = sys.argv[sys.argv.index("--json") + 1]

    rows = []
    for rel in INTEREST:
        m = os.path.join(miui, rel)
        l = lineage_path(los, rel)
        row = {
            "rel": rel,
            "miui": None,
            "lineage": None,
            "verdict": None,
        }
        if os.path.isfile(m):
            row["miui"] = {
                "sha256": sha256(m),
                "size": os.path.getsize(m),
                **elf_info(m),
            }
        if l:
            row["lineage"] = {
                "path": os.path.relpath(l, los).replace(os.sep, "/"),
                "sha256": sha256(l),
                "size": os.path.getsize(l),
                **elf_info(l),
            }

        if row["miui"] and row["lineage"]:
            if row["miui"]["sha256"] == row["lineage"]["sha256"]:
                row["verdict"] = "IDENTICAL"
            else:
                row["verdict"] = "DIFFERS"
        elif row["miui"]:
            row["verdict"] = "MIUI-ONLY"
        elif row["lineage"]:
            row["verdict"] = "LINEAGE-ONLY"
        else:
            row["verdict"] = "ABSENT-BOTH"
        rows.append(row)

    width = max(len(r["rel"]) for r in rows) + 2
    print("%-*s %-14s %-12s %s" % (width, "file", "verdict", "size(m/l)", "note"))
    print("-" * (width + 50))
    for r in rows:
        m, l = r["miui"], r["lineage"]
        if r["verdict"] == "IDENTICAL":
            note = "byte-identical: reuse LineageOS copy"
        elif r["verdict"] == "DIFFERS":
            note = "same path, different bytes - inspect before reuse"
        elif r["verdict"] == "MIUI-ONLY":
            note = "not present in LineageOS extraction"
        elif r["verdict"] == "LINEAGE-ONLY":
            note = "LineageOS provides it; MIUI does not (or path differs)"
        else:
            note = "-"
        sizes = "%s/%s" % (m["size"] if m else "-", l["size"] if l else "-")
        print("%-*s %-14s %-12s %s" % (width, r["rel"], r["verdict"], sizes, note))

    # ------------------------------------------------------------- summary
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print()
    print("summary:", ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))

    identical = [r["rel"] for r in rows if r["verdict"] == "IDENTICAL"]
    differing = [r["rel"] for r in rows if r["verdict"] == "DIFFERS"]
    miui_only = [r["rel"] for r in rows if r["verdict"] == "MIUI-ONLY"]
    print()
    if identical:
        print("reusable as-is (byte-identical):")
        for x in identical:
            print("   ", x)
    if differing:
        print("needs inspection (bytes differ):")
        for x in differing:
            print("   ", x)
    if miui_only:
        print("MIUI-only, candidate additions:")
        for x in miui_only:
            print("   ", x)

    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump({"miui": miui, "lineage": los, "rows": rows,
                       "summary": counts}, fh, indent=2)
        print("\njson:", out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
