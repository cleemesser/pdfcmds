# Plan: `pdf convert --to docx` via vendored pdf2docx

## Context

`pdfcmds` today converts PDF → Markdown only (`pdfcmds/cli.py`, built on `pymupdf4llm` +
`pymupdf-layout`). We want PDF → DOCX. The obvious engine is Artifex's `pdf2docx`, which
sits on the same PyMuPDF stack already in use.

Rather than take it as a normal dependency, we vendor it, because:

1. **Artifex no longer maintains it.** Upstream's own README and PyPI metadata say so.
   Vendoring makes us able to patch it when PyMuPDF moves under it.
2. **Dependency conflict.** `pdf2docx` requires `opencv-python-headless>=4.5`; `pdfcmds`
   already requires `opencv-python`. Installing both puts two competing `cv2` modules in
   site-packages. Vendoring lets us satisfy `cv2` from the `opencv-python` we already have.
3. **Dead weight.** `pdf2docx` pulls `fire` for its own CLI and ships a tkinter GUI, both
   useless to us — we have Click.

Verified compatibility (not assumed):
- `pdf2docx` 0.5.13 (2026-05-01) is **MIT**, requires Python ≥3.10 / PyMuPDF ≥1.26.7.
  This venv has Python 3.14.3 and PyMuPDF 1.27.1. ✅
- `pdf2docx` uses `import fitz` and `fitz.VersionBind`; both still resolve on PyMuPDF
  1.27.1 (checked in `.venv`). ✅
- `pymupdf.layout.activate()` (called at import time in `cli.py:71`) only assigns the
  `pymupdf._get_layout` hook, which is consulted solely by the opt-in `Page.get_layout()`
  (`pymupdf/__init__.py:10829-10841`). It does **not** patch `get_text()`/`get_drawings()`,
  so pdf2docx's parsing is unaffected by living in the same process. ✅

## Decisions (confirmed with user)

| Axis | Choice |
|---|---|
| Vendor method | Copy into tree + `VENDOR.md` provenance + `scripts/sync_vendor.py` |
| Vendor scope | Everything except `gui/` (tkinter) and `main.py` (fire CLI) |
| CLI options | page selection, `--password`, OCR mode, multi-processing |

## Correction to the OCR option

`--ocr` cannot mean "run OCR". In `pdf2docx/page/RawPageFitz.py`:

```python
ocr = settings['ocr']
if ocr==1: raise SystemExit("OCR feature is planned but not implemented yet.")
...
if ocr==2:            # extract only hidden text (already-OCR-ed PDF), skip images
```

So we expose `--ocr-mode [none|ocred]` → `0|2` and never emit `1`. The existing Tesseract
plumbing (`find_tesseract`, `pdf check`) is unrelated to this path and stays untouched.

## Layout

```
pdfcmds/
  cli.py                     # modified
  _vendor/
    __init__.py              # new, empty
    VENDOR.md                # new: upstream URL, tag, commit SHA, patch log
    LICENSE.pdf2docx         # new: upstream MIT text
    pdf2docx/                # new: copied, minus gui/ and main.py
      __init__.py            # patched: drop gui/main re-exports
      converter.py
      common/ font/ image/ layout/ page/ shape/ table/ text/
scripts/
  sync_vendor.py             # new: re-pull upstream, re-apply trims, refresh VENDOR.md
tests/
  test_docx.py               # new
plans/
  pdf-to-docx.md             # copy of this plan (user asked for it in plans/)
```

`pdf2docx` uses **relative** intra-package imports (`from .page.Page import Page`), so the
copy works under `pdfcmds._vendor.pdf2docx` with no import rewriting. The only edit is
`__init__.py`, which re-exports the dropped `main`/`gui`.

## Steps

### 1. Vendor the source
- Fetch the 0.5.13 sdist/tag, copy `pdf2docx/` → `pdfcmds/_vendor/pdf2docx/`.
- Delete `gui/` and `main.py`; strip their re-exports from `_vendor/pdf2docx/__init__.py`,
  keeping `Converter`.
- Write `LICENSE.pdf2docx` (MIT, upstream copyright preserved) and `VENDOR.md` recording
  upstream URL, version, commit SHA, sync date, and every local patch with its rationale.
- Confirm no vendored module imports `fire` or `tkinter` after the trim.

### 2. `scripts/sync_vendor.py`
Downloads a given upstream ref, applies the same trim, overwrites the vendored tree, and
rewrites the `VENDOR.md` header. Keep it dumb and re-runnable; local patches are reviewed
in the resulting diff rather than replayed from patch files.

### 3. Dependencies (`pyproject.toml`)
Add `python-docx>=0.8.10`, `fonttools>=4.24.0`, `numpy>=1.17.2`.
Do **not** add `opencv-python-headless` (existing `opencv-python` provides `cv2`) and do
**not** add `fire`. Note the `cv2` decision in `VENDOR.md`.

