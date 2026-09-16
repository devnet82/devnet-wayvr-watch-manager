#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

APP_NAME = "devnet-wayvr-watch-manager"
APP_VERSION = "0.1.14"
BASE_WAYVR_VERSION = "26.8.0"
MARKER = "DEVNET_WAYVR_WATCH_MANAGER"

HOME = Path.home()
WAYVR_CONFIG = HOME / ".config" / "wayvr"
APP_CONFIG_DIR = HOME / ".config" / APP_NAME
CONFIG_PATH = APP_CONFIG_DIR / "config.json"
STATE_PATH = APP_CONFIG_DIR / "state.json"
APP_DIR = Path(__file__).resolve().parent
CONTROLLER_ASSETS = ("devnet-controller_l.svg", "devnet-controller_r.svg")

CONTROLLER_LEFT_TOKEN = "__DEVNET_CONTROLLER_L_ABS__"
CONTROLLER_RIGHT_TOKEN = "__DEVNET_CONTROLLER_R_ABS__"

def render_watch_text(source: Path, target: Path) -> str:
    """Render packaged watch.xml for the actual filesystem target."""
    text = source.read_text(encoding="utf-8")
    replacements = {
        CONTROLLER_LEFT_TOKEN: str((target.parent / CONTROLLER_ASSETS[0]).resolve()),
        CONTROLLER_RIGHT_TOKEN: str((target.parent / CONTROLLER_ASSETS[1]).resolve()),
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text

DEFAULT_CONFIG = {
    "schema": 1,
    "show_devices": True,
    "show_local_day": True,
    "show_local_date": True,
    "show_stock_timezones": True,
    "show_quest_controller_batteries": True,
    "metrics": {
        "cpu_temp": False,
        "cpu_usage": False,
        "gpu_temp": False,
        "gpu_usage": False,
        "ram_usage": False,
        "vram_usage": False,
        "uptime": False,
    },
    "metric_order": ["gpu_temp", "gpu_usage", "cpu_temp", "cpu_usage", "vram_usage", "ram_usage", "uptime"],
    "timezones": [],
    "show_ipd": False,
    "show_timer": False,
    "preview_mode": "wrist",
}

def ensure_dirs() -> None:
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return json.loads(json.dumps(default))

def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def ensure_default_config() -> dict:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_json(CONFIG_PATH, DEFAULT_CONFIG)
    return load_config()

def load_config() -> dict:
    ensure_dirs()
    cfg = load_json(CONFIG_PATH, {})
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update({k: v for k, v in cfg.items() if k != "metrics"})
    if isinstance(cfg.get("metrics"), dict):
        merged["metrics"].update(cfg["metrics"])
    return merged

def save_config(cfg: dict) -> None:
    ensure_dirs()
    save_json(CONFIG_PATH, cfg)

def _extract_theme_path(text: str):
    # JSON5/YAML-ish forms used in WayVR conf.d. Ignore comment-only lines.
    cleaned = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith(("#", "//"))
    )
    patterns = [
        r'["\']?theme_path["\']?\s*:\s*["\']([^"\']+)["\']',
        r'theme_path\s*:\s*["\']?([^"\'\s,#}]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(1).strip()
    return None

def detect_theme_path() -> str:
    # WayVR's built-in default is "theme".
    theme = "theme"
    confd = WAYVR_CONFIG / "conf.d"
    if confd.is_dir():
        for path in sorted(confd.iterdir()):
            if not path.is_file():
                continue
            try:
                found = _extract_theme_path(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if found:
                theme = found
    return theme

def watch_target() -> Path:
    theme = Path(detect_theme_path())
    if theme.is_absolute():
        return theme / "gui" / "watch.xml"
    return WAYVR_CONFIG / theme / "gui" / "watch.xml"

def load_state() -> dict:
    return load_json(STATE_PATH, {})

def save_state(state: dict) -> None:
    save_json(STATE_PATH, state)

def is_our_watch(path: Path | None = None) -> bool:
    path = path or watch_target()
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

def install_watch(source: Path) -> dict:
    ensure_dirs()
    target = watch_target()
    target.parent.mkdir(parents=True, exist_ok=True)
    state = load_state()

    # Back up a pre-existing non-Devnet override once.
    if target.exists() and not is_our_watch(target) and not state.get("pre_devnet_watch_backup"):
        backup_dir = APP_CONFIG_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"watch.xml.pre-devnet-{stamp}"
        shutil.copy2(target, backup)
        state["pre_devnet_watch_backup"] = str(backup)

    # Keep the stock WayVR watch in its proven path mode. Only the two Devnet
    # controller SVGs are filesystem assets, rendered as explicit absolute paths.
    for asset_name in CONTROLLER_ASSETS:
        asset_source = APP_DIR / asset_name
        if not asset_source.is_file():
            raise FileNotFoundError(f"missing packaged controller asset: {asset_source}")
        shutil.copy2(asset_source, target.parent / asset_name)

    rendered = render_watch_text(source, target)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    os.replace(tmp, target)
    state["watch_target"] = str(target)
    state["installed_version"] = APP_VERSION
    state["base_wayvr_version"] = BASE_WAYVR_VERSION
    save_state(state)
    return {"target": str(target), "backup": state.get("pre_devnet_watch_backup")}

def restore_watch() -> dict:
    target = watch_target()
    state = load_state()
    backup = state.get("pre_devnet_watch_backup")
    action = "nothing to restore"

    if backup and Path(backup).is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        action = f"restored previous override: {backup}"
        state.pop("pre_devnet_watch_backup", None)
    elif target.exists() and is_our_watch(target):
        target.unlink()
        action = "removed Devnet override; WayVR will fall back to its built-in standard watch"

    for asset_name in CONTROLLER_ASSETS:
        try:
            (target.parent / asset_name).unlink()
        except FileNotFoundError:
            pass

    state["restored_at"] = int(time.time())
    save_state(state)
    return {"target": str(target), "action": action}

def command_output(argv, timeout=2.0) -> str:
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
        return (result.stdout or result.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

def wayvr_version() -> str:
    out = command_output(["wayvr", "--version"])
    match = re.search(r"(\d+\.\d+\.\d+)", out)
    return match.group(1) if match else (out or "not found")

def wayvr_pid():
    out = command_output(["pgrep", "-n", "-x", "wayvr"], timeout=1)
    try:
        return int(out.splitlines()[-1])
    except (ValueError, IndexError):
        return None

def wayvr_running() -> bool:
    return wayvr_pid() is not None

def watch_override_loaded() -> bool:
    """Best-effort check that the running WayVR started after our watch.xml was written."""
    if not is_our_watch():
        return False
    pid = wayvr_pid()
    if pid is None:
        return False
    try:
        process_started = Path(f"/proc/{pid}").stat().st_ctime
        watch_written = watch_target().stat().st_mtime
    except OSError:
        return False
    return process_started >= (watch_written - 0.5)

def wayvrctl_path():
    override = os.environ.get("DEVNET_WAYVRCTL")
    if override:
        return override
    return shutil.which("wayvrctl") or ("/usr/bin/wayvrctl" if Path("/usr/bin/wayvrctl").exists() else None)

def wayvrctl_available() -> bool:
    return wayvrctl_path() is not None

def probe_hook() -> bool:
    # wayvrctl panel-modify is fire-and-forget and cannot reliably report a
    # missing element. Compare process start time to watch.xml instead.
    return watch_override_loaded()

def status() -> dict:
    return {
        "app_version": APP_VERSION,
        "base_wayvr_version": BASE_WAYVR_VERSION,
        "wayvr_version": wayvr_version(),
        "wayvr_running": wayvr_running(),
        "wayvrctl": wayvrctl_available(),
        "theme_path": detect_theme_path(),
        "watch_target": str(watch_target()),
        "our_watch_installed": is_our_watch(),
        "hook_loaded": probe_hook(),
    }

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    install = sub.add_parser("install-watch")
    install.add_argument("--source", required=True)
    sub.add_parser("restore-watch")
    sub.add_parser("status")
    sub.add_parser("theme-path")
    sub.add_parser("init-config")
    args = parser.parse_args()

    if args.cmd == "install-watch":
        print(json.dumps(install_watch(Path(args.source)), indent=2))
    elif args.cmd == "restore-watch":
        print(json.dumps(restore_watch(), indent=2))
    elif args.cmd == "status":
        print(json.dumps(status(), indent=2))
    elif args.cmd == "theme-path":
        print(detect_theme_path())
    elif args.cmd == "init-config":
        print(json.dumps(ensure_default_config(), indent=2))

if __name__ == "__main__":
    main()
