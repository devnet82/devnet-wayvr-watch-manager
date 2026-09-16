# Devnet WayVR Watch Manager v0.1.14

v0.1.14 is the current public package for the Quest 3 + WiVRn + WayVR watch customisation tool.

## Highlights

- preserves WayVR's standard watch and controls
- adds live PC metrics and extra watch information
- adds Quest left/right Touch Plus battery percentages through wireless ADB
- uses WayVR's controller images in the live battery row
- uses WayVR HMD/controller images in the desktop preview
- keeps the HMD and both controller preview boxes the same height
- includes PC- / PC+ in-VR hide/show control
- includes backup/restore and a detailed Doctor / Debug tool

## Controller battery architecture

The current WiVRn/Monado path exposes HMD battery status to WayVR but does not expose controller battery status in the battery-device list. Devnet reads left/right controller percentages from Quest `OVRRemoteService` over ADB and writes them to permanent watch widgets.

Those widgets are deliberately outside WayVR's runtime-owned `devices_root`, preventing them from being deleted when WayVR rebuilds its tracked-device list.

## Icon/path recovery

An earlier XML-v2 path experiment made the stock WayVR button images render as error glyphs. The confirmed fix restores the proven stock WayVR path mode and gives only the custom controller images explicit filesystem paths.

v0.1.14 keeps that working live-watch implementation. Its release-specific change is the addition of the WayVR HMD icon to the desktop preview.

## QA

The final v0.1.14 source passes 21 automated functional tests covering XML structure, controller battery parsing, fake ADB discovery/reconnect/failure handling, metrics command generation, toggle behaviour, backup/restore, Doctor output and desktop preview icon regressions.

The live watch/controller-battery architecture and stock WayVR icon recovery were confirmed on the reference Quest 3 setup before the preview-only v0.1.13/v0.1.14 changes.

See `TEST-REPORT.md` for the exact verification boundary.
