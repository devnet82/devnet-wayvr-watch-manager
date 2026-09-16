#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import metrics
import watchlib

APP_DIR = Path(__file__).resolve().parent
WATCH_SOURCE = APP_DIR / "watch.xml"
REPORT_PATH = Path.home() / ".config" / "devnet-wayvr-watch-manager" / "doctor-latest.txt"


@dataclass
class Check:
    level: str
    name: str
    detail: str

    def line(self) -> str:
        return f"[{self.level:<4}] {self.name}: {self.detail}"


def _run(argv, timeout=4.0, input_text=None):
    try:
        result = subprocess.run(
            argv,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.1f}s"
    except OSError as error:
        return 1, "", str(error)


def _sha256(path: Path):
    try:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _process_env(pid):
    if not pid:
        return {}
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    env = {}
    for item in raw.split(b"\0"):
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        try:
            env[key.decode()] = value.decode(errors="replace")
        except Exception:
            continue
    return env


def _tail_relevant_wayvr_log(path=Path("/tmp/wayvr.log"), max_lines=80):
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 256 * 1024))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    pattern = re.compile(
        r"(devnet|battery|role\s+(?:Hmd|LeftHand|RightHand)|"
        r"duplicate component|widget.*doesn.t exist|element.*doesn.t exist|"
        r"watch\.xml|failed to load|failed.*panel|panel.*modify|parse.*xml|xml.*error)",
        flags=re.I,
    )
    lines = [line for line in text.splitlines() if pattern.search(line)]
    return lines[-max_lines:]


def _watch_xml_checks(target):
    checks = []
    details = []
    if not target.exists():
        checks.append(Check("FAIL", "Watch XML", f"missing: {target}"))
        return checks, details
    try:
        root = ET.parse(target).getroot()
        checks.append(Check("PASS", "Watch XML", "parses successfully"))
    except Exception as error:
        checks.append(Check("FAIL", "Watch XML", f"parse failed: {error}"))
        return checks, details

    ids = {
        elem.attrib.get("id")
        for elem in root.iter()
        if elem.attrib.get("id")
    }
    required = [
        "devices_root",
        "devnet_quest_left_box",
        "devnet_quest_left_battery",
        "devnet_quest_right_box",
        "devnet_quest_right_battery",
        "devnet_toggle_root",
        "devnet_toggle_label",
    ]
    missing = [item for item in required if item not in ids]
    if missing:
        checks.append(Check("FAIL", "Devnet XML IDs", "missing: " + ", ".join(missing)))
    else:
        checks.append(Check("PASS", "Devnet XML IDs", "all required IDs are present"))

    # Controller battery widgets are intentionally static in v0.1.14. WayVR's
    # native LeftHand/RightHand templates remain present but must not contain the
    # Devnet battery IDs, because WiVRn does not expose controller battery_status.
    for template_name in ("LeftHand", "RightHand"):
        template = root.find(f".//template[@name='{template_name}']")
        if template is None:
            checks.append(Check("FAIL", template_name + " template", "template missing"))
        else:
            checks.append(Check("PASS", template_name + " template", "native template present"))

    if root.get("version") is None:
        checks.append(Check("PASS", "Watch XML path mode", "stock WayVR path mode retained; Devnet controller SVGs use absolute src_ext paths"))
    else:
        checks.append(Check("FAIL", "Watch XML path mode", "unexpected layout version; stock WayVR path mode must be retained"))

    installed_sha = _sha256(target)
    try:
        expected_text = watchlib.render_watch_text(WATCH_SOURCE, target)
        expected_sha = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
    except Exception:
        expected_sha = None
    details.append("Installed watch SHA256: " + (installed_sha or "unavailable"))
    details.append("Expected rendered SHA256: " + (expected_sha or "unavailable"))
    if installed_sha and expected_sha:
        if installed_sha == expected_sha:
            checks.append(Check("PASS", "Installed watch version", "matches rendered packaged v" + watchlib.APP_VERSION))
        else:
            checks.append(Check(
                "WARN",
                "Installed watch version",
                "installed watch differs from rendered packaged v" + watchlib.APP_VERSION +
                "; press Save & Apply, then restart the full VR stack"
            ))

    # v0.1.14 architecture check: controller battery IDs must be permanent static
    # elements, not inside runtime-instantiated LeftHand/RightHand templates.
    left_template = root.find(".//template[@name='LeftHand']")
    right_template = root.find(".//template[@name='RightHand']")
    in_dynamic_template = False
    for template in (left_template, right_template):
        if template is not None:
            if template.find(".//*[@id='devnet_quest_left_battery']") is not None:
                in_dynamic_template = True
            if template.find(".//*[@id='devnet_quest_right_battery']") is not None:
                in_dynamic_template = True
    static_root = root.find(".//*[@id='devnet_quest_controller_root']")
    if static_root is not None and not in_dynamic_template:
        checks.append(Check("PASS", "Controller widget architecture", "permanent static row"))
    else:
        checks.append(Check("FAIL", "Controller widget architecture", "controller widgets are not in the permanent static row"))

    asset_pairs = [
        ("devnet-controller_l.svg", WATCH_SOURCE.parent / "devnet-controller_l.svg"),
        ("devnet-controller_r.svg", WATCH_SOURCE.parent / "devnet-controller_r.svg"),
    ]
    asset_errors = []
    for filename, packaged in asset_pairs:
        installed = target.parent / filename
        if not installed.is_file():
            asset_errors.append(filename + " missing")
        elif _sha256(installed) != _sha256(packaged):
            asset_errors.append(filename + " differs from packaged asset")
    if asset_errors:
        checks.append(Check("FAIL", "Controller icon assets", "; ".join(asset_errors)))
    else:
        checks.append(Check("PASS", "Controller icon assets", "left/right SVGs installed beside watch.xml and match package"))

    controller_root = root.find(".//*[@id='devnet_quest_controller_root']")
    path_errors = []
    expected_paths = {
        "devnet_quest_left_box": str((target.parent / "devnet-controller_l.svg").resolve()),
        "devnet_quest_right_box": str((target.parent / "devnet-controller_r.svg").resolve()),
    }
    if controller_root is not None:
        for box_id, expected_path in expected_paths.items():
            box = controller_root.find(f".//*[@id='{box_id}']")
            sprite = box.find("sprite") if box is not None else None
            actual = sprite.get("src_ext") if sprite is not None else None
            if actual != expected_path:
                path_errors.append(f"{box_id}: {actual!r} != {expected_path!r}")
    else:
        path_errors.append("controller root missing")
    if path_errors:
        checks.append(Check("FAIL", "Controller icon paths", "; ".join(path_errors)))
    else:
        checks.append(Check("PASS", "Controller icon paths", "absolute src_ext paths point to installed SVGs"))
    return checks, details


