#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from watchlib import load_config, watch_override_loaded, wayvr_running, wayvrctl_path

ADB_TARGET_CACHE = Path.home() / ".config" / "devnet-wayvr-watch-manager" / "adb-target"

def adb_path():
    override = os.environ.get("DEVNET_ADB")
    if override:
        return override
    return shutil.which("adb") or ("/usr/bin/adb" if Path("/usr/bin/adb").exists() else None)

class QuestControllerBatteryReader:
    """Low-rate Quest controller battery reader using Android OVRRemoteService.

    ADB is deliberately polled much more slowly than PC metrics. The last good
    values are cached briefly so a momentary wireless hiccup does not make the
    watch flicker. A previously seen TCP target is also cached and reconnected
    automatically if the host ADB server restarts.
    """
    def __init__(self, refresh_seconds=30.0, stale_seconds=300.0):
        self.refresh_seconds = float(refresh_seconds)
        self.stale_seconds = float(stale_seconds)
        self.last_attempt = 0.0
        self.last_success = 0.0
        self.left = None
        self.right = None
        self.target = None

    def _run(self, argv, timeout=3.0):
        try:
            return subprocess.run(
                argv, text=True, capture_output=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _targets(self, adb):
        result = self._run([adb, "devices"], timeout=2.5)
        if not result or result.returncode != 0:
            return []
        targets = []
        for line in result.stdout.splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 2 and fields[1] == "device":
                targets.append(fields[0])
        # Prefer wireless TCP ADB, then USB.
        return sorted(targets, key=lambda value: (":" not in value, value))

    def _cached_tcp_target(self):
        try:
            value = ADB_TARGET_CACHE.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value if ":" in value else None

    def _remember_target(self, target):
        if ":" not in target:
            return
        try:
            ADB_TARGET_CACHE.parent.mkdir(parents=True, exist_ok=True)
            ADB_TARGET_CACHE.write_text(target + "\n", encoding="utf-8")
        except OSError:
            pass

    def _try_reconnect(self, adb):
        target = self._cached_tcp_target()
        if not target:
            return
        self._run([adb, "connect", target], timeout=3.0)

    @staticmethod
    def _parse(text):
        values = {"left": None, "right": None}
        # Quest OVRRemoteService emits one Paired-device record per controller.
        # Parse line-by-line so one controller record cannot bleed into another.
        for line in text.splitlines():
            side = re.search(r"\bType:\s*(Left|Right)\b", line, flags=re.I)
            battery = re.search(r"\bBattery:\s*(\d{1,3})%", line, flags=re.I)
            if not side or not battery:
                continue
            percent = max(0, min(100, int(battery.group(1))))
            values[side.group(1).lower()] = percent
        return values

    def read(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_attempt < self.refresh_seconds:
            return {"left": self.left, "right": self.right, "target": self.target}
        self.last_attempt = now

        adb = adb_path()
        if not adb:
            if self.last_success and now - self.last_success > self.stale_seconds:
                self.left = self.right = self.target = None
            return {"left": self.left, "right": self.right, "target": self.target}

        targets = self._targets(adb)
        if not targets:
            self._try_reconnect(adb)
            targets = self._targets(adb)

        for target in targets:
            result = self._run(
                [adb, "-s", target, "shell", "dumpsys", "OVRRemoteService"],
                timeout=4.0,
            )
            if not result or result.returncode != 0:
                continue
            parsed = self._parse(result.stdout)
            if parsed["left"] is None and parsed["right"] is None:
                continue
            self.left = parsed["left"]
            self.right = parsed["right"]
            self.target = target
            self.last_success = now
            self._remember_target(target)
            return {"left": self.left, "right": self.right, "target": self.target}

        if self.last_success and now - self.last_success > self.stale_seconds:
            self.left = self.right = self.target = None
        return {"left": self.left, "right": self.right, "target": self.target}

def controller_battery_text(value):
    return f"{int(value)}%" if value is not None else "--%"

class CpuUsageSampler:
    def __init__(self):
        self.prev = None

    def read(self):
        try:
            line = Path("/proc/stat").read_text().splitlines()[0]
            values = [int(x) for x in line.split()[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            total = sum(values)
        except Exception:
            return None
        current = (idle, total)
        if self.prev is None:
            self.prev = current
            return None
        idle_delta = idle - self.prev[0]
        total_delta = total - self.prev[1]
        self.prev = current
        if total_delta <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))

def _read_int(path: Path):
    try:
        return int(path.read_text().strip())
    except Exception:
        return None

def _hwmon_entries():
    for path in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            name = (path / "name").read_text().strip()
        except Exception:
            continue
        yield path, name

def cpu_temp_c():
    candidates = []
    for path, name in _hwmon_entries():
        if name not in ("k10temp", "zenpower") and "cpu" not in name.lower():
            continue
        for temp_file in path.glob("temp*_input"):
            label_file = temp_file.with_name(temp_file.name.replace("_input", "_label"))
            try:
                label = label_file.read_text().strip().lower()
            except Exception:
                label = ""
            value = _read_int(temp_file)
            if value is None:
                continue
            degrees = value / 1000.0
            rank = 0 if any(token in label for token in ("tctl", "tdie", "package")) else 1
            candidates.append((rank, degrees))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]

def amd_gpu_paths():
    found = []
    for card in Path("/sys/class/drm").glob("card*"):
        device = card / "device"
        try:
            vendor = (device / "vendor").read_text().strip().lower()
        except Exception:
            vendor = ""
        for hwmon in (device / "hwmon").glob("hwmon*"):
            try:
                name = (hwmon / "name").read_text().strip()
            except Exception:
                name = ""
            if name == "amdgpu" or vendor == "0x1002":
                found.append((device, hwmon))
    return found

def gpu_temp_c():
    for device, hwmon in amd_gpu_paths():
        value = _read_int(hwmon / "temp1_input")
        if value is not None:
            return value / 1000.0
    return None

def gpu_usage_percent():
    for device, _ in amd_gpu_paths():
        value = _read_int(device / "gpu_busy_percent")
        if value is not None:
            return float(value)
    return None

def vram_usage_percent():
    for device, _ in amd_gpu_paths():
        used = _read_int(device / "mem_info_vram_used")
        total = _read_int(device / "mem_info_vram_total")
        if used is not None and total:
            return 100.0 * used / total
    return None

def ram_usage_percent():
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0])
        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
        return 100.0 * (total - available) / total if total else None
    except Exception:
        return None

