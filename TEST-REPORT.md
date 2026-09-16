# Devnet WayVR Watch Manager v0.1.14 — Test Report

Date: 2026-09-16

## Automated functional suite

Final local run:

```text
PASS 21 tests
```

The suite covers:

- watch XML parsing and required Devnet widget IDs
- permanent controller battery widgets as siblings of WayVR's `devices_root`
- stock WayVR asset-path regression
- PC metric command generation
- PC- / PC+ runtime helper behaviour
- daemon regression preventing hidden extras from being forced open
- toggle round-trip behaviour
- Quest `OVRRemoteService` left/right battery parsing
- fake ADB target discovery and target-cache behaviour
- cached wireless ADB reconnect
- missing-ADB safe failure path
- backup/restore of a pre-existing watch override
- restore to the built-in WayVR watch when no prior override existed
- custom and commented `theme_path` handling
- metrics dry-run without and with Quest batteries
- Doctor report generation in a fake environment
- Doctor live 77% / 88% controller test command generation
- desktop preview WayVR controller SVG usage
- desktop preview WayVR HMD SVG usage

## Additional package checks

Passed during development/package validation:

- Python syntax/AST checks
- Bash syntax checks for installer/uninstaller/launch wrappers
- `watch.xml` XML parsing
- HMD/controller SVG XML parsing
- equal 126×48 HMD/left/right preview boxes
- 32×32 HMD/controller preview icons
- preservation of the known-good v0.1.12 live-watch logic through the v0.1.13/v0.1.14 preview-only changes

## Live hardware acceptance

Confirmed on the reference Quest 3 + WiVRn + WayVR 26.8.0 setup during the v0.1.12 line:

- Quest left/right controller percentages visible in the watch
- stock WayVR buttons render correctly after the icon-path recovery
- controller battery widgets remain present instead of being removed by WayVR's device-list refresh
- PC- / PC+ watch toggle works

v0.1.13 and v0.1.14 only change the desktop preview icon rendering. They do not change the working live-watch XML architecture or controller battery transport.

## Not executable in the build sandbox

- real Quest/WayVR/OpenXR rendering
- physical controller battery polling from a connected Quest
- interactive GTK rendering on the user's desktop

Those areas require the real VR/desktop environment and are not represented as sandbox-tested.
