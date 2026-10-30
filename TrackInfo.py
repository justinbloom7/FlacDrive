"""Track layout parsed from a FLAC embedded CUESHEET."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from mutagen.flac import CueSheet, CueSheetTrack

from Constants import CD_LEAD_OUT_TRACK, SAMPLES_PER_SECTOR


@dataclass
class TrackInfo:
   number: int
   startSample: int
   startSector: int
   isrc: str
   preEmphasis: bool
   indexes: List[Tuple[int, int]]  # (indexNumber, absoluteSample)

   def msf(self, sample: Optional[int] = None) -> str:
      """Format an absolute sample offset as MM:SS:FF (75 frames/sec)."""
      sector = (self.startSample if sample is None else sample) // SAMPLES_PER_SECTOR
      frames = sector % 75
      totalSec = sector // 75
      minutes = totalSec // 60
      seconds = totalSec % 60
      return f"{minutes:02d}:{seconds:02d}:{frames:02d}"


def samplesToMsf(sample: int) -> str:
   sector = sample // SAMPLES_PER_SECTOR
   frames = sector % 75
   totalSec = sector // 75
   return f"{totalSec // 60:02d}:{totalSec % 60:02d}:{frames:02d}"


def asText(value: object) -> str:
   """Normalize mutagen text/bytes fields to str."""
   if value is None:
      return ""
   if isinstance(value, bytes):
      return value.decode("ascii", errors="replace").strip("\x00").strip()
   return str(value).strip("\x00").strip()


def parseCuesheet(cue: CueSheet) -> Tuple[List[TrackInfo], Optional[TrackInfo]]:
   """Return (audioTracks, leadOutTrack)."""
   tracks: List[TrackInfo] = []
   leadOut: Optional[TrackInfo] = None

   for track in cue.tracks:
      assert isinstance(track, CueSheetTrack)
      indexes = [
         (idx.index_number, track.start_offset + idx.index_offset)
         for idx in track.indexes
      ]
      info = TrackInfo(number=track.track_number,
                       startSample=track.start_offset,
                       startSector=track.start_offset // SAMPLES_PER_SECTOR,
                       isrc=asText(track.isrc),
                       preEmphasis=bool(track.pre_emphasis),
                       indexes=indexes)
      if track.track_number == CD_LEAD_OUT_TRACK or track.track_number == 255:
         leadOut = info
      else:
         tracks.append(info)
   return tracks, leadOut


def formatCuesheetReport(path: str,
                         cue: CueSheet,
                         tracks: List[TrackInfo],
                         leadOut: Optional[TrackInfo],
                         totalSamples: int) -> str:
   catalog = asText(cue.media_catalog_number) or "(none)"
   lines = [
      f"File: {path}",
      f"Catalog: {catalog}",
      f"CD-DA cuesheet: {bool(cue.compact_disc)}",
      f"Lead-in samples: {cue.lead_in_samples} "
      f"({samplesToMsf(cue.lead_in_samples)} of lead-in, not stored in FLAC)",
      f"Audio samples in FLAC: {totalSamples} ({samplesToMsf(totalSamples)})",
      f"Tracks: {len(tracks)}",
      "",
   ]
   for track in tracks:
      isrc = f"  ISRC={track.isrc}" if track.isrc else ""
      pre = "  pre-emphasis" if track.preEmphasis else ""
      lines.append(f"  TRACK {track.number:02d}  LBA {track.startSector:6d}  "
                   f"{track.msf()}{isrc}{pre}")
      for indexNumber, indexSample in track.indexes:
         lines.append(f"    INDEX {indexNumber:02d}  {samplesToMsf(indexSample)}")
   if leadOut:
      lines.append(f"  LEAD-OUT   LBA {leadOut.startSector:6d}  {leadOut.msf()}")
   return "\n".join(lines)
