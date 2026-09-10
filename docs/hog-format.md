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
4. To extract entry *i*: copy `length[i]` bytes from absolute `offset[i]`. The
   container itself applies **no compression** — but see the next section, because
   most of the blobs you get back are compressed *payloads*.

> **Endianness gotcha:** in the original SLExtract source the integer-reading
> helper is named `le()`, but it actually reads **big-endian**
> (`s[0]<<24 | s[1]<<16 | s[2]<<8 | s[3]`). The name is a red herring — `BIGF`
> archives are big-endian (vs. the little-endian `BIG4` / `C0FB` variants).

## The payload layer: most members are RefPack streams

The container stores raw blobs, but that is not the same as storing usable files.
**98% of `resource.hog`'s members are EA RefPack ("QFS") streams**, recognisable
by the two-byte `10 FB` signature. Extract one verbatim and you get a compressed
file, not a model or a mission.

A census of a retail install, by archive:

| archive | members | RefPack payloads |
|---|---:|---:|
| `resource.hog` | 967 | 950 (98%) |
| `CD1.HOG` | 225 | 18 (8%) |
| `CD2.HOG` | 174 | 0 |
| `pilots/pilots.hog` | 258 | 0 |
| `ms_speech/msspeech.hog` | 4369 | 0 |

The split is by role, not by archive: the asset archive is compressed almost
end-to-end, while the streaming-media archives (Bink video, MP3, speech banks)
are stored plain because they are already compressed formats. By extension,
across all five archives:

| extension | members | RefPack | stored | expands to | ratio |
|---|---:|---:|---:|---:|---:|
| `.shp` (models) | 440 | 440 | 14,946,926 | 38,097,004 | 2.55× |
| `.spr` (sprites) | 339 | 287 | 30,926,871 | 44,576,100 | 1.44× |
| `.tga` (textures) | 148 | 146 | 18,830,822 | 44,798,002 | 2.38× |
| `.dte` (missions) | 44 | 44 | 1,628,754 | 35,732,624 | 21.94× |
| `.fat` (audio) | 40 | 19 | 5,340,762 | 5,920,424 | 1.11× |
| `.fnt` (fonts) | 19 | 19 | 104,845 | 490,015 | 4.67× |
| `.ccb` (palettes) | 5 | 5 | 162,345 | 1,330,080 | 8.19× |
| `.bin` (stats tables) | 5 | 5 | 6,779 | 144,880 | 21.37× |
| `.bik` `.mp3` `.box` `.fm8` | 4917 | 0 | — | — | — |
| **total** | **5993** | **968** | **71,969,985** | **171,569,624** | **2.38×** |

Note that `resource.hog` carries its own copy of `shipstats.bin`,
`gunstats.bin`, `missilestats.bin` and `pilotstats.bin`, decompressing to exactly
256, 15, 16 and 124 records of 352 bytes — matching the loose installed files
byte-for-byte on a clean install (see [`stats-format.md`](stats-format.md)). The
archived copies are therefore a **pristine baseline**: useful for verifying or
restoring a modded install.

The codec is documented and implemented in [`tools/refpack.py`](../tools/refpack.py),
a port of the game's own `DecompressRefPackBlock` at `0x4CC350`. Two details bite:

- The header's flags byte selects a 3- or 4-byte uncompressed size and an optional
  compressed-size field. Assuming a fixed 5-byte header works on Starlancer's
  streams but is not the general format.
- A stream ends with a `0xFC..0xFF` opcode carrying 0–3 trailing literals, which
  may leave fewer than four bytes in the buffer. A decoder that demands four bytes
  of lookahead silently truncates the file by 1–3 bytes. Always check the decoded
  length against the declared size.

`hog_extract.py --decompress` expands RefPack members on the way out and leaves
everything else untouched:

```
python tools/hog_extract.py resource.hog -o out/ -d -f gunstats.bin
  extracted gunstats.bin  (5280 bytes) <- refpack 459
```

*The audit that produced this section was prompted by DMJC's independent port of
the same routine — see [`external-re-credits.md`](external-re-credits.md).*

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
