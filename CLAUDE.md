# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Development Commands

```bash
# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## CLI Usage

The package provides a `pdf` command-line tool:

```bash
pdf convert --to markdown input.pdf             # Output to input.md (default)
pdf convert --to markdown input.pdf -o out.md   # Output to specific file
pdf convert --to markdown input.pdf --stdout    # Output to stdout
pdf check                                        # Check if Tesseract OCR is installed
```

## OCR Setup

PyMuPDF4LLM has built-in OCR support via Tesseract. OCR is automatically applied to scanned PDFs when Tesseract is installed.

### macOS

```bash
brew install tesseract
```

For additional languages:
```bash
brew install tesseract-lang
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install tesseract-ocr
```

For additional languages (e.g., German, French):
```bash
sudo apt install tesseract-ocr-deu tesseract-ocr-fra
```

### Linux (Fedora/RHEL)

```bash
sudo dnf install tesseract
```

For additional languages:
```bash
sudo dnf install tesseract-langpack-deu tesseract-langpack-fra
```

### Windows

1. Download the installer from UB Mannheim:
   https://github.com/UB-Mannheim/tesseract/wiki

   Direct link (64-bit): https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe

2. Run the installer:
   - Use default path: `C:\Program Files\Tesseract-OCR`
   - On "Select Components", keep defaults (English language data is included)
   - Select additional languages if needed

3. Configure environment variables:
   - Open **Settings** → search "environment variables" → **Edit the system environment variables**
   - Click **Environment Variables...**
   - Under **System variables**:

     **Add to PATH:**
     - Select `Path` → **Edit** → **New**
     - Add: `C:\Program Files\Tesseract-OCR`

     **Add TESSDATA_PREFIX:**
     - Click **New**
     - Variable name: `TESSDATA_PREFIX`
     - Variable value: `C:\Program Files\Tesseract-OCR\tessdata`

   - Click **OK** on all dialogs

### Verify Installation

Open a new terminal and run:

```bash
tesseract --version
```

Should output version info like `tesseract 5.5.0`.

### Language Files

Tesseract requires trained data files for each language. English (`eng`) is included by default.

**List installed languages:**
```bash
tesseract --list-langs
```

**Common language codes:**
| Code    | Language              |
|---------|-----------------------|
| eng     | English               |
| deu     | German                |
| fra     | French                |
| spa     | Spanish               |
| chi_sim | Chinese (Simplified)  |
| chi_tra | Chinese (Traditional) |
| jpn     | Japanese              |
| kor     | Korean                |
| ara     | Arabic                |
| rus     | Russian               |

#### Installing Language Files

**macOS:**
```bash
brew install tesseract-lang  # Installs all languages
```

**Linux (Ubuntu/Debian):**
```bash
# Install specific languages
sudo apt install tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa

# Or search for available languages
apt search tesseract-ocr-
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install tesseract-langpack-deu tesseract-langpack-fra
```

**Windows:**

Option 1: Re-run the installer and select additional languages in "Select Components".

Option 2: Download language files manually:

1. Download `.traineddata` files from:
   https://github.com/tesseract-ocr/tessdata

   For best quality, use tessdata_best:
   https://github.com/tesseract-ocr/tessdata_best

2. Copy the `.traineddata` file to your tessdata folder:
   ```
   C:\Program Files\Tesseract-OCR\tessdata\
   ```

3. Verify installation:
   ```bash
   tesseract --list-langs
   ```

#### Tessdata Variants

Tesseract offers three tessdata variants:

| Variant                                                         | Description                | Use Case                       |
|-----------------------------------------------------------------|----------------------------|--------------------------------|
| [tessdata](https://github.com/tesseract-ocr/tessdata)           | Standard, integer-based    | Good balance of speed/accuracy |
| [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) | Float-based, most accurate | When accuracy is critical      |
| [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) | Optimized for speed        | When speed is critical         |

## Architecture

This is a CLI tool for PDF manipulation built on PyMuPDF and PyMuPDF4LLM.

- **pdfcmds/cli.py**: Click-based CLI with command groups. Entry point is `main()`.
- **pdfcmds/\_\_init__.py**: Package version (used by pyproject.toml dynamic versioning).

New commands should be added as functions decorated with `@main.command()` in cli.py.

## Known Issues

### pymupdf-layout ignores image_path parameter

**Affected versions:**
- pymupdf: 1.26.6
- pymupdf4llm: 0.2.7
- pymupdf-layout: 1.26.6

**Bug:** When `pymupdf.layout` is activated (required for enhanced layout detection), the `image_path` parameter passed to `pymupdf4llm.to_markdown()` is ignored. Images are written to the source PDF's directory instead of the specified path.

**Workarounds implemented in pdfcmds:**

1. **Resolve input paths to absolute** - Prevents path concatenation errors when relative paths are used
2. **Post-process markdown** - Convert absolute image paths in output to relative paths using `_make_image_paths_relative()`

**Minimal reproduction:**

```python
import tempfile
from pathlib import Path

import pymupdf.layout
pymupdf.layout.activate()

import pymupdf4llm

pdf_path = Path("test.pdf").resolve()

with tempfile.TemporaryDirectory() as tmpdir:
    image_dir = Path(tmpdir) / "images"
    image_dir.mkdir()

    md = pymupdf4llm.to_markdown(
        str(pdf_path),
        write_images=True,
        image_path=str(image_dir)
    )

    # Expected: images in image_dir
    # Actual: images in pdf_path.parent (BUG)
    print(f"Images in image_dir: {list(image_dir.glob('*.png'))}")
    print(f"Images in PDF dir: {list(pdf_path.parent.glob('*.png'))}")
```

**Status:** Not yet reported upstream. See `bug_report_example.py` for a runnable test case.

## Python Project Standards

Use dynamic versioning for all Python projects. Define version in `__init__.py` and reference it from pyproject.toml:

```python
# package/__init__.py
__version__ = "0.1.0"
```

```toml
# pyproject.toml
[project]
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "package.__version__"}
```

### development
- use uv as standard development tool

### references
- see especially: https://github.com/pymupdf/PyMuPDF-Utilities for lots of examples
- see https://github.com/pymupdf/pymupdf4llm/discussions/327 for summary of what changes when import pymupdf.layout
## TODO
- [ ] add support for other pymupdf/llm ouptuts like json and txt
- [ ] testing from others with and without tesseract
- [ ] Publish to PyPI