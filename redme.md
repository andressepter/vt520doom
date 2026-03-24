How to make DOOM render (very slowly) on a DEC terminal (target: VT520; current hardware here: **VT510**).

Many **VT510-class** terminals also offer **WYSE 160/60** in Setup — same box, different *personality*. The DOOM/WYSE plan and `ESC ~` / font-bank commands come from the VT520 manual (Wyse side of the firmware). Reference: https://web.mit.edu/dosathena/doc/www/ek-vt520-rm.pdf

1. Get pre rendered DOOM frame.
2. Upscale it to 640x400.
3. Dither to bw
4. Split it to 64x25 blocks = 1600 blocks, each 10x16 pixels.
So far, so good. Now, here lies The Problem!
1600 > 256
Fortunately vt520 can be pushed to WYSE160 mode
From manual "WYSE 160: You can display all 512 characters in the four font banks on
the screen at the same time."
It is still less than 1600 but 512 10x16 individual pixel blocks are a LOT. Lot more than zx or NES
5. No i have to find an algorithm to detect "similar" blocks so I can reduce size to 512 blocks per frame. // TODO
But lets stay at 512 club. 512 x 10 x 16 = 81920
It takes mere 0.7 seconds to load WYSE 160 font. THEORETICALLY. There are header and usage commands also. But still... a breathtaking 1 FPS pereparation time is theoretically achievable.
To send actual frame (ASCII string) we need to send 2000 bytes. 2000 bytes is 16 000 bits.
togeher with font 97920 bits per second to achieve whopping 1 FPS. And we still have ~ 2KB/s to waste for overhead.

Yet antoher point of optimization. Blocks that are absolute inverse (1s instead of 0s and vice versa) can loaded only once as font and sent with "inverse" attribute set. 
This may be huge advantage because it theoretically gives us 512 blocks and additional 512 "inversed" blocks. 

Also 520 characters have "dim" attribute. This gives us weird "3-"color"" black-white-gray "palette". 
so 512+512+512 altogether. Theoretically. This should be bleny of playroom. 

I think this problem need deeper analysis. Finding "similar" fields and merging them to one - galois fields may help there.
But.. this is purely mathematical approach. Two fields that differ by just few pixels may be "close" mathematically but they belong to bigger picture. 
So 6 bits can be just "noise" OR they can be significant detail (like goom-guy eye). Bits that create status bar are similar to bits that create landscape in a math. sense, 
but much more significant in gameplay sense. This is going to be tough!

We need to extract more information from DOOM engine and separate it to classes

1. Wireframes that make up floor ceilings etc. class A
2. status bar - class A
3. Monsters. class B
4. sprites - class D
5. textures - class F

So class A gets A treatment. Fully rendered. Class B - some replacements allowed. Classes D and F - whatever left over. 

Of course, higher classes blocks can, and will be, re-used on lower priority classes. 

---

Emulation modes (from terminal Setup — exact list depends on firmware)

These panels expose multiple personalities; pick one in Setup before or instead of relying on host-sent mode switches:

- **DEC:** VT510, VT420, VT320, VT220, VT100, VT52, VT420PCTerm  
- **Wyse:** WYSE 160/60, WYSE 160/60 PCTerm, WYSE 50+, WYSE 150/120  
- **Televideo:** TVI 950, TVI 925, TVI 910+  
- **Other:** ADDS A2, SCO Console  

`vt520_init.py --model vt510` sends **DEC** control sequences — use when Setup is **VT510 / VT420 / …** (DEC). `--model vt520` sends **WYSE 160/60** setup bytes from the VT520 manual — use when Setup is **WYSE 160/60** (or you are switching into that personality). It is **not** “VT520 hardware only”; it is “Wyse command set.” Sending Wyse bytes while the session is still in **DEC** mode (or the reverse) produces garbage or a blank screen — **match script to the active Setup personality**, not to the model name on the bezel.

---

Basic serial prerequisites and terminal init

Assumption: no getty is attached to the serial device, and your process owns that port.

