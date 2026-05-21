#!/usr/bin/env python3
"""Build .mcpb (Anthropic Desktop Extension) bundles from mcpb/node/.

For each manifest in ``mcpb/node/manifests/<name>.json`` (currently only
``comms``; ``shared`` and ``private`` land in their own PRs), assembles a
staging directory of the shape that Claude Desktop's MCPB format expects:

    staging/
      manifest.json    # the per-bundle manifest, copied verbatim
      server/          # compiled JS + production node_modules
        index.js
        node_modules/

...then runs ``npx @anthropic-ai/mcpb pack staging/ out.mcpb`` to produce
the final bundle. Output goes to ``deploy/dist/mcpb/<name>.mcpb``.

Run from the repo root:

    python build/build_mcpb.py           # builds every available bundle
    python build/build_mcpb.py comms     # one named bundle

Or via the recipe wrapper:

    just build-mcpb
    just build-mcpb comms

Prerequisites: Node 20+ and npm. The ``@anthropic-ai/mcpb`` CLI is
invoked via ``npx`` so no global install is required.

Why a Python build driver in a Node project: it keeps the build entry
points uniform with the rest of the repo's tooling (``build_pwa.py``,
``restore_from_knack_scrapefile.py``), and Python's subprocess + pathlib
ergonomics fit the orchestration cleanly. The TypeScript inside
``mcpb/node/`` is compiled by ``tsc``; this script just orchestrates.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCPB_NODE_DIR = REPO_ROOT / "mcpb" / "node"
MANIFESTS_DIR = MCPB_NODE_DIR / "manifests"
DIST_TS_DIR = MCPB_NODE_DIR / "dist"
PACKAGE_JSON = MCPB_NODE_DIR / "package.json"
OUTPUT_DIR = REPO_ROOT / "deploy" / "dist" / "mcpb"


def _run(cmd: list[str], cwd: Path) -> None:
    """Run a subprocess and surface stdout/stderr inline. Raises on failure."""
    print(f"  $ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(f"command failed (exit {result.returncode}): {' '.join(cmd)}")


def _ensure_node_modules() -> None:
    """Install Node dependencies in mcpb/node/ if missing."""
    if (MCPB_NODE_DIR / "node_modules").is_dir():
        return
    print("Installing mcpb/node/ dependencies...", file=sys.stderr)
    _run(["npm", "install"], cwd=MCPB_NODE_DIR)


def _compile_typescript() -> None:
    """Compile TS sources to JS into mcpb/node/dist/."""
    print("Compiling TypeScript...", file=sys.stderr)
    _run(["npx", "tsc"], cwd=MCPB_NODE_DIR)


def _load_manifest(name: str) -> dict:
    path = MANIFESTS_DIR / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"no manifest for '{name}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_bundle(name: str, manifest: dict, staging: Path) -> None:
    """Assemble the bundle layout under ``staging`` per the MCPB Node format."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # Per-bundle manifest at the root of the staging dir.
    (staging / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Server entry: compiled JS + production node_modules. Each bundle
    # only ships the one server's compiled output (not the whole dist/).
    server_dir = staging / "server"
    server_dir.mkdir()
    src_dir = DIST_TS_DIR / name
    if not src_dir.is_dir():
        raise SystemExit(
            f"compiled output for '{name}' not found at {src_dir} — did tsc run?"
        )
    # Copy compiled JS as server/index.js + any sibling files (sourcemaps etc).
    for item in src_dir.iterdir():
        shutil.copy2(item, server_dir / item.name)

    # Bundle production node_modules INSIDE server/ so the manifest's
    # entry_point and ${__dirname}/server/index.js Just Work after install.
    # Use --production to skip devDeps; --no-package-lock to avoid touching
    # the source tree's lockfile from inside a staging dir.
    print("  Installing production node_modules into staging/server/...", file=sys.stderr)
    # Copy package.json into server/ so npm install knows what to fetch.
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    # Strip devDependencies + scripts that aren't relevant in the bundle.
    pkg.pop("devDependencies", None)
    pkg.pop("scripts", None)
    (server_dir / "package.json").write_text(
        json.dumps(pkg, indent=2) + "\n", encoding="utf-8"
    )
    _run(
        ["npm", "install", "--omit=dev", "--no-package-lock", "--ignore-scripts"],
        cwd=server_dir,
    )


def _pack(staging: Path, output_path: Path) -> None:
    """Run mcpb pack against the staging dir."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    _run(["npx", "--yes", "@anthropic-ai/mcpb", "pack", str(staging), str(output_path)],
         cwd=REPO_ROOT)


def build_bundle(name: str) -> Path:
    """Build one named bundle. Returns the output .mcpb path."""
    print(f"\n=== Building {name}.mcpb ===", file=sys.stderr)
    manifest = _load_manifest(name)
    staging = MCPB_NODE_DIR / ".staging" / name
    _stage_bundle(name, manifest, staging)
    output_path = OUTPUT_DIR / f"{name}.mcpb"
    _pack(staging, output_path)
    size_kb = output_path.stat().st_size // 1024
    print(f"  -> {output_path} ({size_kb} KB)", file=sys.stderr)
    return output_path


def available_bundles() -> list[str]:
    """All manifests currently in mcpb/node/manifests/."""
    return sorted(p.stem for p in MANIFESTS_DIR.glob("*.json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build .mcpb bundles.")
    parser.add_argument(
        "names",
        nargs="*",
        help="Bundle names to build (default: all available).",
    )
    args = parser.parse_args(argv)

    _ensure_node_modules()
    _compile_typescript()

    targets = args.names or available_bundles()
    if not targets:
        print("No manifests found in mcpb/node/manifests/.", file=sys.stderr)
        return 1
    for name in targets:
        build_bundle(name)
    print(f"\nBuilt {len(targets)} bundle(s) into {OUTPUT_DIR}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
