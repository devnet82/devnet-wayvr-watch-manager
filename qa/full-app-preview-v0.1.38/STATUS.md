# Full application QA preview 0.1.38 — release BLOCKED

The user requested a complete application with the accumulated incremental updates.
**This is not a published GitHub release or approved replacement for the working installation.**

**Original, preserved preview ZIP SHA-256:** `d03c0e8d6a95ce8903c1ddc431322d05ec5d3dd45150030d960e94e7dca4eff9`. The exact ZIP was built locally and is **not uploaded to GitHub**, so GitHub Actions has not physically tested these exact new ZIP bytes in an installed CachyOS guest.

Source baseline: v0.1.28 original complete app (v0.1.18-approved watch layout and SideQuest helper); v0.1.31 documented custom HMD-write suppression; v0.1.34 original Doctor patch.

Safety improvements: Preserve v0.1.28 SideQuest guidance; catch OSError in optional WayVR command detection; per-user nonblocking flock; nonzero PARTIAL_ROLLBACK when edited new files are preserved.

**Baseline source gap:** v0.1.29–v0.1.33 complete source not verified. Feature parity with the user's current working application cannot be certified.

Local QA (11 October 2026; unprivileged disposable Debian container):
- 7/7 common full-installer tests PASS across the two newest preview candidates.
- 15/15 extended ZIP, version, portability, symlink, malicious rollback reference, tamper preservation, permission failure and file-lock regression tests PASS.
- Exact ZIP extracted and actually installed, reinstalled and rolled back in isolated HOME: PASS for both.
- ZIP SHA-256, CRC/path safety, shell syntax, Python AST, source watch/icon integrity and no forced service starts: PASS.
- Legacy v0.1.28 suite 59 PASS / 2 FAIL due to expected old HMD fallback and auto-service-restart semantics. Actual Quest ADB and WayVR UI/hardware not tested.

**NOT_TESTED:** Genuine installed CachyOS GRUB/BTRFS/KVM of this exact new ZIP; full historical existing-app upgrade; actual KDE GUI/tray; real connected hardware; long-run/runtime/full Master QA.
Prior native VM fixture tests for previous original hotfix ZIPs do not establish acceptance of these new full-app previews.

All original candidate ZIPs, GitHub drafts and published releases remain untouched.
