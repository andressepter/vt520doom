#!/usr/bin/env python3
"""
NEXT ITERATION FORK — copy of vt520_init.py; extend here for frame/font upload experiments.

Stable entrypoint remains: ./vt520_init.py

Initialize a serial-attached DEC- or Wyse-personality session (see terminal Setup).

`--model vt510` — DEC control sequences (VT510/420/320-class). Default avoids full RIS when that
feels like a reboot. `--cols` default `keep` skips DECCOLM so Setup width (e.g. 132) is preserved;
use `80` or `132` to force `ESC [ ? 3 l` / `ESC [ ? 3 h`.

`--model vt520` — Wyse 160/60 setup from the VT520 manual (font banks, `ESC ~` commands). Use when
Setup is WYSE 160/60; many VT510-class terminals offer that mode in Setup — it is not limited to
a VT520 badge. Other Setup modes (TVI, ADDS, SCO, …) are not targeted.

Wrong pairing (Wyse bytes while session is DEC, or DEC init while session is Wyse) yields a blank
or corrupt screen; match `--model` to the **active emulation** in Setup.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import termios
import time

ESC = b"\x1b"

# Figlet fonts tried in order (ASCII-only, chunky first — “doom.flf” needs extra font packages).
_FIGLET_DOOM_FONTS = ("block", "big", "shadow", "slant", "standard")


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

    speed = baud_map[baud]
    # Python's termios often omits cfsetispeed/cfsetospeed; tcgetattr's list uses
    # indices 4/5 for input/output speed (same layout as the C termios struct).
    if hasattr(termios, "cfsetispeed"):
        termios.cfsetispeed(attrs, speed)
        termios.cfsetospeed(attrs, speed)
    else:
        attrs[4] = speed
        attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def send(fd: int, data: bytes, sleep_s: float = 0.03) -> None:
    os.write(fd, data)
    termios.tcdrain(fd)
    time.sleep(sleep_s)


def build_init_sequence_vt510(reset: str, cols: str) -> list[tuple[str, bytes]]:
    """DEC VT510 / VT420-class: no WYSE personality or font-bank commands."""
    if cols not in ("80", "132", "keep"):
        raise ValueError('cols must be "80", "132", or "keep"')

    steps: list[tuple[str, bytes]] = []
    if reset == "full":
        steps.append(("RIS (full hardware reset)", ESC + b"c"))
    elif reset == "soft":
        # DECSTR — soft terminal reset; avoids full RIS power-on style behavior.
        steps.append(("DECSTR (soft terminal reset)", ESC + b"[!p"))
    elif reset != "none":
        raise ValueError(f"Unknown reset {reset!r}")

    steps.append(("Home + clear", ESC + b"[H" + ESC + b"[2J"))

    if cols == "132":
        steps.append(("132-column mode (DECCOLM on)", ESC + b"[?3h"))
    elif cols == "80":
        steps.append(("80-column mode (DECCOLM off)", ESC + b"[?3l"))
    # cols == "keep": omit DECCOLM so width matches Setup (e.g. 132 max).

    steps.extend(
        [
            ("Show cursor (DECTCEM)", ESC + b"[?25h"),
            ("Clear after mode change", ESC + b"[2J" + ESC + b"[H"),
        ]
    )
    return steps


def build_init_sequence_vt520() -> list[tuple[str, bytes]]:
    """WYSE 160/60 path from VT520 RM — use when Setup personality is Wyse (not “VT520 hardware only”)."""
    return [
        ("RIS (full reset)", ESC + b"c"),
        ("Home + clear", ESC + b"[H" + ESC + b"[2J"),
        ("Select WYSE 160/60 personality", ESC + b"~4"),
        ("Set WYSE enhanced mode ON", ESC + b"~!"),
        ("Select 132-column display (WYSE)", ESC + b"`;"),
        ("Load bank 0: Native", ESC + b"c@0@"),
        ("Load bank 1: Graphics 1", ESC + b"c@1C"),
        ("Load bank 2: Graphics 2", ESC + b"c@2E"),
        ("Load bank 3: Graphics 3", ESC + b"c@3F"),
        ("Primary charset -> bank 1", ESC + b"cB1"),
        ("Secondary charset -> bank 2", ESC + b"cC2"),
        ("Select primary charset active", ESC + b"cD"),
    ]


def build_init_sequence(model: str, reset: str, cols: str) -> list[tuple[str, bytes]]:
    if model == "vt520":
        return build_init_sequence_vt520()
    if model == "vt510":
        return build_init_sequence_vt510(reset, cols)
    raise ValueError(f"Unknown model {model!r}; use vt510 or vt520")


def build_visual_test_sequence(model: str, cols: str) -> list[tuple[str, bytes]]:
    if model == "vt520":
        cols = "132"
    if cols not in ("80", "132", "keep"):
        raise ValueError('cols must be "80", "132", or "keep"')
    # Ruler width: match explicit DECCOLM; for "keep" assume max (132) so ruler fits Setup max.
    visual_cols = 132 if cols == "keep" else int(cols)

    if model == "vt520":
        tag = b"VT520 WYSE160"
    else:
        tag = b"VT510 DEC"

    ruler = "".join(str(i % 10) for i in range(1, visual_cols + 1)).encode("ascii")
    inner = visual_cols - 2

    def boxed_row(text: bytes) -> bytes:
        body = text.ljust(inner, b" ")[:inner]
        return b"|" + body + b"|"

    line_row = 10
    instr_row = 12
    cur_row = 14

    if visual_cols == 132:
        title = (tag + b" INIT OK | 132-col ruler | box OK => serial+mode OK").ljust(visual_cols)[
            :visual_cols
        ]
        msg = boxed_row(
            b" visual: ruler width ~132 cols if DECCOLM matches your screen"
        )
        line_demo = b"lqqqqqqk VT line drawing mqqqqqqj"
    else:
        title = (tag + b" INIT OK | 80-col | fits Setup lines/screen").ljust(visual_cols)[
            :visual_cols
        ]
        msg = boxed_row(
            b" 80-col: lines/screen set in Setup; try --reset none if unit still resets"
        )
        line_demo = b""

    out: list[tuple[str, bytes]] = [
        ("Clear before visual test", ESC + b"[2J" + ESC + b"[H"),
        ("Title line", ESC + b"[1;1H" + title),
        ("Column ruler", ESC + b"[2;1H" + ruler),
        ("ASCII box top", ESC + b"[4;1H" + b"+" + b"-" * inner + b"+"),
        ("ASCII box middle", ESC + b"[5;1H" + b"|" + b" " * inner + b"|"),
        ("ASCII box message", ESC + b"[6;1H" + msg),
        ("ASCII box middle 2", ESC + b"[7;1H" + b"|" + b" " * inner + b"|"),
        ("ASCII box bottom", ESC + b"[8;1H" + b"+" + b"-" * inner + b"+"),
    ]

    if visual_cols == 80:
        # SO/SI + G1 maps l q k m j to box-drawing; looks "wrong" if you expect letters.
        plain = (
            b" 80-col: plain text row (no ESC )0 / SO / SI). For G1 demo use --cols 132."
        ).ljust(visual_cols, b" ")[:visual_cols]
        out.append(("Visual row (plain ASCII)", ESC + b"[%d;1H" % line_row + plain))
    else:
        out.append(
            (
                "DEC line drawing (ESC )0 + SO + lqk... + SI)",
                ESC + b"[%d;1H" % line_row
                + ESC
                + b")0"
                + b"\x0e"
                + line_demo
                + b"\x0f",
            )
        )

    out.extend(
        [
            (
                "Instruction",
                (
                    ESC
                    + b"[%d;1H" % instr_row
                    + b"Ctrl+C exits sender. ".ljust(visual_cols, b" ")[:visual_cols]
                ),
            ),
            ("Cursor to safe row", ESC + b"[%d;1H" % cur_row),
        ]
    )
    return out


def visual_width_for_layout(model: str, cols: str) -> int:
    if model == "vt520":
        return 132
    if cols == "keep":
        return 132
    return int(cols)


def _figlet_doom_lines(text: str, visual_cols: int) -> tuple[list[str], str]:
    exe = shutil.which("figlet")
    if not exe:
        return (
            [
                text.center(min(visual_cols, len(text) + 4))[:visual_cols],
                "install: apt install figlet",
            ],
            "none",
        )

    w_arg = str(max(visual_cols * 2, 80))
    for font in _FIGLET_DOOM_FONTS:
        try:
            proc = subprocess.run(
                [exe, "-w", w_arg, "-f", font, text],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            continue
        lines = [ln.rstrip() for ln in proc.stdout.rstrip("\n").split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue
        try:
            "\n".join(lines).encode("ascii")
        except UnicodeEncodeError:
            continue
        if max(len(s) for s in lines) > visual_cols:
            continue
        return lines, font

    return (
        [
            text.center(min(visual_cols, len(text) + 4))[:visual_cols],
            "figlet: no font fit; try --cols 132",
        ],
        "fallback",
    )


def build_doom_finale_sequence(
    visual_cols: int,
    screen_rows: int,
    doom_text: str,
) -> list[tuple[str, bytes]]:
    lines, font_tag = _figlet_doom_lines(doom_text, visual_cols)
    reserved = 3
    start_row = max(1, (screen_rows - len(lines) - reserved) // 2)

    parts: list[bytes] = [ESC + b"[2J" + ESC + b"[H"]
    for i, raw in enumerate(lines):
        row = start_row + i
        centered = raw.center(visual_cols)[:visual_cols].ljust(visual_cols)[:visual_cols]
        parts.append(ESC + ("[%d;1H" % row).encode("ascii") + centered.encode("ascii", "replace"))

    info1 = (
        f"vt520_init.py | figlet -f {font_tag} | serial OK"
        if font_tag not in ("none", "fallback")
        else "vt520_init.py | install figlet (apt install figlet) for banner"
    )
    info1 = info1.center(visual_cols)[:visual_cols].ljust(visual_cols)[:visual_cols]
    info_row = start_row + len(lines) + 1
    parts.append(ESC + ("[%d;1H" % info_row).encode("ascii") + info1.encode("ascii", "replace"))

    info2 = "Optional: extra figlet fonts (e.g. doom.flf) from distro figlet-fonts packages".center(
        visual_cols
    )[:visual_cols].ljust(visual_cols)[:visual_cols]
    parts.append(
        ESC + ("[%d;1H" % (info_row + 1)).encode("ascii") + info2.encode("ascii", "replace")
    )

    label = f"DooM finale (figlet -f {font_tag})" if font_tag != "none" else "DooM finale (no figlet)"
    return [(label, b"".join(parts))]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serial init: vt510=DEC sequences, vt520=Wyse 160/60 (match terminal Setup)."
    )
    parser.add_argument("--device", default="/dev/ttyS0", help="Serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument(
        "--model",
        choices=("vt510", "vt520"),
        default="vt510",
        help="vt510=DEC init (VT510/420… in Setup); vt520=Wyse 160/60 init (set Wyse in Setup first)",
    )
    parser.add_argument(
        "--reset",
        choices=("none", "soft", "full"),
        default="soft",
        help="none=clear only; soft=DECSTR (default); full=RIS ESC c (can feel like reboot)",
    )
    parser.add_argument(
        "--cols",
        type=str,
        default="keep",
        choices=("80", "132", "keep"),
        help=(
            "vt510 DECCOLM: keep=do not send ESC[?3h/l (leave Setup width); "
            "80 or 132=force mode. VT520 init ignores this."
        ),
    )
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
    parser.add_argument(
        "--skip-doom-finale",
        action="store_true",
        help="Skip centered figlet DooM splash after init / visual test",
    )
    parser.add_argument(
        "--screen-rows",
        type=int,
        default=25,
        metavar="N",
        help="Terminal height for vertical centering of DooM finale (match Setup lines/screen)",
    )
    parser.add_argument(
        "--doom-text",
        default="DooM",
        help="String passed to figlet for the finale banner",
    )
    args = parser.parse_args()

    steps = build_init_sequence(args.model, args.reset, args.cols)
    if not args.skip_visual_test:
        steps.extend(build_visual_test_sequence(args.model, args.cols))
    if not args.skip_doom_finale:
        vw = visual_width_for_layout(args.model, args.cols)
        steps.extend(
            build_doom_finale_sequence(vw, max(10, args.screen_rows), args.doom_text)
        )

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
