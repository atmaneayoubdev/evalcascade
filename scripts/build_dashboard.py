#!/usr/bin/env python3
"""Build the EvalCascade dashboard and bundle it into the Python package.

Steps:

1. ``npm ci`` in ``web/``, or ``npm install`` when there is no ``package-lock.json``.
2. ``npm run build``, a Next.js static export to ``web/out``.
3. Copy ``web/out`` to ``src/evalcascade/dashboard_dist/``, replacing any previous bundle.
   The wheel ships this directory, and ``evalcascade serve`` serves it at ``/``.

Usage::

    uv run python scripts/build_dashboard.py               # install, build, copy
    uv run python scripts/build_dashboard.py --skip-build  # copy an existing web/out only

Works on Linux, macOS and Windows (where npm is ``npm.cmd``). Requires Node.js 22 and npm,
except with ``--skip-build``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
OUT_DIR = WEB_DIR / "out"
DEST_DIR = ROOT / "src" / "evalcascade" / "dashboard_dist"
MIN_NODE_MAJOR = 20  # Next.js 16 needs Node >= 20.9; the project targets Node 22.


class BuildError(Exception):
    """A step failed; the message explains what to do."""


def find_npm() -> str:
    """Absolute path of the npm executable (``npm.cmd`` on Windows)."""
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    raise BuildError(
        "npm was not found on PATH. Install Node.js 22 (which includes npm) from "
        "https://nodejs.org/ or with your package manager, then re-run this script. "
        "To bundle an already-built web/out, use --skip-build."
    )


def check_node() -> None:
    """Warn (don't fail) when Node.js is missing or older than the supported version."""
    node = shutil.which("node")
    if node is None:
        print("warning: `node` was not found on PATH; npm may fail.", file=sys.stderr)
        return
    try:
        version = subprocess.run(  # noqa: S603 - fixed arguments, absolute executable path
            [node, "--version"], capture_output=True, text=True, check=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        print("warning: could not determine the Node.js version.", file=sys.stderr)
        return
    major = version.lstrip("v").split(".", 1)[0]
    if major.isdigit() and int(major) < MIN_NODE_MAJOR:
        print(
            f"warning: Node.js {version} detected; Node.js 22 is recommended "
            f"(>= {MIN_NODE_MAJOR} is required by Next.js).",
            file=sys.stderr,
        )
    else:
        print(f"Node.js {version}")


def run(cmd: list[str], cwd: Path) -> None:
    """Run a command, streaming its output; raise BuildError on failure."""
    printable = " ".join([Path(cmd[0]).stem, *cmd[1:]])
    print(f"\n$ {printable}   (in {cwd.relative_to(ROOT).as_posix() or '.'})", flush=True)
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, check=False)  # noqa: S603 - fixed args
    except OSError as exc:
        raise BuildError(f"could not start `{printable}`: {exc}") from exc
    if result.returncode != 0:
        raise BuildError(f"`{printable}` failed with exit code {result.returncode}")


def build(npm: str) -> None:
    if not (WEB_DIR / "package.json").is_file():
        raise BuildError(f"{WEB_DIR / 'package.json'} not found; is this an EvalCascade checkout?")
    check_node()
    if (WEB_DIR / "package-lock.json").is_file():
        run([npm, "ci", "--no-audit", "--no-fund"], WEB_DIR)
    else:
        print("note: web/package-lock.json not found; using `npm install`.")
        run([npm, "install", "--no-audit", "--no-fund"], WEB_DIR)
    run([npm, "run", "build"], WEB_DIR)


def copy_bundle() -> int:
    """Replace DEST_DIR with the contents of OUT_DIR; return the number of files copied."""
    if not (OUT_DIR / "index.html").is_file():
        raise BuildError(
            f"{OUT_DIR / 'index.html'} not found. Build the dashboard first "
            "(run this script without --skip-build) and check that web/next.config.ts "
            'uses output: "export".'
        )
    # Safety net before deleting anything: only ever replace the package's bundle directory.
    if DEST_DIR.name != "dashboard_dist" or DEST_DIR.parent.name != "evalcascade":
        raise BuildError(f"refusing to replace unexpected directory {DEST_DIR}")
    if DEST_DIR.exists():
        shutil.rmtree(DEST_DIR)
    shutil.copytree(OUT_DIR, DEST_DIR)
    return sum(1 for p in DEST_DIR.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Next.js dashboard in web/ and copy the static export into "
        "src/evalcascade/dashboard_dist/ (served by `evalcascade serve`).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Do not run npm; only copy an existing web/out into the package.",
    )
    args = parser.parse_args(argv)

    try:
        if not args.skip_build:
            build(find_npm())
        count = copy_bundle()
    except BuildError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    print(f"\nCopied {count} files: web/out -> {DEST_DIR.relative_to(ROOT).as_posix()}/")
    print("`evalcascade serve` will now serve the dashboard at http://127.0.0.1:8000/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
