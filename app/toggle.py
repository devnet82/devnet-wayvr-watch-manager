#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_CONFIG_DIR = Path.home() / ".config" / "devnet-wayvr-watch-manager"
HIDDEN_STATE = APP_CONFIG_DIR / "section-hidden"

def wayvrctl_path():
    return os.environ.get("DEVNET_WAYVRCTL") or shutil.which("wayvrctl")

def send(commands):
    ctl = wayvrctl_path()
    if not ctl:
        print("devnet-wayvr-watch-toggle: wayvrctl not found", file=sys.stderr)
        return 127
    payload = "\n".join(commands) + "\n"
    try:
        result = subprocess.run(
            [ctl, "batch"],
            input=payload,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"devnet-wayvr-watch-toggle: {error}", file=sys.stderr)
        return 1
    if result.returncode != 0 and result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode

def main():
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if HIDDEN_STATE.exists():
        commands = [
            "panel-modify watch devnet_extra_root set-visible 1",
            "panel-modify watch devnet_toggle_label set-text 'PC-'",
        ]
        rc = send(commands)
        if rc == 0:
            HIDDEN_STATE.unlink(missing_ok=True)
        return rc

    commands = [
        "panel-modify watch devnet_extra_root set-visible 0",
        "panel-modify watch devnet_toggle_label set-text 'PC+'",
    ]
    rc = send(commands)
    if rc == 0:
        HIDDEN_STATE.touch()
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