def uptime_text():
    try:
        seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:
        return "--"
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes:02d}"
    return f"{minutes}m"

def latest_hmd_battery(log_path=Path("/tmp/wayvr.log")):
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 131072))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    matches = re.findall(r"role\s+Hmd:\s+(\d+)%", text, flags=re.I)
    return int(matches[-1]) if matches else None

def collect_metrics(cpu_sampler: CpuUsageSampler, quest_reader=None, include_quest=False):
    values = {
        "cpu_temp": cpu_temp_c(),
        "cpu_usage": cpu_sampler.read(),
        "gpu_temp": gpu_temp_c(),
        "gpu_usage": gpu_usage_percent(),
        "ram_usage": ram_usage_percent(),
        "vram_usage": vram_usage_percent(),
        "uptime": uptime_text(),
    }
    if include_quest and quest_reader is not None:
        quest = quest_reader.read()
        values["quest_left_battery"] = quest.get("left")
        values["quest_right_battery"] = quest.get("right")
        values["quest_adb_target"] = quest.get("target")
    return values

def metric_text(key, value):
    if key == "cpu_temp":
        return f"CPU {value:.0f}°C" if value is not None else "CPU --°C"
    if key == "gpu_temp":
        return f"GPU {value:.0f}°C" if value is not None else "GPU --°C"
    if key == "cpu_usage":
        return f"CPU {value:.0f}%" if value is not None else "CPU --%"
    if key == "gpu_usage":
        return f"GPU {value:.0f}%" if value is not None else "GPU --%"
    if key == "ram_usage":
        return f"RAM {value:.0f}%" if value is not None else "RAM --%"
    if key == "vram_usage":
        return f"VRAM {value:.0f}%" if value is not None else "VRAM --%"
    if key == "uptime":
        return f"UP {value}"
    return str(value)

def tz_text(item):
    zone = item.get("zone", "")
    if not zone:
        return None
    try:
        tz = ZoneInfo(zone)
    except ZoneInfoNotFoundError:
        return f"{item.get('label') or zone} INVALID"
    label = item.get("label") or zone.rsplit("/", 1)[-1].replace("_", " ")
    return f"{label} {datetime.now(tz).strftime('%H:%M')}"

def command_set_visible(element, visible):
    return f"panel-modify watch {element} set-visible {1 if visible else 0}"

def command_set_text(element, text):
    return f"panel-modify watch {element} set-text {shlex.quote(str(text))}"

