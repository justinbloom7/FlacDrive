"""ImDisk IMDPROXY protocol session over a binary stream."""

from __future__ import annotations

import sys
from typing import BinaryIO

from Constants import (
   EACCES,
   EIO,
   IMDPROXY_FLAG_RO,
   IMDPROXY_REQ_CLOSE,
   IMDPROXY_REQ_CONNECT,
   IMDPROXY_REQ_INFO,
   IMDPROXY_REQ_NULL,
   IMDPROXY_REQ_READ,
   IMDPROXY_REQ_WRITE,
   INFO_RESP,
   READ_REQ_TAIL,
   READ_RESP,
   U64,
   WRITE_RESP,
)
from FlacCdImage import FlacCdImage


class ProxySession:
   """Speak the ImDisk proxy protocol on a binary bi-directional stream."""

   def __init__(self, image: FlacCdImage, reader: BinaryIO, writer: BinaryIO):
      self.image = image
      self.reader = reader
      self.writer = writer

   def _readExact(self, size: int) -> bytes:
      buf = bytearray()
      while len(buf) < size:
         chunk = self.reader.read(size - len(buf))
         if not chunk:
            raise EOFError("peer closed connection")
         buf.extend(chunk)
      return bytes(buf)

   def _write(self, data: bytes) -> None:
      self.writer.write(data)
      self.writer.flush()

   def serve(self) -> None:
      while True:
         raw = self._readExact(8)
         (code,) = U64.unpack(raw)

         if code == IMDPROXY_REQ_INFO:
            self._handleInfo()
         elif code == IMDPROXY_REQ_READ:
            self._handleRead()
         elif code == IMDPROXY_REQ_WRITE:
            self._handleWrite()
         elif code == IMDPROXY_REQ_CLOSE:
            return
         elif code == IMDPROXY_REQ_NULL:
            continue
         elif code == IMDPROXY_REQ_CONNECT:
            # Shared-memory connect is not used for TCP/stdio proxies.
            # Reply with a generic failure object_ptr.
            self._write(U64.pack(1) + U64.pack(0))
         else:
            print(f"warning: unknown IMDPROXY request {code}", file=sys.stderr)
            return

   def _handleInfo(self) -> None:
      # alignment 1 = any byte offset; flag RO
      self._write(INFO_RESP.pack(self.image.imageSize, 1, IMDPROXY_FLAG_RO))

   def _handleRead(self) -> None:
      offset, length = READ_REQ_TAIL.unpack(self._readExact(16))
      length = int(length)
      offset = int(offset)
      # Cap individual transfers to avoid huge allocations (16 MiB)
      maxXfer = 16 * 1024 * 1024
      if length > maxXfer:
         length = maxXfer
      try:
         data = self.image.read(offset, length)
         self._write(READ_RESP.pack(0, len(data)))
         if data:
            self._write(data)
      except OSError as exc:
         print(f"read error at {offset}+{length}: {exc}", file=sys.stderr)
         self._write(READ_RESP.pack(EIO, 0))

   def _handleWrite(self) -> None:
      offset, length = READ_REQ_TAIL.unpack(self._readExact(16))
      length = int(length)
      # Drain payload so the stream stays in sync, then reject (read-only).
      remaining = length
      while remaining > 0:
         chunk = self.reader.read(min(remaining, 1 << 20))
         if not chunk:
            break
         remaining -= len(chunk)
      self._write(WRITE_RESP.pack(EACCES, 0))
