"""Device discovery and output sinks.

The transport is write-only (see cammcut.cammcut.send): a read stalls the
PL2305 and every later write is silently swallowed. Sinks therefore only
write, report progress per chunk, and honour a cancel check between chunks.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from ...cammcut import _node_vid_pid, find_devices
from ..schemas import DeviceInfo

# sink(device_path, data, on_progress, is_cancelled)
Sink = Callable[[str, bytes, Callable[[int], None], Callable[[], bool]], None]

# Pseudo-device for demo mode: jobs routed here never touch hardware.
DEMO_DEVICE = "demo"


def list_devices(include_demo: bool = False) -> list[DeviceInfo]:
    out = []
    for node in find_devices():
        vid, pid = _node_vid_pid(node)
        out.append(
            DeviceInfo(
                path=node,
                vid=vid or "",
                pid=pid or "",
                exists=True,
                writable=os.access(node, os.W_OK),
            )
        )
    if include_demo:
        out.append(DeviceInfo(path=DEMO_DEVICE, vid="", pid="", exists=True, writable=True))
    return out


def resolve(settings_device: str | None) -> str:
    from ...cammcut import resolve_device

    return resolve_device(settings_device)


def _usblp_kernel_name(device_path: str) -> str | None:
    """/dev/usb/lp7 -> usblp7 (the name the kernel logs use)."""
    base = Path(device_path).name
    return "usblp" + base[2:] if base.startswith("lp") else None


def stall_detected(device_path: str, since_ts: float) -> bool:
    """Kernel-side stall signal: usblp logs 'nonzero ... bulk status received:
    -32' (-EPIPE) when the adapter's endpoints are halted. We look for such a
    line in the current boot's kernel journal, after since_ts (the marker of
    the last successful unstick — old messages mean a stall that is already
    fixed). Returns True when detection itself is impossible, so the caller
    falls back to always clearing: writes into a stalled adapter succeed
    silently, so clearing again is the safe default. journalctl exits 1 when
    the grep matches nothing — that is a confident "no stall", not a failure
    (getting this wrong cycles the adapter on every job).
    """
    name = _usblp_kernel_name(device_path)
    if name is None:
        return True
    try:
        r = subprocess.run(
            ["journalctl", "-kq", "--no-pager", "--since", "@%d" % int(since_ts),
             "--grep", r"%s: nonzero \w+ bulk status received: -32" % name],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    if r.returncode == 1:
        return False  # journalctl: no lines matched
    if r.returncode != 0:
        return True
    return bool(r.stdout.strip())


def wait_openable(path: str, timeout: float = 5.0) -> None:
    """Block until the node can be opened for writing. After unstick's
    `bind`, udev applies the plugdev rule asynchronously: measured, the node
    can still be root:root 0600 when the script returns, and an immediate
    open fails with EACCES. Polls with a real open (harmless — nothing is
    written) and re-raises the last PermissionError on timeout."""
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(path, os.O_WRONLY)
        except PermissionError:
            if time.time() >= deadline:
                raise
            time.sleep(0.1)
            continue
        os.close(fd)
        return


def unstick() -> str:
    """Cycle the usblp driver on the PL2305 to clear an endpoint stall.

    Writing to sysfs needs root. Run as root directly, or through `sudo -n`
    which requires a NOPASSWD rule (see setup/sudoers-cammcut). An
    unprivileged clear-halt ioctl path was tested and rejected: clearing the
    halt works without root, but re-attaching usblp does not — the kernel
    never re-probes, leaving /dev/usb/lpN missing.
    """
    script = Path(__file__).resolve().parents[3] / "setup" / "unstick-adapter.sh"
    if not script.exists():
        raise RuntimeError("unstick script not found: %s" % script)
    cmd = [str(script)] if os.geteuid() == 0 else ["sudo", "-n", str(script)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError("could not run unstick-adapter.sh: %s" % e) from e
    if r.returncode != 0:
        detail = (r.stderr or r.stdout).strip() or "exit code %d" % r.returncode
        if "password is required" in detail:
            detail += " — install the NOPASSWD rule (setup/sudoers-cammcut) " \
                      "so the runner can clear stalls automatically"
        raise RuntimeError(detail)
    return (r.stdout or "").strip() or "adapter stall cleared"


def real_sink(device: str, data: bytes, on_progress: Callable[[int], None],
              is_cancelled: Callable[[], bool]):
    """Chunked write-only stream with progress + cancel."""
    fd = os.open(device, os.O_WRONLY)
    try:
        sent = 0
        for i in range(0, len(data), 4096):
            if is_cancelled():
                raise CancelledError()
            sent += os.write(fd, data[i:i + 4096])
            on_progress(sent)
    finally:
        os.close(fd)


def file_sink(path: Path) -> Sink:
    """Dry-run/test sink: same interface, writes to a file."""

    def sink(_device: str, data: bytes, on_progress: Callable[[int], None],
             is_cancelled: Callable[[], bool]):
        with open(path, "wb") as f:
            sent = 0
            for i in range(0, len(data), 4096):
                if is_cancelled():
                    raise CancelledError()
                sent += f.write(data[i:i + 4096])
                on_progress(sent)

    return sink


class CancelledError(Exception):
    pass


def demo_sink() -> Sink:
    """Mock cutter for user testing without hardware.

    Same interface as the real sink, but bytes are paced out in real time
    so the progress bar behaves like a cut. The pace approximates a cut and
    is not the machine's timing. The exact stream is still saved as the
    job artifact by the runner, so demo jobs can be inspected like real
    ones.
    """
    import time

    def sink(_device: str, data: bytes, on_progress: Callable[[int], None],
             is_cancelled: Callable[[], bool]):
        duration = min(20.0, max(2.0, len(data) / 1500.0))
        step = max(1, len(data) // 30)
        delay = duration / 30.0
        sent = 0
        while sent < len(data):
            if is_cancelled():
                raise CancelledError()
            time.sleep(delay)
            sent = min(len(data), sent + step)
            on_progress(sent)

    return sink


class DeviceBusy(Exception):
    pass


def sink_from_env() -> tuple[Sink, str | None]:
    """CAMMCUT_DRY_RUN=1 routes jobs to a file instead of the machine."""
    import sys

    if os.environ.get("CAMMCUT_DRY_RUN"):
        from .. import settings

        target = settings.subdir("jobs") / "dry-run.hpgl"

        def dry(_device: str, data: bytes, on_progress, _cancel):
            target.write_bytes(data)
            on_progress(len(data))
            print("dry-run: wrote %d bytes to %s" % (len(data), target), file=sys.stderr)

        return dry, "dry-run"
    return real_sink, None