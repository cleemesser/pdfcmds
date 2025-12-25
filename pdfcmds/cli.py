"""Command-line interface for pdfcmds."""

import os
import re
import shutil
import sys
from pathlib import Path

import click

# Common Tesseract installation paths on Windows
WINDOWS_TESSERACT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path(
        os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"
    ),
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
            os.environ["PATH"] = (
                str(tesseract_dir) + os.pathsep + os.environ.get("PATH", "")
            )

        # Always set TESSDATA_PREFIX if not already set (needed by pymupdf)
        if "TESSDATA_PREFIX" not in os.environ:
            tessdata_dir = tesseract_dir / "tessdata"
            if tessdata_dir.exists():
                os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)

    return tesseract_path


# Configure Tesseract before importing pymupdf (which may use it)
_find_tesseract_early()

# Activate PyMuPDF Layout before importing pymupdf4llm for enhanced layout detection
# it is possible this could be moved before the Tesseract configuration above
import pymupdf.layout  # noqa: E402

pymupdf.layout.activate()

import pymupdf4llm  # noqa:E402


def _try_relative(img_path: str, output_dir: Path) -> str:
    """Try to convert an image path to be relative to output_dir."""
    try:
        abs_path = Path(img_path)
        if abs_path.is_absolute():
            return abs_path.relative_to(output_dir).as_posix()  # I love pathlib so much
    except ValueError:
        pass
    return img_path


def _make_image_paths_relative(md_text: str, output_dir: Path) -> str:
    """Convert absolute image paths in markdown to relative paths."""
    # Match markdown image syntax: ![alt](path)
    return re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f"![{m.group(1)}]({_try_relative(m.group(2), output_dir)})",
        md_text,
    )


def _move_images_to_correct_dir(
    pdf_dir: Path, image_dir: Path, md_text: str, existing_images: set[Path]
) -> str:
    """Move images from PDF directory to specified image_dir and update markdown.

    Workaround for pymupdf-layout bug where image_path parameter is ignored.
    Images are written to the PDF's directory instead of the specified path.
    """
    # Find new images created by to_markdown()
    current_images = set(pdf_dir.glob("*.png"))
    new_images = current_images - existing_images

    # Move each new image to the target directory
    for img in new_images:
        dest = image_dir / img.name
        shutil.move(str(img), str(dest))

    # Update markdown to reference new locations
    for img in new_images:
        old_path = str(img)
        new_path = str(image_dir / img.name)
        md_text = md_text.replace(old_path, new_path)

    return md_text


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
    "--embed-images",
    is_flag=True,
    default=False,
    help="Embed images as base64 in the markdown output",
)
@click.option(
    "--image-dir",
    type=click.Path(path_type=Path),
    help="Directory for extracted images (default: {input}_images)",
)
def convert(
    input_file: Path,
    output_format: str,
    output: Path | None,
    use_stdout: bool,
    write_images: bool,
    embed_images: bool,
    image_dir: Path | None,
):
    """Convert PDF to other formats."""
    # Validate mutually exclusive options
    if write_images and embed_images:
        raise click.UsageError(
            "--write-images and --embed-images are mutually exclusive"
        )

    # Resolve to absolute path to avoid pymupdf-layout path concatenation issues
    input_file = input_file.resolve()

    if output_format in ("markdown", "md"):
        # Default output is {input_stem}.md unless --stdout is specified
        if output is None and not use_stdout:
            output = input_file.with_suffix(".md")

        kwargs = {}
        pdf_dir = input_file.parent
        existing_images = set()

        if embed_images:
            kwargs["embed_images"] = True
        elif write_images:
            kwargs["write_images"] = True
            # Default image directory is {input_stem}_images
            if image_dir is None:
                image_dir = pdf_dir / f"{input_file.stem}_images"
            else:
                image_dir = image_dir.resolve()
            # Create the image directory if it doesn't exist
            image_dir.mkdir(parents=True, exist_ok=True)
            kwargs["image_path"] = str(image_dir)
            # Record existing images before conversion (for workaround)
            existing_images = set(pdf_dir.glob("*.png"))

        md_text = pymupdf4llm.to_markdown(str(input_file), **kwargs)

        # Workaround: pymupdf-layout ignores image_path and writes to PDF directory
        # Move images to the correct location and update markdown paths
        if write_images:
            md_text = _move_images_to_correct_dir(
                pdf_dir, image_dir, md_text, existing_images
            )

        # Convert absolute image paths to relative (pymupdf-layout uses absolute paths)
        if write_images and output:
            md_text = _make_image_paths_relative(md_text, output.parent.resolve())

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
    # tesseract_path = find_tesseract()
    tesseract_path = _find_tesseract_early()
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