def _adb_diagnostics():
    checks = []
    details = []
    adb = metrics.adb_path()
    if not adb:
        checks.append(Check("FAIL", "ADB", "adb not found"))
        return checks, details, {"left": None, "right": None, "target": None}

    checks.append(Check("PASS", "ADB executable", adb))
    rc, out, err = _run([adb, "devices"], timeout=3.0)
    details.append("adb devices:\n" + (out or err or "(no output)"))
    targets = []
    if rc == 0:
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                targets.append(parts[0])
    if targets:
        checks.append(Check("PASS", "ADB Quest connection", ", ".join(targets)))
    else:
        checks.append(Check("FAIL", "ADB Quest connection", "no authorised device"))

    reader = metrics.QuestControllerBatteryReader(refresh_seconds=0)
    values = reader.read(force=True)
    left = values.get("left")
    right = values.get("right")
    target = values.get("target")
    if left is not None and right is not None:
        checks.append(Check("PASS", "Controller battery parse", f"Left {left}%  Right {right}% via {target}"))
    elif left is not None or right is not None:
        checks.append(Check("WARN", "Controller battery parse", f"Left {left}  Right {right} via {target}"))
    else:
        checks.append(Check("FAIL", "Controller battery parse", "OVRRemoteService values not found"))

    if target:
        rc, raw, err = _run([adb, "-s", target, "shell", "dumpsys", "OVRRemoteService"], timeout=5.0)
        paired = [
            line.strip()
            for line in raw.splitlines()
            if re.search(r"\bType:\s*(?:Left|Right)\b", line, flags=re.I)
        ]
        if paired:
            details.append("OVRRemoteService controller records:\n" + "\n".join(paired))
        elif err:
            details.append("OVRRemoteService error:\n" + err)

    return checks, details, values


