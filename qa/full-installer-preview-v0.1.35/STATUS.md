# Devnet devnet-wayvr-watch-manager v0.1.35 — FULL APP QA PREVIEW / NOT RELEASE APPROVED

The user requested complete installable application candidates rather than incremental hotfix-only packages. A new versioned local ZIP preview was produced from archived original full source and current known hotfix code.

**Candidate ZIP SHA-256:** `9b9e0d7b2ae20eab78cc45b28d2d9c905ba5d546c37bfe86ad1aa252bc31894b` (built in isolated assistant working container; NOT uploaded as a GitHub release asset).

## Provenance

- Integrated sources: v0.1.27 complete manager + v0.1.31 documented HMD suppression behavior + v0.1.34 Doctor constructor fix.
- Gaps in feature-parity certification: **full v0.1.28–v0.1.33 sources not available**.
- Updated candidate has a full bin/application payload, safe user-only installer with dry-run, existing-config preservation, a backup manifest and rollback.
- Existing supported app upgrades are conservative: version sync is applied to existing runtime source without replacing current daemon, GUI layout or watch assets. Fresh installation uses the earlier recovered full source.
- Original release ZIPs remain unmodified and unpublished.

## QA

7 shared isolated installer regressions passed; 59/61 archived v0.1.27 tests passed; 2 historical expectations differ (HMD writes and service auto-start).

The preview was tested in an isolated Linux container as an unprivileged user. **It has not undergone the authentic installed CachyOS GRUB/BTRFS VM regression process for this NEW candidate**, nor any live Quest/SteamVR/Gtk UI, multi-hardware or production service testing.

The WayVR watch.xml and SVGs originate from the archived full source and were not modified; matching the user's *latest* locked and approved watch-layout image is NOT VERIFIED.

**Decision: BLOCKED / DO NOT PUBLISH OR DEPLOY.**

The preview is delivered as a conversation artifact, not a GitHub release. To approve a complete substitute, first reconcile the missing intervening full sources and pass comprehensive application Master QA in genuine installed CachyOS.
