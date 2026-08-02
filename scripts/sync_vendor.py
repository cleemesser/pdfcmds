#!/usr/bin/env python3
"""Re-vendor pdf2docx into pdfcmds/_vendor/.

pdf2docx is no longer maintained by Artifex, requires opencv-python-headless (which
would collide with the opencv-python that pdfcmds already depends on), and ships a
tkinter GUI plus a `fire`-based CLI that pdfcmds has no use for. So we carry a trimmed
copy in-tree instead of depending on it.

Usage:
    python scripts/sync_vendor.py                 # re-vendor the pinned version
    python scripts/sync_vendor.py --version 0.6.0 # move to a new upstream release
    python scripts/sync_vendor.py --check         # verify tree matches upstream + patches

Local modifications are expressed as exact-string PATCHES below. A patch that no longer
applies is a hard error: that is the signal that upstream changed something we rely on,
and it should be reviewed rather than silently dropped.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import io
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

PACKAGE = "pdf2docx"
PINNED_VERSION = "0.5.13"

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = REPO_ROOT / "pdfcmds" / "_vendor"
TARGET = VENDOR_ROOT / PACKAGE

# Paths (relative to the upstream package root) dropped from the vendored copy.
DROP = [
    "gui",      # tkinter GUI; pdfcmds is a Click CLI
    "main.py",  # `fire`-based CLI entry point, superseded by pdfcmds.cli
]

# Exact-string edits applied after the drop. (relative path, old, new).
PATCHES = [
    (
        "__init__.py",
        # Upstream ships this file without a trailing newline.
        "\nfrom .main import parse",
        "\n",  # `parse` is defined in the dropped main.py
    ),
    (
        "converter.py",
        # Upstream configures the *root* logger at import time, which hijacks
        # logging for the whole host process. A library must not do this;
        # pdfcmds.cli decides its own verbosity.
        'logging.basicConfig(\n    level=logging.INFO, \n    format="[%(levelname)s] %(message)s")',
        "# logging.basicConfig removed when vendoring; see VENDOR.md",
    ),
]


def fetch_release(version: str) -> tuple[bytes, str, str]:
    """Download the pure-Python wheel for `version`.

    Returns (wheel bytes, sha256 as published by PyPI, wheel filename).
    """
    url = f"https://pypi.org/pypi/{PACKAGE}/{version}/json"
    with urllib.request.urlopen(url) as response:
        meta = json.load(response)

    for entry in meta["urls"]:
        if entry["packagetype"] == "bdist_wheel":
            break
    else:
        raise SystemExit(f"no wheel published for {PACKAGE} {version}")

    with urllib.request.urlopen(entry["url"]) as response:
        payload = response.read()

    expected = entry["digests"]["sha256"]
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise SystemExit(f"sha256 mismatch: got {actual}, expected {expected}")

    return payload, expected, entry["filename"]


def build_tree(payload: bytes, destination: Path) -> str:
    """Extract, trim, and patch the wheel into `destination`. Returns the license text."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(destination)

    package_dir = destination / PACKAGE

    for name in DROP:
        path = package_dir / name
        if not path.exists():
            raise SystemExit(f"expected to drop {name}, but it is not in the wheel")
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    for name, old, new in PATCHES:
        path = package_dir / name
        source = path.read_text(encoding="utf-8")
        if old not in source:
            raise SystemExit(
                f"patch no longer applies to {name}: upstream changed.\n"
                f"  looked for: {old!r}\n"
                f"Review the change and update PATCHES in {Path(__file__).name}."
            )
        path.write_text(source.replace(old, new, 1), encoding="utf-8")

    # Nothing we keep may pull in the deps we deliberately shed.
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for banned in ("import fire", "tkinter"):
            if banned in source:
                raise SystemExit(f"{path.relative_to(package_dir)} still references {banned}")

    dist_info = next(destination.glob(f"{PACKAGE}-*.dist-info"))
    return (dist_info / "licenses" / "LICENSE").read_text(encoding="utf-8")


