from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
COMPAT_PORT = 9631
COMPAT_SCRIPT = ROOT_DIR / 'scripts' / 'lightrag_compat_server.py'


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_lightrag_service() -> None:
    if _port_open('127.0.0.1', COMPAT_PORT):
        return

    subprocess.Popen(
        [sys.executable, str(COMPAT_SCRIPT)],
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.time() + 8
    while time.time() < deadline:
        if _port_open('127.0.0.1', COMPAT_PORT):
            return
        time.sleep(0.2)
