#!/usr/bin/env python3
"""
FlacDrive — ImDisk / devio proxy that serves a single-file FLAC as a raw
CD-DA image (2352-byte sectors) without decompressing the whole file first.

Protocol: ImDisk IMDPROXY over TCP or stdio (see ImDisk inc/imdproxy.h).
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from typing import BinaryIO, List, Optional, Tuple

from Constants import SAMPLES_PER_SECTOR, SECTOR_SIZE
from FlacCdImage import FlacCdImage
from ProxySession import ProxySession


def forceBinaryStdio() -> Tuple[BinaryIO, BinaryIO]:
   """Put stdin/stdout in binary mode (required on Windows)."""
   if sys.platform == "win32":
      import msvcrt

      msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
      msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
   return sys.stdin.buffer, sys.stdout.buffer


def serveStdio(image: FlacCdImage) -> None:
   reader, writer = forceBinaryStdio()
   print("Serving on stdio (binary IMDPROXY). Waiting for ImDisk...",
         file=sys.stderr)
   ProxySession(image, reader, writer).serve()


def serveTcp(image: FlacCdImage,
             host: str,
             port: int,
             once: bool = True) -> None:
   with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
      server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      server.bind((host, port))
      server.listen(1)
      print(f"Listening on {host}:{port}. Mount with:\n"
            f"  imdisk -a -t proxy -o ip -o ro -f {host}:{port} -m X: -b {SECTOR_SIZE}",
            file=sys.stderr)
      while True:
         conn, addr = server.accept()
         print(f"Client connected: {addr[0]}:{addr[1]}", file=sys.stderr)
         try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            reader = conn.makefile("rb")
            writer = conn.makefile("wb")
            try:
               ProxySession(image, reader, writer).serve()
            finally:
               writer.close()
               reader.close()
         except (EOFError, ConnectionResetError, BrokenPipeError) as exc:
            print(f"Client disconnected: {exc}", file=sys.stderr)
         finally:
            conn.close()
         if once:
            break


def buildArgParser() -> argparse.ArgumentParser:
   parser = argparse.ArgumentParser(description=(
      "Serve a single-file FLAC (with embedded CUESHEET) as a raw "
      f"{SECTOR_SIZE}-byte/sector CD-DA image for ImDisk."))
   parser.add_argument("flac",
                       help="Path to a CD-DA FLAC with embedded CUESHEET")
   mode = parser.add_mutually_exclusive_group()
   mode.add_argument("--tcp",
                     metavar="PORT",
                     type=int,
                     help="Listen on TCP localhost:PORT (ImDisk -o ip)")
   mode.add_argument("--stdio",
                     action="store_true",
                     help="Speak IMDPROXY on stdin/stdout (binary)")
   mode.add_argument("--list",
                     action="store_true",
                     help="Print cuesheet / image info and exit (no server)")
   parser.add_argument("--host",
                       default="127.0.0.1",
                       help="TCP bind address (default: 127.0.0.1)")
   parser.add_argument("--keep-listening",
                       action="store_true",
                       help="With --tcp, accept another client after disconnect")
   parser.add_argument("--cache-sectors",
                       type=int,
                       default=64,
                       metavar="N",
                       help="Decoded PCM cache size in CD sectors (default: 64 ≈ 147 KiB)")
   return parser


def main(argv: Optional[List[str]] = None) -> int:
   args = buildArgParser().parse_args(argv)

   if not os.path.isfile(args.flac):
      print(f"error: file not found: {args.flac}", file=sys.stderr)
      return 2

   try:
      image = FlacCdImage(args.flac,
                          cacheFrames=SAMPLES_PER_SECTOR * max(1, args.cache_sectors))
   except Exception as exc:
      print(f"error: {exc}", file=sys.stderr)
      return 1

   print(image.report(), file=sys.stderr)

   if args.list:
      image.close()
      return 0

   if not args.tcp and not args.stdio:
      print("error: specify --tcp PORT, --stdio, or --list",
            file=sys.stderr)
      image.close()
      return 2

   try:
      if args.stdio:
         serveStdio(image)
      else:
         serveTcp(image,
                  host=args.host,
                  port=args.tcp,
                  once=not args.keep_listening)
   except KeyboardInterrupt:
      print("\nInterrupted.", file=sys.stderr)
   finally:
      image.close()
   return 0


if __name__ == "__main__":
   sys.exit(main())
