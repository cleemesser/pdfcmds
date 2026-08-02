# pdfcmds

Convenient command-line tools for PDF manipulation, built on the amazing [PyMuPDF](https://pymupdf.readthedocs.io/) family of libraries.

## Installation

Install as a standalone CLI tool using [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```bash
# Using uv (recommended)
uv tool install git+https://github.com/cleemesser/pdfcmds

# Using pipx
pipx install git+https://github.com/cleemesser/pdfcmds
```

## Usage

### Convert PDF to Markdown

```bash
# Convert to markdown (outputs to input.md by default)
pdf convert --to markdown document.pdf

# Specify output file
pdf convert --to markdown document.pdf -o output.md

# Output to stdout (for piping)
pdf convert --to markdown document.pdf --stdout

# Extract images to files during conversion
pdf convert --to markdown document.pdf --write-images

# Embed images as base64 in the markdown (no external files)
pdf convert --to markdown document.pdf --embed-images
```

### Convert PDF to DOCX

```bash
# Convert to Word (outputs to input.docx by default)
pdf convert --to docx document.pdf

# Specify output file, or pipe the DOCX bytes
pdf convert --to docx document.pdf -o output.docx
pdf convert --to docx document.pdf --stdout > output.docx

# Convert a page range (1-based, inclusive)
pdf convert --to docx document.pdf --start 5 --end 12

# Or pick pages and ranges; "10-" means page 10 to the end
pdf convert --to docx document.pdf --pages 1-3,7,10-

# Encrypted PDFs
pdf convert --to docx document.pdf --password secret

# Report per-page progress on long documents
pdf convert --to docx document.pdf --verbose

# Parse pages in parallel (continuous ranges only)
pdf convert --to docx document.pdf --multi-processing --cpu-count 4
```

DOCX conversion uses [pdf2docx](https://github.com/ArtifexSoftware/pdf2docx), vendored into
`pdfcmds/_vendor` — see [`pdfcmds/_vendor/VENDOR.md`](pdfcmds/_vendor/VENDOR.md) for why and
how to re-sync it.

#### Selecting pages

`--pages` takes comma-separated 1-based pages and ranges: `1-3,7,10-`. A trailing `-` means
"to the last page". `--start/--end` are also 1-based and inclusive, and cannot be combined
with `--pages`.

- Pages past the end of the document are **clamped with a warning** rather than rejected, so
  one spec can be reused across PDFs of different lengths: `--pages 1-9999` converts
  everything. A spec that selects nothing at all (`--pages 99` on a 10-page PDF) is an error.
- Reversed ranges (`7-3`) are rejected as typos.
- Duplicates and overlaps are accepted. Note that pages are always written in **document
  order**: `--pages 3,1` produces page 1 followed by page 3, not the reverse.

#### `--ocr-mode` does not run OCR

`--ocr-mode ocred` tells the converter that the PDF **already has** an OCR text layer: it
reads that hidden text and skips images. It does not perform OCR. pdf2docx never implemented
OCR of its own, so there is no mode that does.

For scanned PDFs with no text layer, use markdown conversion instead, which does apply OCR
through PyMuPDF and Tesseract (see [OCR Support](#ocr-support)).

### Check Dependencies

```bash
# Check if optional dependencies (like Tesseract OCR) are installed
pdf check
```

## OCR Support

This tool automatically applies OCR to scanned PDFs when [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) is installed. OCR is handled by PyMuPDF's built-in integration.

### Installing Tesseract OCR

#### macOS

```bash
brew install tesseract

# For additional languages
brew install tesseract-lang
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install tesseract-ocr

# For additional languages (e.g., German, French)
sudo apt install tesseract-ocr-deu tesseract-ocr-fra
```

#### Linux (Fedora/RHEL)

```bash
sudo dnf install tesseract

# For additional languages
sudo dnf install tesseract-langpack-deu tesseract-langpack-fra
```

#### Windows

1. Download the installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki):

   [Download Tesseract for Windows (64-bit)](https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe)

2. Run the installer:
   - Use the default path: `C:\Program Files\Tesseract-OCR`
   - Select additional languages if needed (English is included by default)

3. **Important:** Configure environment variables:
   - Open **Settings** → search "environment variables" → **Edit the system environment variables**
   - Click **Environment Variables...**
   - Under **System variables**:
     - Edit `Path` → Add `C:\Program Files\Tesseract-OCR`
     - Add new variable `TESSDATA_PREFIX` with value `C:\Program Files\Tesseract-OCR\tessdata`

   Alternatively, `pdfcmds` will auto-detect Tesseract in common installation locations even if not in PATH.

### Verify Installation

```bash
# Check Tesseract directly
tesseract --version

# Check via pdfcmds
pdf check
```

### Language Files

Tesseract requires trained data files for each language. English (`eng`) is included by default.

**Common language codes:**

| Code | Language |
|------|----------|
| eng | English |
| deu | German |
| fra | French |
| spa | Spanish |
| chi_sim | Chinese (Simplified) |
| chi_tra | Chinese (Traditional) |
| jpn | Japanese |
| kor | Korean |

For manual language file installation, download `.traineddata` files from:
- [tessdata](https://github.com/tesseract-ocr/tessdata) - Standard (recommended)
- [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) - Highest accuracy
- [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) - Fastest performance

## Development

Running `pdf` from a source checkout, rather than from an installed copy.

### Setup

```bash
git clone https://github.com/cleemesser/pdfcmds
cd pdfcmds
uv sync
```

`uv sync` creates `.venv/` and installs `pdfcmds` in editable mode together with the dev
dependencies, so source edits take effect immediately with no reinstall.

### Running the CLI from the source tree

```bash
uv run pdf convert --to docx tests/data/power2022-grokking.pdf --pages 1-2
uv run pdf convert --to markdown tests/data/power2022-grokking.pdf --stdout
uv run pdf check
```

Three equivalent ways to invoke it:

| Command | Notes |
|---------|-------|
| `uv run pdf …` | Recommended. Syncs the environment first if needed. |
| `uv run python -m pdfcmds.cli …` | Same CLI via the module; useful under a debugger or profiler. |
| `./.venv/bin/pdf …` | Direct, skips uv entirely. |

> **Careful:** if `pdfcmds` is *also* installed globally (`uv tool install`), a bare `pdf`
> runs that installed copy, **not** your working tree — so your changes appear to do
> nothing. Use `uv run pdf` while developing, and check which one you are on with:
>
> ```bash
> which pdf && pdf --version      # the globally installed tool
> uv run which pdf                # the working-tree copy in .venv
> ```

### Tests

```bash
uv run pytest                                       # everything
uv run pytest tests/test_docx.py -q                 # DOCX conversion only
uv run pytest tests/test_docx.py::TestParsePageSpec # one class
uv run pytest -k PageSpec -q                        # by name (case-sensitive substring)
```

### Re-vendoring pdf2docx

`pdf2docx` is vendored into `pdfcmds/_vendor` (see
[`pdfcmds/_vendor/VENDOR.md`](pdfcmds/_vendor/VENDOR.md) for why). **Do not hand-edit it** —
express changes as `PATCHES` in `scripts/sync_vendor.py` so they survive the next sync.

```bash
uv run python scripts/sync_vendor.py --check      # verify tree matches upstream + patches
uv run python scripts/sync_vendor.py              # re-vendor the pinned version
uv run python scripts/sync_vendor.py --version 0.6.0   # move to a new upstream release
```

`--check` re-downloads the pinned release and diffs it against the tree, so it needs network
access. A patch that no longer applies is a hard error: that is the signal upstream changed
something we depend on, and it should be reviewed rather than skipped.

### Building and installing your working tree

```bash
uv build                  # wheel + sdist into dist/
uv tool install .         # install the working tree as the global `pdf` command
uv tool install --force . # overwrite an existing global install
```

## Acknowledgments

This tool is built on:
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF parsing and rendering
- [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) - Markdown extraction optimized for LLMs
- [pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) - PDF to DOCX conversion (MIT, vendored)
- [Click](https://click.palletsprojects.com/) - Command-line interface

## License

MIT

## Future directions for mathematics especially
- The work on [Nougat: Neural Optical Understanding for academic
  Documents](https://github.com/facebookresearch/nougat) seems interesting
This installs but does not quite work on the first pdf I tried
```
uv tool install -U git+https://github.com/facebookresearch/nougat --with torch --with torchvision --index https://download.pytorch.org/wh1/cu126
```
- Mathpix integration seems like a good commercial option for handling equations
- [SnapXam Math api] (https://www.snapxam.com/apis/math-apis)
```
pip install snapxam-math-ocr
```
