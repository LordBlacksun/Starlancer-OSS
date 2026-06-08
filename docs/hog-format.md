# Starlancer `.HOG` archive format

Starlancer's `.HOG` files are **Electronic Arts `BIGF` archives**. Despite the
`.HOG` extension, the container is EA's BIG format (magic `BIGF`). Storage is
**uncompressed**; all multi-byte integers are **big-endian**.

*Reverse-engineered from the source of SLExtract (DraconPern & KingLord).*

## Layout

```
Off   Size  Field
0x00   4    magic = "BIGF" (ASCII)
0x04   4    archive_size  (uint32, big-endian) — total .hog size in bytes
0x08   4    num_files     (uint32, big-endian)
0x0C   4    data_start    (uint32, big-endian) — offset where file data begins
                          (= size of header + table-of-contents)
0x10   ..   Table of contents — num_files entries, packed back-to-back:
              4    offset  (uint32, big-endian) — ABSOLUTE offset of the blob
              4    length  (uint32, big-endian) — blob size in bytes
              n+1  name    (ASCII, NUL-terminated, variable length)
       ..   File data — raw, uncompressed blobs at their offsets.
```

## Parse / extract algorithm

1. Read 4 bytes; reject if not `BIGF`.
2. Read three big-endian `uint32`: `archive_size`, `num_files`, `data_start`.
3. Read `num_files` TOC entries — each is a big-endian `uint32` offset, a
   big-endian `uint32` length, then a NUL-terminated ASCII filename.
4. To extract entry *i*: copy `length[i]` bytes from absolute `offset[i]`.
   There is **no decompression**.

> **Endianness gotcha:** in the original SLExtract source the integer-reading
> helper is named `le()`, but it actually reads **big-endian**
> (`s[0]<<24 | s[1]<<16 | s[2]<<8 | s[3]`). The name is a red herring — `BIGF`
> archives are big-endian (vs. the little-endian `BIG4` / `C0FB` variants).

## Contents observed in Starlancer HOGs

- Archives are **per-CD**: `cd1.hog`, `cd2.hog` (the game shipped on two discs).
- Inner file types:
  - `.bik` — Bink video (magic `BIK`; frames @ off 16, width @ 20, height @ 24)
  - `.tga` — Targa (a nonstandard variant)
  - `.mp3` — audio
  - `.fat` — RIFF/WAVE-like audio, unknown subtype
  - `.spr` — sprites
  - `.shp` — 3D ship models
  - indexed startup images such as `00000409.016` (GIF) / `00000409.256` (BMP)

See [`tools/hog_extract.py`](../tools/hog_extract.py) for a reference implementation.
