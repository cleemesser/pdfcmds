# Vendored dependencies

## pdf2docx

| | |
|---|---|
| Version | `0.5.13` |
| Source | <https://pypi.org/project/pdf2docx/0.5.13/> |
| Upstream | <https://github.com/ArtifexSoftware/pdf2docx> |
| Artifact | `pdf2docx-0.5.13-py3-none-any.whl` |
| sha256 | `a293e9e78d89b12a4a43fcefba1346de220681c3daf20b8a7d3e1fce77f0fe97` |
| Synced | 2026-10-23 |
| License | MIT — see `LICENSE.pdf2docx` |

Re-vendor with `python scripts/sync_vendor.py`. Do not hand-edit `pdf2docx/`; express
changes as `PATCHES` in that script so they survive the next sync.

### Why vendored

- Artifex no longer maintains `pdf2docx`, so we need to be able to patch it ourselves
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
| all modules | `import fitz` → `import pymupdf as fitz`, `from fitz…` → `from pymupdf…` | `fitz` is PyMuPDF's deprecated alias. Binding the real package to the old name leaves every `fitz.X` call site unchanged. A sync fails if any `fitz` import survives. |

### Dependencies

Vendoring drops upstream's `fire` requirement. Still required, and declared in
`pyproject.toml`: `python-docx`, `fonttools`, `numpy`, and `opencv-python` (upstream asks
for `opencv-python-headless`; either provides the `cv2` module this code imports, and we
deliberately keep the non-headless build already used by `pdfcmds`).
