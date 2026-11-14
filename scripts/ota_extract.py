#!/usr/bin/env python3
"""ota_extract.py — materialise a LineageOS block-OTA into plain ext4 images.

Half one of the B-01 extraction: turn the OTA's block data into readable
partition images, without root and without touching the original archive.

Format handled (observed in lineage-22.2-*-equuleus-signed.zip):

    <part>.new.dat.br      brotli-compressed block data
    <part>.transfer.list   Android "transfer list"

The transfer list is the **command form** used by Android 10+ (what
`sdat2img` calls version 4), e.g.

    4
    161531            # total blocks to write
    0                 # blocks in "new" groups that were skipped
    0
    new 2,0,1024      # op 2 = "new", then destination block ranges
    new 2,1024,2048
    erase 4,242609,261632,262657,265386

Semantics: after the integer header lines, each remaining line is
`<op> <dst-block>[,<dst-block>...]`. The op index selects an entry from the
previously read command groups. For an op of type "new", the source data is
consumed **sequentially** in dst-block order, one 4096-byte block per listed
destination. This sequencing is the part that is easy to get wrong.

New-style `payload.bin` OTAs are rejected explicitly: they need update_engine's
protobuf payload reader, and mis-parsing would silently produce garbage.

Usage:
    python3 ota_extract.py <ota.zip> <outdir> [--parts vendor,product,...]

Exit codes: 0 = all requested partitions produced, 1 = a partition failed,
            2 = usage / unsupported format, 3 = everything absent.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

BLOCK = 4096


def parse_transfer_list(text: str):
    """Parse an Android v4 command-form transfer list.

    Layout verified against vendor.transfer.list in the equuleus OTA:

        4                 <- version
        161531            <- total destination blocks to write
        0
        0
        new 2,0,1024      <- kind, op-index, then half-open dst ranges
        new 2,1024,2048
        ...
        new 2,160768,161531

    The ranges sum to exactly the value on line 1 (161531), which confirms the
    reading: after the kind, the numbers are `<op>[,<start>,<end>]...` where each
    (start, end) pair is a half-open destination block range. Source data for
    "new" commands is consumed sequentially in destination order.

    Returns (version, commands) where commands is [(kind, [(start,end),...])].
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("empty transfer list")

    version = int(lines[0])
    if version != 4:
        raise ValueError(
            f"transfer-list version {version} is not the command form this tool "
            "implements (only v4 is supported)")

    ints = []
    idx = 1
    while idx < len(lines) and lines[idx].isdigit():
        ints.append(int(lines[idx]))
        idx += 1
    if not ints:
        raise ValueError("transfer list has no integer header")
    total_blocks = ints[0]

    commands = []
    for line in lines[idx:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        kind = parts[0]
        if kind not in ("new", "erase", "zero", "filler"):
            raise ValueError(f"unexpected command kind {kind!r} in transfer list")
        numbers = []
        for token in parts[1].split(","):
            token = token.strip()
            if token:
                numbers.append(int(token))
        if len(numbers) < 3 or len(numbers) % 2 != 1:
            raise ValueError(f"malformed range list on line: {line!r}")
        # numbers[0] is the op index; the rest are (start, end) pairs
        pairs = list(zip(numbers[1::2], numbers[2::2]))
        commands.append((kind, pairs))

    # Header line 1 is the number of blocks the writer EXPECTS to place, which
    # includes zero-fill from `erase` commands. It therefore does NOT equal the
    # amount of source data, and must not be used as an integrity check.
    #
    # The trustworthy invariant is: blocks covered by "new" ranges == blocks
    # present in <part>.new.dat. Verified on all five partitions of this OTA
    # (product 128136, system_ext 104076, system 242820, vendor 161531,
    # odm 375 — each exactly equal to dat_size/4096). That check lives in
    # build_image(), where the .dat size is known.
    return version, commands


def decompress_br(src: str, dst: str) -> None:
    try:
        import brotli  # type: ignore
    except ImportError:
        exe = shutil.which("brotli")
        if not exe:
            raise RuntimeError(
                "neither the 'brotli' Python module nor the brotli CLI is available")
        r = subprocess.run([exe, "-d", "-f", "-o", dst, src],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"brotli CLI failed: {r.stderr.strip()[:200]}")
        return
    with open(src, "rb") as fh:
        data = brotli.decompress(fh.read())
    with open(dst, "wb") as fh:
        fh.write(data)


def build_image(new_dat: str, transfer_list: str, img_path: str) -> dict:
    with open(transfer_list, encoding="utf-8") as fh:
        version, commands = parse_transfer_list(fh.read())

    max_block = 0
    for _kind, pairs in commands:
        for _s, e in pairs:
            max_block = max(max_block, e)
    size = max_block * BLOCK

    written = left_zero = 0
    with open(new_dat, "rb") as src, open(img_path, "wb") as out:
        out.truncate(size)
        for kind, pairs in commands:
            if kind != "new":
                # zero / erase / filler: destination blocks stay zero-filled
                left_zero += sum(e - s for s, e in pairs)
                continue
            for start, end in pairs:
                for dst in range(start, end):
                    chunk = src.read(BLOCK)
                    if len(chunk) < BLOCK:
                        chunk = chunk + b"\x00" * (BLOCK - len(chunk))
                    out.seek(dst * BLOCK)
                    out.write(chunk)
                    written += 1

    consumed = os.path.getsize(new_dat)
    if consumed != written * BLOCK:
        raise ValueError(
            f"source/spec mismatch: {written} 'new' blocks need "
            f"{written * BLOCK} bytes but {new_dat} is {consumed} bytes")
    return {
        "transfer_list_version": version,
        "commands": len(commands),
        "blocks_written": written,
        "blocks_left_zero": left_zero,
        "source_dat_bytes": consumed,
        "expected_dat_bytes": written * BLOCK,
        "source_fully_consumed": consumed == written * BLOCK,
        "size_bytes": os.path.getsize(img_path),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ota")
    ap.add_argument("outdir")
    ap.add_argument("--parts", default="vendor,product,system,system_ext,odm")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    ota = os.path.abspath(args.ota)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    if not os.path.isfile(ota):
        print(f"FATAL: no such OTA: {ota}", file=sys.stderr)
        return 2

    report = {"ota": ota, "outdir": outdir, "partitions": {}, "ok": True}

    with zipfile.ZipFile(ota) as zf:
        names = set(zf.namelist())
        if "payload.bin" in names:
            print("FATAL: payload.bin (update_engine) OTA — unsupported by this tool.",
                  file=sys.stderr)
            return 2

        for part in [p.strip() for p in args.parts.split(",") if p.strip()]:
            br = f"{part}.new.dat.br"
            tl = f"{part}.transfer.list"
            if br not in names or tl not in names:
                print(f"  [skip] {part}: absent from this OTA")
                report["partitions"][part] = {"status": "absent"}
                continue

            print(f"  [{part}] extracting …", flush=True)
            br_path = os.path.join(outdir, br)
            dat_path = os.path.join(outdir, f"{part}.new.dat")
            tl_path = os.path.join(outdir, tl)
            img_path = os.path.join(outdir, f"{part}.img")

            with zf.open(br) as src, open(br_path, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 22)
            with zf.open(tl) as src, open(tl_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

            try:
                decompress_br(br_path, dat_path)
                info = build_image(dat_path, tl_path, img_path)
                info["status"] = "ok"
                print(f"  [{part}] {info['size_bytes']:,} bytes, "
                      f"{info['blocks_written']:,} blocks written, "
                      f"{info['blocks_left_zero']:,} left zero")
            except Exception as exc:                        # noqa: BLE001
                info = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                report["ok"] = False
                print(f"  [{part}] FAILED: {info['error']}", file=sys.stderr)
            report["partitions"][part] = info

            for tmp in (dat_path, br_path):
                if os.path.exists(tmp):
                    os.remove(tmp)

    js = args.json or os.path.join(outdir, "ota_extract_report.json")
    with open(js, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nreport: {js}")

    if not report["ok"]:
        return 1
    if all(v.get("status") == "absent" for v in report["partitions"].values()):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
