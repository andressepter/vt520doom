#!/usr/bin/env python3
"""
Initialize a VT520 over a Linux serial device for pseudographics experiments.

Default behavior:
- Open /dev/ttyS0 at 115200 8N1, raw mode.
- Reset terminal.
- Select WYSE 160/60 personality.
- Enable WYSE enhanced mode.
- Select 132-column display.
- Initialize 4 font banks with built-in sets and select primary active set.
"""

from __future__ import annotations

import argparse
import os
import sys
import termios
import time

ESC = b"\x1b"


def configure_serial(fd: int, baud: int) -> None:
    attrs = termios.tcgetattr(fd)

    # iflag, oflag, lflag: raw-ish I/O (no translations/echo/canonical mode).
    attrs[0] = 0
    attrs[1] = 0
    attrs[3] = 0

    # cflag: 8N1, local line, enable receiver.
    attrs[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[2] &= ~(termios.PARENB | termios.CSTOPB | termios.CSIZE)
    attrs[2] |= termios.CS8

    baud_map = {
        9600: termios.B9600,
        19200: termios.B19200,
        38400: termios.B38400,
        57600: termios.B57600,
        115200: termios.B115200,
    }
    if baud not in baud_map:
        raise ValueError(f"Unsupported baud {baud}. Use one of: {sorted(baud_map)}")

    termios.cfsetispeed(attrs, baud_map[baud])
    termios.cfsetospeed(attrs, baud_map[baud])
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def send(fd: int, data: bytes, sleep_s: float = 0.03) -> None:
    os.write(fd, data)
    termios.tcdrain(fd)
    time.sleep(sleep_s)


def build_init_sequence() -> list[tuple[str, bytes]]:
    return [
        ("RIS (full reset)", ESC + b"c"),
        ("Home + clear", ESC + b"[H" + ESC + b"[2J"),
        # VT520 manual table 12-2: select WYSE 160/60 personality.
        ("Select WYSE 160/60 personality", ESC + b"~4"),
        # Enhanced mode ON (default), sent explicitly for deterministic startup.
        ("Set WYSE enhanced mode ON", ESC + b"~!"),
        # Table 12-11: select 132-column display in WYSE mode.
        ("Select 132-column display", ESC + b"`;"),
        # Chapter 13 table 13-2: load built-in character sets into all 4 font banks.
        ("Load bank 0: Native", ESC + b"c@0@"),
        ("Load bank 1: Graphics 1", ESC + b"c@1C"),
        ("Load bank 2: Graphics 2", ESC + b"c@2E"),
        ("Load bank 3: Graphics 3", ESC + b"c@3F"),
        # Define logical sets and select active set.
        ("Primary charset -> bank 1", ESC + b"cB1"),
        ("Secondary charset -> bank 2", ESC + b"cC2"),
        ("Select primary charset active", ESC + b"cD"),
    ]


def build_visual_test_sequence() -> list[tuple[str, bytes]]:
    ruler = "".join(str(i % 10) for i in range(1, 133)).encode("ascii")
    title = b"VT520/WYSE160 INIT OK  |  132-col ruler below  |  if box is intact: serial + mode are good"

    return [
        ("Clear before visual test", ESC + b"[2J" + ESC + b"[H"),
        ("Title line", ESC + b"[1;1H" + title[:132]),
        ("132-column ruler", ESC + b"[2;1H" + ruler),
        ("ASCII box top", ESC + b"[4;1H" + b"+" + b"-" * 130 + b"+"),
        ("ASCII box middle", ESC + b"[5;1H" + b"|" + b" " * 130 + b"|"),
        ("ASCII box message", ESC + b"[6;1H" + b"| visual test: if this line spans almost full screen, 132-col mode is active ".ljust(131, b" ") + b"|"),
        ("ASCII box middle 2", ESC + b"[7;1H" + b"|" + b" " * 130 + b"|"),
        ("ASCII box bottom", ESC + b"[8;1H" + b"+" + b"-" * 130 + b"+"),
        # DEC Special Graphics demo (line drawing) using G1 + SO/SI.
        ("DEC line drawing demo", ESC + b"[10;1H" + ESC + b")0" + b"\x0e" + b"lqqqqqqk x VT line drawing demo x mqqqqqqj" + b"\x0f"),
        ("Instruction", ESC + b"[12;1H" + b"Press Ctrl+C in sender app to exit, terminal should remain responsive."),
        ("Cursor to safe row", ESC + b"[14;1H"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize VT520 over serial.")
    parser.add_argument("--device", default="/dev/ttyS0", help="Serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print sequence names and bytes without writing serial output",
    )
    parser.add_argument(
        "--skip-visual-test",
        action="store_true",
        help="Only initialize mode; do not draw the visual self-test screen",
    )
    args = parser.parse_args()

    steps = build_init_sequence()
    if not args.skip_visual_test:
        steps.extend(build_visual_test_sequence())

    if args.dry_run:
        for name, payload in steps:
            print(f"{name}: {payload!r}")
        return 0

    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_SYNC)
    except OSError as exc:
        print(f"Failed to open {args.device}: {exc}", file=sys.stderr)
        return 2

    try:
        configure_serial(fd, args.baud)
        for name, payload in steps:
            send(fd, payload)
            print(f"OK: {name}")
        return 0
    except Exception as exc:  # noqa: BLE001 - simple CLI tool
        print(f"Initialization failed: {exc}", file=sys.stderr)
        return 3
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