Also add to `[tool.setuptools.packages.find]` / package data so `_vendor` ships in the wheel —
the current config relies on autodiscovery, so verify `_vendor.pdf2docx.*` subpackages are
actually included in a built wheel, not silently dropped.

### 4. CLI (`pdfcmds/cli.py`)
- `--to` choices: `["markdown", "md", "docx"]`.
- Split the existing body of `convert()` (cli.py:176-240) into `_convert_to_markdown(...)`,
  add `_convert_to_docx(...)`, leave `convert()` as a thin dispatcher. Markdown behaviour,
  including the `_make_image_paths_relative` workaround, must be byte-for-byte unchanged.
- New options, all docx-only: `--pages`, `--start`, `--end`, `--password`, `--ocr-mode`,
  `--multi-processing`, `--cpu-count`.
- Import the vendored converter **lazily inside `_convert_to_docx`**, so markdown runs and
  `pdf check` don't pay for `python-docx`/`cv2`/`numpy` import.
- Default output `input.with_suffix(".docx")`; `--stdout` writes bytes via
  `sys.stdout.buffer` (pdf2docx's `Converter.convert` accepts `IO[AnyStr]`), matching the
  existing markdown stdout pattern.
- Always `Converter.close()` in a `finally` — the class has no `__enter__`/`__exit__`.

### 5. Validation rules (extend the existing `click.UsageError` pattern at cli.py:186)
- `--write-images` / `--embed-images` / `--image-dir` with `--to docx` → error.
- `--pages` together with `--multi-processing` → error. Upstream raises
  `ConversionException('Multi-processing works for continuous pages specified by "start"
  and "end" only.')`; catch it at the CLI boundary instead so the user sees a clean message.
- `--pages` together with `--start`/`--end` → error (ambiguous).

### 6. Your contribution — page-spec parsing

I'll create `_parse_page_spec(spec: str, page_count: int) -> list[int]` in `cli.py` with the
signature, docstring, and call site wired up, marked `TODO`. It turns `"1-3,7,10-"` into
zero-based indexes for pdf2docx's `pages` argument.

Worth your call because the semantics are yours to set:
- 1-based user input vs. pdf2docx's 0-based `pages` — where does the conversion happen?
- Out-of-range page (`"99"` on a 10-page PDF): hard error, or clamp and warn?
- Open-ended (`"10-"`) and reversed (`"7-3"`) ranges: support, or reject?
- Duplicates/overlaps (`"1-3,2"`): dedupe and sort, or preserve the user's order?

~10 lines. I'll implement everything around it and write the tests against whatever
semantics you choose.

### 7. Docs
- `README.md` + `CLAUDE.md`: docx usage, the new options, the `--ocr-mode` caveat.
- `CLAUDE.md` "Known Issues": note the vendoring rationale and point at `VENDOR.md`.

## Verification

```bash
uv sync
uv pip list | grep -Ei "docx|opencv|fonttools"   # expect python-docx + opencv-python only,
                                                  # NOT opencv-python-headless

# no stray upstream deps leaked in
grep -rn "import fire\|import tkinter" pdfcmds/_vendor/ || echo "clean"

uv run pdf convert --to docx tests/data/power2022-grokking.pdf -o /tmp/out.docx
uv run pdf convert --to docx tests/data/power2022-grokking.pdf --pages 1-2 -o /tmp/p12.docx
uv run pdf convert --to docx tests/data/power2022-grokking.pdf --stdout > /tmp/s.docx

python -c "from docx import Document; d=Document('/tmp/out.docx'); print(len(d.paragraphs), len(d.tables))"

uv run pytest            # existing markdown tests must still pass unchanged
uv build && python -c "import zipfile; print([n for n in zipfile.ZipFile(__import__('glob').glob('dist/*.whl')[0]).namelist() if '_vendor' in n][:5])"
```

`tests/test_docx.py` covers: default output path, `-o`, `--stdout` produces a valid zip,
page selection, each rejected flag combination, and that a converted DOCX opens under
`python-docx` with non-empty content. Follows the `CliRunner` + `tmpdir` style of
`tests/test_convert.py`.

## Risks

- **Wheel packaging.** Easiest way to ship a broken release is `_vendor` subpackages missing
  from the wheel. Explicitly verified in the build step above.
- **Upstream is unmaintained.** Accepted, and the reason we're vendoring. `VENDOR.md` is what
  makes the next PyMuPDF break tractable.
- **`import fitz` deprecation.** Works on 1.27.1 today. When it breaks, the patch is a
  one-line `import pymupdf as fitz` per module; logged in `VENDOR.md` as a known future edit.
  Not doing it now keeps the vendor diff at zero.
- **Multi-processing** is upstream's flakiest path. Off by default, opt-in only.
