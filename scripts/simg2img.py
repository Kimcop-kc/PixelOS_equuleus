#!/usr/bin/env python3
"""simg2img.py — convert an Android sparse image to a raw image.

MIUI fastboot packages ship `vendor.img` etc. as Android sparse images
(magic 0xED26FF3A). `debugfs` cannot read those, so they must be unsparsed
first. This is a minimal, dependency-free implementation of the format:

    header (28 bytes):
        magic        u32  0xED26FF3A
        major, minor u16  (1, 0)
        file_hdr_sz  u16  28
        chunk_hdr_sz u16  12
        blk_sz       u32  usually 4096
        total_blks   u32
        total_chunks u32
        checksum     u32

    chunk header (12 bytes):
        type   u16  (0xCAC1 raw, 0xCAC2 fill, 0xCAC3 don't-care, 0xCAC4 crc32)
        reserved u16
        chunk_sz u32  in blocks
        total_sz u32  in bytes, including the 12-byte header

Chunks longer than `chunk_hdr_sz` are skipped by that difference.

Usage: python3 simg2img.py <sparse.img> <raw.img>
Exit:  0 = converted, 1 = not sparse / malformed, 2 = usage.
"""
from __future__ import annotations

import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


def is_sparse(path: str) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(4)
    return len(head) == 4 and struct.unpack("<I", head)[0] == SPARSE_MAGIC


def convert(src: str, dst: str) -> dict:
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        hdr = fin.read(28)
        if len(hdr) < 28:
            raise ValueError("file too small for a sparse header")
        (magic, major, _minor, file_hdr_sz, chunk_hdr_sz,
         blk_sz, total_blks, total_chunks, _cksum) = struct.unpack("<IHHHHIIII", hdr)
        if magic != SPARSE_MAGIC:
            raise ValueError("not a sparse image (bad magic)")
        if major != 1:
            raise ValueError(f"unsupported sparse major version {major}")

        # skip any extra header bytes beyond the declared size
        if file_hdr_sz > 28:
            fin.seek(file_hdr_sz)
        elif file_hdr_sz < 28:
            raise ValueError(f"implausible file_hdr_sz {file_hdr_sz}")

        written = 0
        stats = {CHUNK_RAW: 0, CHUNK_FILL: 0, CHUNK_DONT_CARE: 0, CHUNK_CRC32: 0}

        for _ in range(total_chunks):
            ch = fin.read(12)
            if len(ch) < 12:
                raise ValueError("truncated chunk header")
            ctype, _res, chunk_sz, total_sz = struct.unpack("<HHII", ch)
            if total_sz < 12:
                raise ValueError(f"chunk total_sz {total_sz} < 12")
            extra = total_sz - 12
            payload_expected = chunk_sz * blk_sz

            if ctype == CHUNK_RAW:
                remaining = payload_expected
                while remaining:
                    buf = fin.read(min(1 << 20, remaining))
                    if not buf:
                        raise ValueError("truncated raw chunk payload")
                    fout.write(buf)
                    remaining -= len(buf)
                written += payload_expected
                stats[CHUNK_RAW] += 1
                # consume any padding declared but beyond the payload
                pad = extra - payload_expected
                if pad > 0:
                    fin.seek(pad, 1)
            elif ctype == CHUNK_FILL:
                if extra < 4:
                    raise ValueError("fill chunk missing its 4-byte pattern")
                pattern = fin.read(4)
                pad = extra - 4
                if pad > 0:
                    fin.seek(pad, 1)
                fout.write(pattern * (payload_expected // 4))
                written += payload_expected
                stats[CHUNK_FILL] += 1
            elif ctype == CHUNK_DONT_CARE:
                fout.write(b"\x00" * payload_expected)
                written += payload_expected
                stats[CHUNK_DONT_CARE] += 1
                if extra > 0:
                    fin.seek(extra, 1)
            elif ctype == CHUNK_CRC32:
                if extra > 0:
                    fin.seek(extra, 1)
                stats[CHUNK_CRC32] += 1
            else:
                raise ValueError(f"unknown chunk type 0x{ctype:04X}")

        # the image must be exactly total_blks blocks
        expected = total_blks * blk_sz
        if written != expected:
            raise ValueError(
                f"size mismatch: wrote {written} bytes, header says {expected}")

        stats.update(block_size=blk_sz, total_blocks=total_blks,
                     total_chunks=total_chunks, bytes_written=written)
        return stats


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: simg2img.py <sparse.img> <raw.img>", file=sys.stderr)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    if not is_sparse(src):
        print(f"FATAL: {src} is not an Android sparse image", file=sys.stderr)
        return 1
    try:
        st = convert(src, dst)
    except (ValueError, OSError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    print(f"  blocks      : {st['total_blocks']:,} x {st['block_size']} = "
          f"{st['bytes_written']:,} bytes")
    print(f"  chunks      : raw={st[CHUNK_RAW]} fill={st[CHUNK_FILL]} "
          f"dontcare={st[CHUNK_DONT_CARE]} crc32={st[CHUNK_CRC32]}")
    print(f"  wrote       : {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
