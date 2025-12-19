"""Command-line interface for pdfcmds."""

import os
import shutil
import sys
from pathlib import Path

import click

# Common Tesseract installation paths on Windows
WINDOWS_TESSERACT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
    Path(os.environ.get("ProgramFiles", ""), "Tesseract-OCR", "tesseract.exe"),
    Path(os.environ.get("ProgramFiles(x86)", ""), "Tesseract-OCR", "tesseract.exe"),
]


def _find_tesseract_early() -> Path | None:
    """Configure Tesseract environment before pymupdf imports.

    Returns the path to tesseract executable if found.
    """
    tesseract_path = None

    # First check PATH
    path_result = shutil.which("tesseract")
    if path_result:
        tesseract_path = Path(path_result)
    elif sys.platform == "win32":
        # Check common Windows locations
        for path in WINDOWS_TESSERACT_PATHS:
            if path.exists():
                tesseract_path = path
                break

    if tesseract_path:
        tesseract_dir = tesseract_path.parent

        # On Windows, add to PATH if not already there
        if sys.platform == "win32" and not path_result:
            os.environ["PATH"] = str(tesseract_dir) + os.pathsep + os.environ.get("PATH", "")

        # Always set TESSDATA_PREFIX if not already set (needed by pymupdf)
        if "TESSDATA_PREFIX" not in os.environ:
            tessdata_dir = tesseract_dir / "tessdata"
            if tessdata_dir.exists():
                os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)

    return tesseract_path


# Configure Tesseract before importing pymupdf (which may use it)
_find_tesseract_early()

# Activate PyMuPDF Layout before importing pymupdf4llm for enhanced layout detection
import pymupdf.layout

pymupdf.layout.activate()

import pymupdf4llm


@click.group()
@click.version_option()
def main():
    """PDF command-line tools."""
    pass


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--to",
    "output_format",
    type=click.Choice(["markdown", "md"]),
    required=True,
    help="Output format",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (defaults to {input}.md)",
)
@click.option(
    "--stdout",
    "use_stdout",
    is_flag=True,
    default=False,
    help="Write output to stdout instead of file",
)
@click.option(
    "--write-images",
    is_flag=True,
    default=False,
    help="Extract images to a directory (default: {input}_images)",
)
@click.option(
    "--image-dir",
    type=click.Path(path_type=Path),
    help="Directory for extracted images (default: {input}_images)",
)
def convert(input_file: Path, output_format: str, output: Path | None, use_stdout: bool, write_images: bool, image_dir: Path | None):
    """Convert PDF to other formats."""
    # Resolve to absolute path to avoid issues with pymupdf-layout image paths
    input_file = input_file.resolve()

    if output_format in ("markdown", "md"):
        # Default output is {input_stem}.md unless --stdout is specified
        if output is None and not use_stdout:
            output = input_file.with_suffix(".md")

        kwargs = {}
        if write_images:
            kwargs["write_images"] = True
            # Default image directory is {input_stem}_images
            if image_dir is None:
                image_dir = input_file.parent / f"{input_file.stem}_images"
            else:
                image_dir = image_dir.resolve()
            # Create the image directory if it doesn't exist
            image_dir.mkdir(parents=True, exist_ok=True)
            kwargs["image_path"] = str(image_dir)

        md_text = pymupdf4llm.to_markdown(str(input_file), **kwargs)

        if use_stdout:
            # Write UTF-8 bytes directly to stdout to avoid Windows encoding issues
            sys.stdout.buffer.write(md_text.encode("utf-8"))
        else:
            output.write_text(md_text, encoding="utf-8")
            click.echo(f"Converted to {output}", err=True)


def find_tesseract() -> Path | None:
    """Find Tesseract executable, checking PATH and common Windows locations."""
    # First check PATH
    path_result = shutil.which("tesseract")
    if path_result:
        return Path(path_result)

    # On Windows, check common installation locations
    if sys.platform == "win32":
        for path in WINDOWS_TESSERACT_PATHS:
            if path.exists():
                return path

    return None


def configure_tesseract() -> Path | None:
    """Find Tesseract and configure environment if found outside PATH."""
    tesseract_path = find_tesseract()
    if tesseract_path and sys.platform == "win32":
        # If found but not in PATH, add to PATH for subprocess calls
        tesseract_dir = str(tesseract_path.parent)
        if tesseract_dir.lower() not in os.environ.get("PATH", "").lower():
            os.environ["PATH"] = tesseract_dir + os.pathsep + os.environ.get("PATH", "")
        # Set TESSDATA_PREFIX if not already set
        tessdata_dir = tesseract_path.parent / "tessdata"
        if tessdata_dir.exists() and "TESSDATA_PREFIX" not in os.environ:
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)
    return tesseract_path


def is_tesseract_installed() -> bool:
    """Check if Tesseract OCR is installed and available."""
    return find_tesseract() is not None


@main.command()
def check():
    """Check if optional dependencies are installed."""
    # Check Tesseract
    tesseract_path = find_tesseract()
    if tesseract_path:
        in_path = shutil.which("tesseract") is not None
        status = "installed" if in_path else "installed (auto-configured)"
        click.echo(f"Tesseract OCR: {status}")
        click.echo(f"  Executable: {tesseract_path}")

        # Show TESSDATA_PREFIX
        tessdata_prefix = os.environ.get("TESSDATA_PREFIX")
        if tessdata_prefix:
            click.echo(f"  TESSDATA_PREFIX: {tessdata_prefix}")

        # Check for tessdata and languages
        tessdata_dir = tesseract_path.parent / "tessdata"
        if tessdata_dir.exists():
            langs = sorted([p.stem for p in tessdata_dir.glob("*.traineddata")])
            click.echo(f"  Languages ({len(langs)}): {', '.join(langs)}")
    else:
        click.echo("Tesseract OCR: not found")
        click.echo("  OCR for scanned PDFs will not be available.")
        click.echo("  See: https://github.com/UB-Mannheim/tesseract/wiki")


if __name__ == "__main__":
    main()