1) Give your user direct access to `/dev/ttyS0` on Linux

- Check device owner/group:
  - `ls -l /dev/ttyS0`
- Most distros gate serial access via group `dialout` (sometimes `uucp`):
  - `sudo usermod -aG dialout $USER`
- Re-login (or reboot) so new group membership is active.
- Optional udev rule for stable perms:
  - Create `/etc/udev/rules.d/99-ttyS0.rules` with:
    - `KERNEL=="ttyS0", MODE="0660", GROUP="dialout"`
  - Then: `sudo udevadm control --reload-rules && sudo udevadm trigger`

2) Python initializer (`vt520_init.py`)

Opens the serial port at `115200 8N1` raw mode, then sends mode setup. **Default is `--model vt510`**, **`--reset soft`** (DECSTR, not full RIS), **`--cols keep`**.

- **`--model vt510` (DEC path):** CSI/DEC-style sequences only (no `ESC ~` Wyse setup). Uses **soft reset** by default instead of **RIS** (`ESC c`) when a full reset feels like a reboot; try `--reset none` if needed. **`--cols`:** `keep` = **do not send** `ESC [ ? 3 h` / `ESC [ ? 3 l` (leave width as in Setup, e.g. 132 max); `80` or `132` = **force** DECCOLM. Older script versions defaulted to `--cols 80`, which **overrode** a 132-wide Setup — use `keep` or `--cols 132` if you want full width.
- **“Funny lines” below the box:** that row was **DEC line drawing**: `ESC ) 0` maps G1 to Special Graphics; **SO** (shift out) makes `l q k m j` draw corners/lines, not letters. In **`--cols 80`** mode the script now uses a **plain ASCII** line there instead; the G1 demo is kept for **132-wide** visual tests.
- **`--model vt520` (Wyse path):** Sequences from the VT520 manual: personality (`ESC ~ 4`), enhanced mode, Wyse 132-column, font banks. Use this when Setup is **WYSE 160/60** (or equivalent). Same physical **VT510** can run this mode if the firmware lists it.

**Personality mismatch:** If the terminal is in **DEC** mode and you run **`--model vt520`**, or it is in **Wyse** mode and you run **`--model vt510`**, you can get a **blank or wrong screen** while the PC still prints `OK:` (host stdout, not the terminal).

Run:

- `python3 vt520_init.py --dry-run`
- `python3 vt520_init.py --device /dev/ttyUSB0 --baud 115200` (default `--cols keep`)
- `python3 vt520_init.py --device /dev/ttyUSB0 --baud 115200 --cols 132` (force DECCOLM wide)
- `python3 vt520_init.py --device /dev/ttyUSB0 --baud 115200 --cols 80` (force 80-column; plain ASCII on row 10, no SO/SI demo)
- `python3 vt520_init.py --device /dev/ttyUSB0 --baud 115200 --reset none` (mildest: no DECSTR/RIS before clear)
- `python3 vt520_init.py --device /dev/ttyUSB0 --baud 115200 --model vt520` (Wyse 160/60 path — set that personality in Setup first)

**DooM finale (figlet):** By default, after init + visual test the script **clears the screen** and draws a **centered ASCII “DooM”** using `figlet` (tries fonts `block`, `big`, `shadow`, … — `block` is the chunky default). Pure **7-bit ASCII** so it is safe on serial; **`toilet` is not used** (its output is often UTF-8 / ANSI). Install on Debian/Ubuntu: `sudo apt install figlet`. Optional community packs add `doom.flf` and others. Flags: `--skip-doom-finale`, `--screen-rows N` (match Setup lines/screen for vertical centering), `--doom-text "DooM"`.

Note on pseudo-graphics:

- In **DEC** personality: Special Graphics (`ESC ) 0`, SO/SI) and DECCOLM are the usual building blocks.
- In **WYSE 160/60** personality: four font banks + Wyse control set is the better base for many simultaneous custom glyphs (the DOOM plan above).
