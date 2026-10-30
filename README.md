# FlacDrive

Stream a single-file FLAC (with an embedded CUESHEET) as a raw CD-DA image for [ImDisk](https://sourceforge.net/projects/imdisk-toolkit/) on Windows. Sectors are decoded on demand — the whole album is not decompressed to disk first.

The virtual image is interleaved 16-bit little-endian stereo PCM at 44.1 kHz, laid out in **2352-byte** CD-DA sectors (588 sample frames each). Track layout comes from the FLAC **CUESHEET** metadata block.

## Requirements

### System

- **Windows** with [ImDisk Virtual Disk Driver](https://sourceforge.net/projects/imdisk-toolkit/) (or ImDisk Toolkit) installed
- **Python 3.9+**

### Python packages

Install from `requirements.txt`:

```bat
python -m pip install -r requirements.txt
```

| Package | Role |
| --- | --- |
| **mutagen** | Reads the embedded FLAC `CUESHEET` block (tracks, indexes, ISRC, lead-out) |
| **soundfile** | Seeks and decodes FLAC PCM by sample (uses libsndfile; wheels include it on Windows) |
| **numpy** | Packs decoded samples into little-endian PCM bytes |

### Input FLAC

The file must be a CD-DA rip:

- 44.1 kHz, stereo, 16-bit
- Sample count divisible by 588
- A native **CUESHEET** metadata block (not only a Vorbis `CUESHEET=` comment)

If you have a `.cue` beside the FLAC, embed it with:

```bat
metaflac --import-cuesheet-from=album.cue album.flac
```

Check layout without mounting:

```bat
python flacdrive.py album.flac --list
```

## Usage

### 1. TCP proxy (recommended)

**Admin / elevated** command prompt for the ImDisk mount step.

Terminal A — start the proxy:

```bat
python flacdrive.py album.flac --tcp 9000
```

Terminal B — attach ImDisk to it:

```bat
imdisk -a -t proxy -o ip -o ro -f 127.0.0.1:9000 -m X: -b 2352
```

- `-t proxy -o ip` — connect to a TCP ImDisk/devio proxy  
- `-o ro` — read-only (writes are rejected by the proxy)  
- `-b 2352` — CD-DA sector size  
- `-m X:` — drive letter  

Unmount:

```bat
imdisk -d -m X:
```

Then stop the Python process (Ctrl+C). Use `--keep-listening` if you want the proxy to accept another client after disconnect.

### 2. Standard I/O

Binary IMDPROXY on stdin/stdout (useful when wrapping with a pipe or custom launcher):

```bat
python flacdrive.py album.flac --stdio
```

On Windows, the script forces binary mode on stdio so protocol framing is not corrupted.

### Options

| Flag | Meaning |
| --- | --- |
| `--tcp PORT` | Listen on `127.0.0.1:PORT` |
| `--host ADDR` | Bind address for `--tcp` (default `127.0.0.1`) |
| `--stdio` | IMDPROXY over stdin/stdout |
| `--list` | Print cuesheet / image size and exit |
| `--keep-listening` | After a TCP client disconnects, wait for another |
| `--cache-sectors N` | Decoded PCM window size (default 64 sectors ≈ 147 KiB) |

## How it works

1. Open the FLAC with **soundfile** and read **CUESHEET** via **mutagen**.
2. Advertise image size `total_samples × 4` bytes to ImDisk (`IMDPROXY_REQ_INFO`), with the read-only flag set.
3. On each `IMDPROXY_REQ_READ`, map the byte offset to a sample frame, seek/decode that region, and return raw PCM.
4. `IMDPROXY_REQ_WRITE` consumes the payload and returns access-denied; `IMDPROXY_REQ_CLOSE` ends the session.

The wire format matches ImDisk’s `imdproxy.h` (little-endian `ULONGLONG` fields).

## Notes

- The mounted volume is a **raw CD-DA PCM blob**, not an ISO 9660 filesystem. Tools that expect a data CD will not see files; audio tools that understand a 2352-byte/sector image (or a separate `.cue` pointing at the drive/image) are the intended consumers.
- Lead-in samples recorded in the cuesheet are **not** stored in typical FLAC rips and are not prepended to the virtual image; offsets are relative to the start of the FLAC audio stream.
- Bind to localhost by default. Only use `--host 0.0.0.0` if you intentionally want LAN access.

## License

MIT — see [LICENSE](LICENSE).