def _service_diagnostics():
    checks = []
    details = []
    rc, out, err = _run(
        ["systemctl", "--user", "is-active", "devnet-wayvr-watch-metrics.service"],
        timeout=3.0,
    )
    state = (out or err or "unknown").strip()
    if rc == 0 and state == "active":
        checks.append(Check("PASS", "Metrics service", "active"))
    else:
        checks.append(Check("FAIL", "Metrics service", state))

    rc, out, err = _run(
        ["systemctl", "--user", "--no-pager", "--full", "status", "devnet-wayvr-watch-metrics.service"],
        timeout=4.0,
    )
    if out or err:
        lines = (out or err).splitlines()
        details.append("Metrics service status:\n" + "\n".join(lines[-18:]))
    return checks, details


def _wayvr_diagnostics():
    checks = []
    details = []
    status = watchlib.status()

    if status["wayvr_running"]:
        checks.append(Check("PASS", "WayVR process", f"running, version {status['wayvr_version']}"))
    else:
        checks.append(Check("FAIL", "WayVR process", f"not running, version probe: {status['wayvr_version']}"))

    if status["wayvrctl"]:
        checks.append(Check("PASS", "wayvrctl", str(watchlib.wayvrctl_path())))
    else:
        checks.append(Check("FAIL", "wayvrctl", "not found"))

    if status["our_watch_installed"]:
        checks.append(Check("PASS", "Watch override", status["watch_target"]))
    else:
        checks.append(Check("FAIL", "Watch override", f"Devnet marker not found at {status['watch_target']}"))

    if status["wayvr_running"] and status["our_watch_installed"]:
        if status["hook_loaded"]:
            checks.append(Check("PASS", "Watch load timing", "running WayVR started after current watch.xml"))
        else:
            checks.append(Check("WARN", "Watch load timing", "full VR stack restart is required after Save & Apply"))

    pid = watchlib.wayvr_pid()
    env = _process_env(pid)
    if pid:
        details.append(f"WayVR PID: {pid}")
        details.append("OPENXR_RUNTIME_JSON=" + env.get("OPENXR_RUNTIME_JSON", "(not set)"))
        details.append("XR_RUNTIME_JSON=" + env.get("XR_RUNTIME_JSON", "(not set)"))

    ctl = watchlib.wayvrctl_path()
    if ctl and status["wayvr_running"]:
        rc, out, err = _run([ctl, "--pretty", "input-state"], timeout=4.0)
        if rc == 0:
            checks.append(Check("PASS", "WayVR IPC input-state", "query succeeded"))
            details.append("wayvrctl --pretty input-state:\n" + (out or "(empty)"))
        else:
            checks.append(Check("FAIL", "WayVR IPC input-state", err or out or f"exit {rc}"))

    relevant = _tail_relevant_wayvr_log()
    if relevant:
        details.append("Relevant /tmp/wayvr.log lines:\n" + "\n".join(relevant))
    else:
        details.append("Relevant /tmp/wayvr.log lines: none found")
    return checks, details, status


def _metrics_diagnostics(adb_values):
    checks = []
    details = []
    cfg = watchlib.load_config()
    sampler = metrics.CpuUsageSampler()
    sampler.read()
    values = metrics.collect_metrics(sampler)
    values["quest_left_battery"] = adb_values.get("left")
    values["quest_right_battery"] = adb_values.get("right")
    values["quest_adb_target"] = adb_values.get("target")
    commands = metrics.build_commands(cfg, values, initialize_section=True)
    battery_commands = [
        command for command in commands
        if "devnet_quest_" in command
    ]
    if any("devnet_quest_left_battery set-text" in x for x in battery_commands) and \
       any("devnet_quest_right_battery set-text" in x for x in battery_commands):
        checks.append(Check("PASS", "Metrics bridge output", "controller write commands generated"))
    else:
        checks.append(Check("FAIL", "Metrics bridge output", "controller write commands missing"))
    details.append("Controller commands generated by metrics bridge:\n" + "\n".join(battery_commands))
    return checks, details


