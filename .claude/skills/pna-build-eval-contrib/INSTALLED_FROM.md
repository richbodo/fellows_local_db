# Provenance

`SKILL.md` here is a **vendored copy** of the `pna-build-eval-contrib` skill from the
Personal Network Toolkit (https://github.com/richbodo/personal_network_toolkit),
copied at PNT commit `419702a`.

This repo (`fellows_local_db`) is PNT's first reference design and actively contributes
to the toolkit, so the skill is installed **per-repo** to drive the build / evaluate /
contribute flows from here.

Caveats:
- It is a *copy* and will **drift** from upstream — re-sync (re-copy from a known PNT
  commit, update this file) before relying on it for a contribution.
- Claude Code discovers skills at **session start**; after installing, restart the
  session for it to become invocable.

The canonical per-repo install mechanism (copy-with-pinned-commit vs. symlink vs.
user-wide) is being documented upstream in PNT — this vendored copy follows the
"copy with a pinned commit + provenance note" approach.
