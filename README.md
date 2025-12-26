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

## Acknowledgments

This tool is built on:
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF parsing and rendering
- [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) - Markdown extraction optimized for LLMs
- [Click](https://click.palletsprojects.com/) - Command-line interface

## License

MIT
