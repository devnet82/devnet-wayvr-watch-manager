# Changelog

## v0.1.14 — WayVR HMD preview cleanup

- adds a packaged copy of WayVR's HMD SVG for the desktop preview
- replaces the `HMD` text placeholder with the actual headset image
- keeps HMD/left/right preview boxes at the same 126×48 size
- keeps all three preview icons at 32×32
- leaves the known-good v0.1.12 live-watch behaviour unchanged
- retains the controller icon/path recovery from v0.1.12
- current automated suite passes 21 functional tests

## v0.1.13 — controller preview cleanup

- replaces desktop-preview `L` / `R` placeholders with the packaged WayVR controller SVGs
- preserves equal HMD/left/right preview box height
- leaves the live WayVR watch implementation unchanged

## v0.1.12 — stock WayVR icon recovery

- restores the stock WayVR path mode after the v0.1.11 XML-v2 experiment caused stock button icons to render as error glyphs
- isolates the two Devnet controller SVGs using rendered absolute `src_ext` paths
- keeps the controller battery boxes in the same horizontal top row as the HMD box
- live user testing confirmed this build fixed the stock WayVR button icons and controller battery display

## v0.1.11 — controller filesystem-path experiment

- attempted to solve local controller SVG loading by switching the watch override to XML layout v2
- live testing showed that change broke stock WayVR button images
- superseded by v0.1.12

## v0.1.8 — permanent Quest controller battery row

- moved Quest controller battery widgets out of WayVR's runtime-owned `devices_root`
- stopped depending on dynamic LeftHand/RightHand battery templates that are not instantiated on the current WiVRn battery path
- live testing confirmed controller percentages appeared

## v0.1.7 — Doctor / Debug

- added GUI Doctor and `devnet-wayvr-watch-doctor`
- added ADB/controller parser checks, watch/XML checks and live 77% / 88% controller-widget test

## v0.1.3 — reliable PC- / PC+ toggle

- replaced the forward-referenced display action with a small runtime helper using `wayvrctl`
- live testing confirmed the in-VR hide/show button worked