def build_commands(cfg, values, initialize_section=False):
    show_quest_controllers = bool(cfg.get("show_quest_controller_batteries", True))
    commands = [
        command_set_visible("devices_root", cfg.get("show_devices", True)),
        command_set_visible("devnet_quest_controller_root", show_quest_controllers),
        command_set_visible("devnet_quest_left_box", show_quest_controllers),
        command_set_visible("devnet_quest_right_box", show_quest_controllers),
        command_set_text("devnet_quest_left_battery", controller_battery_text(values.get("quest_left_battery"))),
        command_set_text("devnet_quest_right_battery", controller_battery_text(values.get("quest_right_battery"))),
        command_set_visible("devnet_local_dow", cfg.get("show_local_day", True)),
        command_set_visible("devnet_local_date", cfg.get("show_local_date", True)),
        command_set_visible("devnet_stock_timezones", cfg.get("show_stock_timezones", True)),
    ]

    enabled_metrics = []
    metric_cfg = cfg.get("metrics", {})
    for key in cfg.get("metric_order", []):
        if metric_cfg.get(key, False) and key not in enabled_metrics:
            enabled_metrics.append(key)
    for key, enabled in metric_cfg.items():
        if enabled and key not in enabled_metrics:
            enabled_metrics.append(key)
    enabled_metrics = enabled_metrics[:8]

    for index in range(8):
        visible = index < len(enabled_metrics)
        if visible:
            key = enabled_metrics[index]
            commands.append(command_set_text(f"devnet_metric_{index}", metric_text(key, values.get(key))))
        commands.append(command_set_visible(f"devnet_metric_{index}", visible))
    for row in range(4):
        commands.append(command_set_visible(f"devnet_metric_row_{row}", row * 2 < len(enabled_metrics)))

    timezone_items = [
        item for item in cfg.get("timezones", [])
        if item.get("enabled", True) and item.get("zone")
    ][:4]
    for index in range(4):
        visible = index < len(timezone_items)
        if visible:
            commands.append(command_set_text(f"devnet_tz_{index}", tz_text(timezone_items[index]) or ""))
        commands.append(command_set_visible(f"devnet_tz_{index}", visible))
    for row in range(2):
        commands.append(command_set_visible(f"devnet_tz_row_{row}", row * 2 < len(timezone_items)))

    show_ipd = bool(cfg.get("show_ipd"))
    show_timer = bool(cfg.get("show_timer"))
    commands.extend([
        command_set_visible("devnet_ipd_box", show_ipd),
        command_set_visible("devnet_timer_box", show_timer),
        command_set_visible("devnet_native_row", show_ipd or show_timer),
    ])

    any_extra = bool(enabled_metrics or timezone_items or show_ipd or show_timer)

    # Keep the compact PC +/- toggle available whenever there is anything to show.
    commands.append(command_set_visible("devnet_toggle_root", any_extra))

    # Do not force the section visible every second: the in-VR PC- button must be
    # allowed to keep it hidden. We initialise it when WayVR starts / config
    # changes, and always hide it when there is nothing enabled.
    if initialize_section:
        commands.append(command_set_visible("devnet_extra_root", any_extra))
        commands.append(command_set_text("devnet_toggle_label", "PC-"))
    elif not any_extra:
        commands.append(command_set_visible("devnet_extra_root", False))

    return commands

def send_batch(commands, dry_run=False):
    payload = "\n".join(commands) + "\n"
    if dry_run:
        sys.stdout.write(payload)
        return 0
    ctl = wayvrctl_path()
    if not ctl:
        return 127
    try:
        result = subprocess.run(
            [ctl, "batch"], input=payload, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3, check=False
        )
        return result.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1

def run_once(cpu_sampler, quest_reader=None, dry_run=False, force=False, initialize_section=False):
    cfg = load_config()

    if initialize_section and not dry_run:
        hidden_state = Path.home() / ".config" / "devnet-wayvr-watch-manager" / "section-hidden"
        try:
            hidden_state.unlink()
        except FileNotFoundError:
            pass

    values = collect_metrics(
        cpu_sampler, quest_reader, include_quest=bool(cfg.get("show_quest_controller_batteries", True))
    )
    if values.get("cpu_usage") is None:
        time.sleep(0.12)
        values["cpu_usage"] = cpu_sampler.read()
    commands = build_commands(cfg, values, initialize_section=initialize_section)
    if dry_run or force:
        return send_batch(commands, dry_run=dry_run)
    if wayvr_running() and watch_override_loaded():
        return send_batch(commands, dry_run=False)
    return 0

def main():
    parser = argparse.ArgumentParser(description="Devnet WayVR watch metrics bridge")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="try wayvrctl even if pgrep does not see WayVR")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    sampler = CpuUsageSampler()
    quest_reader = QuestControllerBatteryReader()
    if args.once:
        raise SystemExit(
            run_once(
                sampler,
                quest_reader,
                dry_run=args.dry_run,
                force=args.force,
                initialize_section=True,
            )
        )

    sampler.read()
    last_pid = None
    last_any_extra = None
    while True:
        try:
            cfg = load_config()
            metric_cfg = cfg.get("metrics", {})
            any_extra = bool(
                any(metric_cfg.values())
                or any(item.get("enabled", True) and item.get("zone") for item in cfg.get("timezones", []))
                or cfg.get("show_ipd")
                or cfg.get("show_timer")
            )
            current_pid = None
            if wayvr_running():
                try:
                    current_pid = int(
                        subprocess.check_output(
                            ["pgrep", "-n", "-x", "wayvr"],
                            text=True,
                            timeout=1,
                        ).strip()
                    )
                except Exception:
                    current_pid = None

            initialize_section = (
                current_pid is not None
                and (
                    current_pid != last_pid
                    or (last_any_extra is False and any_extra is True)
                )
            )
            run_once(
                sampler,
                quest_reader,
                dry_run=args.dry_run,
                force=args.force,
                initialize_section=initialize_section,
            )
            last_pid = current_pid
            last_any_extra = any_extra
        except Exception as error:
            print(f"devnet-wayvr-watch-metrics: {error}", file=sys.stderr)
        time.sleep(max(0.5, args.interval))

if __name__ == "__main__":
    main()