def _likely_diagnosis(checks, status, adb_values, watch_target):
    fails = {check.name for check in checks if check.level == "FAIL"}
    warns = {check.name for check in checks if check.level == "WARN"}

    if "ADB Quest connection" in fails or "Controller battery parse" in fails:
        return "The failure is on the Quest/ADB side before WayVR."
    if ("Watch XML" in fails or "Devnet XML IDs" in fails or
            "Controller widget architecture" in fails or "Watch XML path mode" in fails or
            "Controller icon assets" in fails or "Controller icon paths" in fails):
        return "The installed watch XML or controller icon asset path is wrong. Press Save & Apply, then restart the full VR stack."
    if "Installed watch version" in warns:
        return "The installed watch.xml does not match this app version. Press Save & Apply, then restart the full VR stack."
    if "Watch load timing" in warns:
        return "The current WayVR process is older than the installed watch XML. Restart the full VR stack once."
    if "Metrics service" in fails:
        return "The background metrics service is not running."
    if "WayVR IPC input-state" in fails or "wayvrctl" in fails:
        return "WayVR IPC is not available, so live watch updates cannot be sent."
    if adb_values.get("left") is not None and adb_values.get("right") is not None:
        return (
            "ADB and parsing are good. If the controller values still do not appear, "
            "the remaining fault is inside the live WayVR watch/widget path. Use the "
            "'Live controller test' button in Doctor; it sends 77%/88% directly to "
            "the two widget IDs for five seconds."
        )
    return "No single cause was identified; use the detailed sections below."


def build_report(save=True):
    checks = []
    detail_sections = []

    way_checks, way_details, status = _wayvr_diagnostics()
    checks.extend(way_checks)
    detail_sections.extend(way_details)

    target = watchlib.watch_target()
    xml_checks, xml_details = _watch_xml_checks(target)
    checks.extend(xml_checks)
    detail_sections.extend(xml_details)

    adb_checks, adb_details, adb_values = _adb_diagnostics()
    checks.extend(adb_checks)
    detail_sections.extend(adb_details)

    service_checks, service_details = _service_diagnostics()
    checks.extend(service_checks)
    detail_sections.extend(service_details)

    bridge_checks, bridge_details = _metrics_diagnostics(adb_values)
    checks.extend(bridge_checks)
    detail_sections.extend(bridge_details)

    diagnosis = _likely_diagnosis(checks, status, adb_values, target)

    lines = [
        "Devnet WayVR Watch Doctor",
        "=" * 72,
        f"App version: {watchlib.APP_VERSION}",
        f"WayVR base used by app: {watchlib.BASE_WAYVR_VERSION}",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "SUMMARY",
        "-" * 72,
    ]
    lines.extend(check.line() for check in checks)
    lines.extend([
        "",
        "LIKELY DIAGNOSIS",
        "-" * 72,
        diagnosis,
        "",
        "DETAILS",
        "-" * 72,
        "\n\n".join(detail_sections),
        "",
    ])
    report = "\n".join(lines)

    if save:
        try:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(report + "\n", encoding="utf-8")
        except OSError:
            pass
    return report


def live_controller_test():
    ctl = watchlib.wayvrctl_path()
    if not ctl:
        return False, "wayvrctl not found"
    commands = [
        "panel-modify watch devnet_quest_left_box set-visible 1",
        "panel-modify watch devnet_quest_right_box set-visible 1",
        "panel-modify watch devnet_quest_left_battery set-text 77%",
        "panel-modify watch devnet_quest_right_battery set-text 88%",
    ]
    payload = "\n".join(commands) + "\n"
    rc, out, err = _run([ctl, "batch", "--fail-fast"], timeout=4.0, input_text=payload)
    if rc == 0:
        return True, "Sent live test: Left 77%, Right 88%. Look at the watch now."
    return False, err or out or f"wayvrctl exited {rc}"


def restore_live_values():
    try:
        sampler = metrics.CpuUsageSampler()
        reader = metrics.QuestControllerBatteryReader(refresh_seconds=0)
        rc = metrics.run_once(
            sampler,
            reader,
            dry_run=False,
            force=True,
            initialize_section=False,
        )
        return rc == 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Devnet WayVR Watch Doctor")
    parser.add_argument("--live-test", action="store_true")
    parser.add_argument("--restore-live", action="store_true")
    args = parser.parse_args()

    if args.live_test:
        ok, message = live_controller_test()
        print(message)
        raise SystemExit(0 if ok else 1)
    if args.restore_live:
        raise SystemExit(0 if restore_live_values() else 1)

    print(build_report(save=True))


if __name__ == "__main__":
    main()
