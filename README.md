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
- For the web app's tracing feature: `potrace` (`sudo apt install
  potrace`). Everything else in the web app works without it.

## Web app

The repo also contains a browser workspace for preparing cuts, served by
a FastAPI backend on the same machine that talks to the cutter:

```
.venv/bin/python -m cammcut.web   # or: uvicorn cammcut.web.app:create_app --factory --host 0.0.0.0 --port 8799
```

The backend serves the built frontend (`web/` is a Vite + React project;
`cd web && npm run build` writes to `cammcut/web/static/`, which the
backend serves — with `npm run dev` for hot reload during development).
Open `http://<host>:8799` from any machine on the subnet.

`python -m cammcut.web` serves **TLS on the same port** with a self-signed
certificate generated on first run into `data/tls/` (10 years, SANs for
the hostnames and current IPv4 addresses of the machine). Browsers that
upgrade `http://` to `https://` automatically therefore land on a working
listener; the first visit shows a certificate warning to accept once.
Silence it properly on machines you control by trusting
`data/tls/cert.pem` as a CA, or use `mkcert` for your own. `CAMMCUT_TLS=off`
serves plain HTTP again.

It does what the CLI does plus document editing: layered project
storage, SVG import with warnings for text/masks, move/scale/rotate
with snapping and undo, a parametric shape library, text converted to
outline paths from the system fonts (emoji work through Unifont
glyphs), raster tracing through potrace when installed, tidy tools
(close open paths, remove duplicate points, simplify, flatten, a
self-crossing check), a cut preview with length/ETA estimates, and a
send panel with byte-based progress over SSE. Projects are saved only
when you save them: a fresh document stays a local draft (marked
"unsaved" in the toolbar) until the first explicit save, and after
that the document autosaves two seconds after the last change.

For trying the interface without a cutter attached, the cutter panel has
a **demo mode**: jobs go to a simulated device with paced progress and
the exact HPGL stream is still saved under `data/jobs/` for inspection.
The demo pace approximates a cut; it is not the machine's timing.

The trace panel can also **generate art from a text prompt** through the
nexos.ai image gateway (optional): set `CAMMCUT_NEXOS_KEY` in
`data/env.local` (`KEY=VALUE` lines, gitignored; environment variables
win) or in the service environment, restart, and a prompt/model/size
form appears above the file picker. Generation runs server-side, the
result is stored as an upload asset and auto-traced with the current
threshold, and the normal confirm flow (threshold, invert, re-trace)
takes it from there. Calls cost credits on the nexos.ai account and
take tens of seconds; the endpoint is a plain sync handler, so other
requests are served while one waits.

Two things to know:

- **No authentication.** Anyone on the subnet can send jobs to the
  cutter. That is a deliberate choice for a workshop LAN; firewall the
  port or bind to 127.0.0.1 (`--host 127.0.0.1`) if that is not
  acceptable.
- The machine connection stays write-only with one job at a time, as
  described below. "Send finished" means the bytes left the host; the
  cutter never confirms anything back.

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

**4. Automatic recovery** — the web app can clear the stall itself at the
start of a real-device job. It watches the kernel journal for the `-32`
line above (since the last successful clear) and only cycles the adapter
when a stall is actually recorded. To let it run without a password:

```
visudo -cf setup/sudoers-cammcut && \
sudo install -o root -g root -m 440 setup/sudoers-cammcut /etc/sudoers.d/cammcut
```

The rule is scoped to the unstick script itself. Without it, the job
still runs but the app reports the sudo failure on the job. Control with
`CAMMCUT_UNSTICK`: `auto` (default, journal-gated), `always`, `off`.

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