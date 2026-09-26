"""Web app settings from environment."""

import os
from pathlib import Path


def _load_env_local() -> None:
    """Load KEY=VALUE lines from data/env.local into the environment.

    Deployment secrets (e.g. the nexos.ai key) live there, outside the
    repo and outside the unit file. Real environment variables win.
    """
    data_dir = Path(os.environ.get("CAMMCUT_DATA_DIR", "data"))
    f = data_dir / "env.local"
    if not f.is_file():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env_local()

# Port 8799: uncommon, easy to firewall on purpose.
HOST = os.environ.get("CAMMCUT_HOST", "0.0.0.0")
PORT = int(os.environ.get("CAMMCUT_PORT", "8799"))
DATA_DIR = Path(os.environ.get("CAMMCUT_DATA_DIR", "data"))
DEVICE = os.environ.get("CAMMCUT_DEVICE") or None  # explicit /dev/usb/lpN
# Clear a stalled PL2305 at the start of real-device jobs: "auto" clears only
# when the kernel journal shows a stall since the last successful clear,
# "always" clears unconditionally, "off" never clears.
UNSTICK = os.environ.get("CAMMCUT_UNSTICK", "auto")
if UNSTICK not in ("auto", "always", "off"):
    UNSTICK = "auto"
# nexos.ai text→image gateway (OpenAI-compatible). The key is optional:
# the generate endpoints report "not configured" without one.
NEXOS_URL = os.environ.get("CAMMCUT_NEXOS_URL", "https://api.nexos.ai/v1").rstrip("/")
NEXOS_KEY = os.environ.get("CAMMCUT_NEXOS_KEY") or None

SUBDIRS = ("projects", "uploads", "fonts", "jobs")


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (DATA_DIR / sub).mkdir(exist_ok=True)


def subdir(name: str) -> Path:
    d = DATA_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d