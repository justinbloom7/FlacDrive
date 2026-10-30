"""CD-DA and ImDisk IMDPROXY protocol constants."""

from __future__ import annotations

import struct

# CD-DA layout
SECTOR_SIZE = 2352          # bytes per CD-DA sector (AUDIO)
SAMPLES_PER_SECTOR = 588    # 44100 / 75
BYTES_PER_SAMPLE_FRAME = 4  # 16-bit stereo interleaved LE PCM
CD_SAMPLE_RATE = 44100
CD_CHANNELS = 2
CD_LEAD_OUT_TRACK = 170

# IMDPROXY request codes (enum IMDPROXY_REQ)
IMDPROXY_REQ_NULL = 0
IMDPROXY_REQ_INFO = 1
IMDPROXY_REQ_READ = 2
IMDPROXY_REQ_WRITE = 3
IMDPROXY_REQ_CONNECT = 4
IMDPROXY_REQ_CLOSE = 5

IMDPROXY_FLAG_RO = 0x01

# Little-endian ULONGLONG helpers
U64 = struct.Struct("<Q")
INFO_RESP = struct.Struct("<QQQ")     # file_size, req_alignment, flags
READ_REQ_TAIL = struct.Struct("<QQ")  # offset, length (after request_code)
READ_RESP = struct.Struct("<QQ")      # errorno, length
WRITE_RESP = struct.Struct("<QQ")     # errorno, length

# errno-style codes returned to ImDisk (POSIX values; ImDisk accepts non-zero)
EACCES = 13
EIO = 5
