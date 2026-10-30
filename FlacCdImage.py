"""FLAC-backed virtual raw CD-DA PCM image."""

from __future__ import annotations

import sys
import threading

import numpy as np
import soundfile as sf
from mutagen.flac import FLAC, CueSheet

from Constants import (
   BYTES_PER_SAMPLE_FRAME,
   CD_CHANNELS,
   CD_SAMPLE_RATE,
   SAMPLES_PER_SECTOR,
   SECTOR_SIZE,
)
from TrackInfo import formatCuesheetReport, parseCuesheet


class FlacCdImage:
   """
   Presents a CD-DA-compatible FLAC as a flat raw PCM image.

   Byte offset N maps to sample frame N // 4 of 16-bit LE stereo PCM.
   One CD sector = 2352 bytes = 588 frames.
   """

   def __init__(self, path: str, cacheFrames: int = 588 * 64):
      self.path = path
      self._lock = threading.RLock()
      self._soundFile = sf.SoundFile(path, mode="r")
      self._meta = FLAC(path)

      self._validateStream()
      if self._meta.cuesheet is None:
         raise ValueError("FLAC has no embedded CUESHEET metadata block. "
                          "Import one with metaflac --import-cuesheet-from=...")

      self.cue: CueSheet = self._meta.cuesheet
      self.tracks, self.leadOut = parseCuesheet(self.cue)

      self.totalSamples = int(self._soundFile.frames)
      if self.totalSamples <= 0:
         # Fall back to STREAMINFO if soundfile reports unknown length
         streamInfo = self._meta.info
         self.totalSamples = int(getattr(streamInfo, "total_samples", 0) or 0)
      if self.totalSamples <= 0:
         raise ValueError("Cannot determine total sample count of FLAC stream")

      if self.totalSamples % SAMPLES_PER_SECTOR != 0:
         raise ValueError(f"Total samples ({self.totalSamples}) is not divisible by "
                          f"{SAMPLES_PER_SECTOR}; not a clean CD-DA rip")

      if self.leadOut and self.leadOut.startSample != self.totalSamples:
         # Warn only — some tools put lead-out at a slightly different point
         print(f"warning: cuesheet lead-out sample {self.leadOut.startSample} "
               f"!= FLAC length {self.totalSamples}",
               file=sys.stderr)

      self.imageSize = self.totalSamples * BYTES_PER_SAMPLE_FRAME
      self.sectorCount = self.totalSamples // SAMPLES_PER_SECTOR

      # Simple decoded-PCM window cache (int16 interleaved bytes)
      self._cacheFrames = max(cacheFrames, SAMPLES_PER_SECTOR)
      self._cacheStart = -1  # absolute frame index of cache[0]
      self._cache = b""

   def _validateStream(self) -> None:
      if self._soundFile.samplerate != CD_SAMPLE_RATE:
         raise ValueError(f"Sample rate {self._soundFile.samplerate} Hz; "
                          f"CD-DA requires {CD_SAMPLE_RATE}")
      if self._soundFile.channels != CD_CHANNELS:
         raise ValueError(f"{self._soundFile.channels} channels; "
                          f"CD-DA requires {CD_CHANNELS}")
      # subtype may be PCM_16 or FLAC; bits from mutagen STREAMINFO
      bitsPerSample = getattr(self._meta.info, "bits_per_sample", 16)
      if bitsPerSample != 16:
         raise ValueError(f"{bitsPerSample}-bit audio; CD-DA requires 16-bit")

   def close(self) -> None:
      with self._lock:
         self._soundFile.close()

   def report(self) -> str:
      return formatCuesheetReport(self.path, self.cue, self.tracks,
                                  self.leadOut, self.totalSamples) + (
         f"\nVirtual image: {self.imageSize} bytes "
         f"({self.sectorCount} × {SECTOR_SIZE}-byte sectors)\n")

   def _fillCache(self, startFrame: int) -> None:
      """Decode up to cacheFrames starting at startFrame into _cache."""
      startFrame = max(0, min(startFrame, self.totalSamples))
      frameCount = min(self._cacheFrames, self.totalSamples - startFrame)
      if frameCount <= 0:
         self._cacheStart = startFrame
         self._cache = b""
         return
      self._soundFile.seek(startFrame)
      # always_2d int16 → shape (n, channels)
      frames = self._soundFile.read(frameCount, dtype="int16", always_2d=True)
      if frames.shape[0] != frameCount:
         # Unexpected short read — use what we got
         frameCount = int(frames.shape[0])
      # Interleave to little-endian PCM bytes (numpy int16 is native endian;
      # force little-endian for CD-DA / Windows).
      pcm = np.ascontiguousarray(frames, dtype="<i2")
      self._cache = pcm.tobytes()
      self._cacheStart = startFrame

   def read(self, offset: int, length: int) -> bytes:
      """Read `length` bytes from virtual image byte `offset`."""
      if length <= 0:
         return b""
      if offset < 0:
         offset = 0
      if offset >= self.imageSize:
         return b"\x00" * length

      end = min(offset + length, self.imageSize)
      need = end - offset
      out = bytearray(length)

      with self._lock:
         pos = 0
         while pos < need:
            absOff = offset + pos
            frame = absOff // BYTES_PER_SAMPLE_FRAME
            inFrame = absOff % BYTES_PER_SAMPLE_FRAME

            # Refill cache if this byte is outside the window
            cacheEndFrame = self._cacheStart + (
               len(self._cache) // BYTES_PER_SAMPLE_FRAME)
            if (self._cacheStart < 0
                  or frame < self._cacheStart
                  or frame >= cacheEndFrame):
               # Align cache start a little before the request for sequential I/O
               align = frame - (frame % SAMPLES_PER_SECTOR)
               self._fillCache(align)
               cacheEndFrame = self._cacheStart + (
                  len(self._cache) // BYTES_PER_SAMPLE_FRAME)

            if not self._cache or frame >= cacheEndFrame:
               # Past EOF inside imageSize shouldn't happen; pad zeros
               break

            cacheByte = (
               (frame - self._cacheStart) * BYTES_PER_SAMPLE_FRAME + inFrame)
            chunk = self._cache[cacheByte : cacheByte + (need - pos)]
            if not chunk:
               break
            out[pos : pos + len(chunk)] = chunk
            pos += len(chunk)

      return bytes(out)
