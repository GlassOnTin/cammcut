# cammcut

Cut SVG files on a Roland CAMM-1 vinyl cutter from Linux, over a cheap
USB-to-Centronics adapter. Developed and verified against a CX-24 with a
Prolific PL2305 adapter (067b:2305); other CAMM-1 models speak the same
CAMM-GL III language but are untested.

```
python3 -m cammcut.cammcut cut design.svg --speed 5
```

## Requirements

- Python 3 with [`svgelements`](https://pypi.org/project/svgelements/)
  (`pip install svgelements`); `pytest` to run the tests
- The cutter connected through a USB-parallel adapter bound by the
  kernel's `usblp` driver (`/dev/usb/lpN`)

## Device setup

The Prolific PL2305 appears as a bidirectional printer device. Two setup
steps make it usable without root and one rule keeps it working.

**1. udev rules** — so the node is group-accessible:

```
sudo setup/install-udev-rules.sh
```

This installs `99-roland-cutter.rules` (both the raw `usb` node and the
`usbmisc` node need a rule; they are owned independently), reloads udev
and retriggers existing nodes. `cammcut devices` should now list
`/dev/usb/lpN`.

**2. Never read from the device.** The tool is write-only by design. A
read leaves the PL2305's bulk endpoints stalled (-EPIPE); `usblp` does
not clear the halt, and every write after that is silently swallowed —
the machine just ignores you. There is no error anywhere except in
`dmesg`:

```
usblp7: nonzero read bulk status received: -32
```

**3. Recovery** — if the adapter reaches that state (writes succeed,
machine does nothing, no error on the machine's display):

```
sudo setup/unstick-adapter.sh
```

This cycles the `usblp` driver on the interface, which clears the stall.
No replug needed.

## Cutting

Machine side: load material, press SETUP until the display shows
`SETUP <ON>`, move the origin with the position keys and ORIGIN SET.
Blade force is the front-panel slider; blade offset is a machine menu
setting (0.25 mm for the standard blade) — the CX-24 firmware does the
corner compensation itself.

```
python3 -m cammcut.cammcut cut design.svg [options]

  --speed CM/S      cutting speed (VS command), default 5
  --x MM --y MM     offset of the artwork's bottom-left corner from
                    the machine origin
  --scale FACTOR    scale the artwork
  --mirror          mirror horizontally, for cutting face-down
  --device DEV      override the usblp node (default: auto-detect
                    the PL2305)
  --dry-run FILE    write the CAMM-GL stream to FILE instead

python3 -m cammcut.cammcut preview design.svg -o p.svg   # toolpath SVG
python3 -m cammcut.cammcut probe                         # 200 invalid bytes;
                                                         # expect Er1 on the
                                                         # machine display
python3 -m cammcut.cammcut devices
```

The artwork's bottom-left corner lands on the machine origin; +x is
right, +y is up (SVG's y-down is flipped for you). Artwork outside the
CX-24 cutting area (584 mm wide) draws a warning.

If the machine shows `Er1: Wrong Cmd`, it received data it could not
parse — that is also what `probe` relies on to prove the transport
works end to end.

## Protocol notes

CAMM-GL III mode 2 (HPGL-compatible) over the parallel port: `IN;` to
initialize, `VS<n>;` speed, one `PU x,y;` then a single `PD x,y,x,y,…;`
run per subpath. One HPGL unit is 0.025 mm. `SP` is not supported on
the CX-24 (single tool, ignored). Curves are flattened to polylines at
0.1 mm chord tolerance — well below blade-width error.

## Limitations

- `<text>` must be converted to outlines first (Inkscape: Path →
  Object to Path); the tool refuses with that message.
- Crop marks / print-then-cut alignment is not implemented.
- Only verified over the PL2305 adapter to a CX-24. The never-read
  constraint has not been checked on other adapters.
- Writes have no completion feedback; the kernel blocks when the
  adapter's buffer fills, so the sender self-paces, but the machine
  never acknowledges anything back over this path.

## Tests

```
python3 -m pytest tests/
```

Golden tests cover squares, lines, arcs, group transforms, subpaths,
mirroring, offset and scale against exact expected CAMM-GL strings.

## License

AGPL-3.0 — see [LICENSE](LICENSE).