def write_provenance(version: str, sha256: str, filename: str) -> None:
    (VENDOR_ROOT / "VENDOR.md").write_text(
        f"""# Vendored dependencies

## {PACKAGE}

| | |
|---|---|
| Version | `{version}` |
| Source | <https://pypi.org/project/{PACKAGE}/{version}/> |
| Upstream | <https://github.com/ArtifexSoftware/{PACKAGE}> |
| Artifact | `{filename}` |
| sha256 | `{sha256}` |
| Synced | {date.today().isoformat()} |
| License | MIT — see `LICENSE.{PACKAGE}` |

Re-vendor with `python scripts/sync_vendor.py`. Do not hand-edit `{PACKAGE}/`; express
changes as `PATCHES` in that script so they survive the next sync.

### Why vendored

- Artifex no longer maintains `{PACKAGE}`, so we need to be able to patch it ourselves
  when PyMuPDF moves underneath it.
- Upstream requires `opencv-python-headless`, which installs a second, competing `cv2`
  alongside the `opencv-python` that `pdfcmds` already depends on. Vendoring lets the
  vendored code resolve `cv2` from the existing `opencv-python`.
- Upstream's `fire` CLI and tkinter GUI are dead weight for a Click-based tool.

### Removed from the upstream package

| Path | Reason |
|---|---|
| `gui/` | tkinter GUI; `pdfcmds` is a Click CLI |
| `main.py` | `fire`-based CLI entry point, superseded by `pdfcmds.cli` |

### Patches

| File | Change | Reason |
|---|---|---|
| `__init__.py` | drop `from .main import parse` | `main.py` is not vendored |
| `converter.py` | drop `logging.basicConfig(...)` | Upstream configured the *root* logger at import time, hijacking logging for the whole host process. `pdfcmds.cli` sets its own verbosity (`--verbose`). |

### Dependencies

Vendoring drops upstream's `fire` requirement. Still required, and declared in
`pyproject.toml`: `python-docx`, `fonttools`, `numpy`, and `opencv-python` (upstream asks
for `opencv-python-headless`; either provides the `cv2` module this code imports, and we
deliberately keep the non-headless build already used by `pdfcmds`).

### Known future patch

The vendored code uses `import fitz`, PyMuPDF's deprecated alias. It still resolves on
PyMuPDF 1.27.1. When it is finally removed upstream, the fix is `import pymupdf as fitz`
per module. Left alone for now to keep the vendor diff at zero.
""",
        encoding="utf-8",
    )


def diff_trees(left: Path, right: Path) -> list[str]:
    """Return paths differing between two trees."""
    comparison = filecmp.dircmp(left, right)
    differences = []

    def walk(node: filecmp.dircmp, prefix: str) -> None:
        for name in node.left_only:
            differences.append(f"{prefix}{name} (missing upstream)")
        for name in node.right_only:
            differences.append(f"{prefix}{name} (not vendored)")
        for name in node.diff_files:
            differences.append(f"{prefix}{name} (content differs)")
        for name, sub in node.subdirs.items():
            walk(sub, f"{prefix}{name}/")

    walk(comparison, "")
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=PINNED_VERSION, help="upstream version to vendor")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the vendored tree matches upstream plus PATCHES; do not write",
    )
    args = parser.parse_args()

    print(f"fetching {PACKAGE} {args.version} from PyPI...")
    payload, sha256, filename = fetch_release(args.version)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        license_text = build_tree(payload, staging)
        fresh = staging / PACKAGE

        if args.check:
            if not TARGET.exists():
                print(f"FAIL: {TARGET} does not exist", file=sys.stderr)
                return 1
            differences = diff_trees(fresh, TARGET)
            if differences:
                print("FAIL: vendored tree diverges from upstream + PATCHES:", file=sys.stderr)
                for item in differences:
                    print(f"  {item}", file=sys.stderr)
                return 1
            print(f"OK: {TARGET.relative_to(REPO_ROOT)} matches {PACKAGE} {args.version}")
            return 0

        VENDOR_ROOT.mkdir(parents=True, exist_ok=True)
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.copytree(fresh, TARGET)

        (VENDOR_ROOT / f"LICENSE.{PACKAGE}").write_text(license_text, encoding="utf-8")
        (VENDOR_ROOT / "__init__.py").write_text(
            '"""Third-party code vendored into pdfcmds. See VENDOR.md."""\n',
            encoding="utf-8",
        )
        write_provenance(args.version, sha256, filename)

    count = sum(1 for _ in TARGET.rglob("*.py"))
    print(f"vendored {count} modules into {TARGET.relative_to(REPO_ROOT)}")
    print(f"sha256 {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
