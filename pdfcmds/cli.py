"""Command-line interface for pdfcmds."""

import logging
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

# definining _find_tesseract_early() here as it may be that found on import of pymupdf/pymupdf.layout

def _find_tesseract_early() -> Path | None:
    """Configure Tesseract environment before pymupdf imports.

    if find in common windows locations, will add the the environment
    os.environ["PATH"] if it is not already there

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




def _make_image_paths_relative(md_text: str, output_dir: Path) -> str:
    """Convert absolute image paths in markdown text to relative paths.

    @md_text: str text of the markdown file
    @output_dir: Path to the base directory things should be relative to
    """

    # Match markdown image syntax: ![alt](path)
    # group(1) is the alt text
    # group(2) is the path to the image file
    # need to resolve this to an absolute path and then make it relative to the
    # base path output_dir
    return re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f"![{m.group(1)}]({Path(m.group(2)).resolve().relative_to(output_dir)})",
        md_text,
    )


# TODO: this bug is fixed so we should be able to to remove this workaround
# at next cleanup. This did work.
def _move_images_to_correct_dir(
    pdf_dir: Path, image_dir: Path, md_text: str, existing_images: set[Path]
) -> str:
    """Move images from PDF directory to specified image_dir and update markdown.

    Workaround for pymupdf-layout bug where image_path parameter is ignored.
    Images are written to the PDF's directory instead of the specified path.

    @pdf_dir: Path to directory that holds the PDF
    @image_dir: Path to where the images *should* be.
    @md_text: markdown text which will need patching
    @existing_images: set of Paths to images
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


# Maps --ocr-mode to the vendored pdf2docx "ocr" setting. Upstream mode 1
# ("perform OCR") is deliberately unreachable: pdf2docx raises
# SystemExit("OCR feature is planned but not implemented yet.") for it.
# See pdfcmds/_vendor/pdf2docx/page/RawPageFitz.py.
OCR_MODES = {"none": 0, "ocred": 2}


def _parse_page_spec(spec: str, page_count: int) -> list[int]:
    """Turn a user page spec into zero-based page indexes for pdf2docx.

    @spec: comma-separated, 1-based pages and ranges, e.g. "1-3,7,10-"
    @page_count: number of pages in the PDF
    Returns a list of 0-based indexes for Converter.convert(pages=...).

    Pages beyond the document are clamped to it with a warning, rather than
    failing, so a spec can be reused across PDFs of differing lengths. Reversed
    ranges ("7-3") are rejected as typos. Duplicates and overlaps are kept in
    the order given; note that pdf2docx marks pages for parsing and then emits
    them in document order, so the ordering is not visible in the DOCX.
    """
    indexes: list[int] = []
    # Held back until we know the spec selects something: otherwise a spec that
    # is entirely out of range would report the same problem twice, once as a
    # warning per token and again as the error below.
    warnings: list[str] = []

    for token in spec.split(","):
        token = token.strip()
        if not token:
            raise click.UsageError(f"empty page in --pages {spec!r}")

        if token.endswith("-"):  # open-ended, e.g. "10-" meaning 10 to the end
            first, last = token[:-1], str(page_count)
        elif "-" in token:
            first, _, last = token.partition("-")
        else:
            first = last = token

        try:
            start, end = int(first), int(last)
        except ValueError:
            raise click.UsageError(
                f"invalid page {token!r} in --pages; expected pages and ranges "
                "like '1-3,7,10-'"
            ) from None

        if end < start:
            raise click.UsageError(
                f"reversed page range {token!r} in --pages; did you mean '{end}-{start}'?"
            )

        low, high = max(start, 1), min(end, page_count)
        if (low, high) != (start, end):
            if low > high:
                warnings.append(
                    f"--pages {token!r} selects no pages in a "
                    f"{page_count}-page document; ignoring"
                )
            else:
                warnings.append(
                    f"--pages {token!r} clamped to {low}-{high} in a "
                    f"{page_count}-page document"
                )

        indexes.extend(range(low - 1, high))  # 1-based inclusive -> 0-based

    if not indexes:
        raise click.UsageError(
            f"--pages {spec!r} selects no pages in a {page_count}-page document"
        )

    for warning in warnings:
        click.echo(f"Warning: {warning}", err=True)

    return indexes


def _convert_to_markdown(
    input_file: Path,
    output: Path | None,
    use_stdout: bool,
    write_images: bool,
    embed_images: bool,
    image_dir: Path | None,
):
    """Convert a PDF to markdown using pymupdf4llm."""
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
    # This workaround is no longer needed since the bug is fixed,
    # but leaving the code here for reference until the next clean up
    # if write_images:
        # md_text = _move_images_to_correct_dir(
        #    pdf_dir, image_dir, md_text, existing_images
        #)


    # Convert absolute image paths to relative (pymupdf-layout uses absolute paths)
    if write_images and output:
        md_text = _make_image_paths_relative(md_text, output.parent.resolve())

    if use_stdout:
        # Write UTF-8 bytes directly to stdout to avoid Windows encoding issues
        sys.stdout.buffer.write(md_text.encode("utf-8"))
    else:
        output.write_text(md_text, encoding="utf-8")
        click.echo(f"Converted to {output}", err=True)


def _convert_to_docx(
    input_file: Path,
    output: Path | None,
    use_stdout: bool,
    pages: str | None,
    start: int | None,
    end: int | None,
    password: str | None,
    ocr_mode: str,
    multi_processing: bool,
    cpu_count: int | None,
    verbose: bool,
):
    """Convert a PDF to DOCX using the vendored pdf2docx."""
    # Imported lazily: pdf2docx pulls in python-docx, numpy and cv2, which
    # markdown conversion and `pdf check` should not have to pay for.
    from ._vendor.pdf2docx import Converter
    from ._vendor.pdf2docx.converter import ConversionException

    # pdf2docx reports per-page progress on the *root* logger via logging.info.
    # Its own logging.basicConfig call is patched out when vendoring (see
    # VENDOR.md), so nothing is emitted unless we ask for it here. basicConfig
    # is no good for that: it silently does nothing when the root logger already
    # has handlers. Attach our own and take it back off afterwards, so a single
    # conversion cannot permanently reconfigure logging for the host process.
    root_logger = logging.getLogger()
    handler = None
    previous_level = root_logger.level
    if verbose:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    # Default output is {input_stem}.docx unless --stdout is specified
    if output is None and not use_stdout:
        output = input_file.with_suffix(".docx")

    settings = {
        "ocr": OCR_MODES[ocr_mode],
        "multi_processing": multi_processing,
    }
    if cpu_count is not None:
        settings["cpu_count"] = cpu_count

    # pdf2docx takes 0-based page indexes, with start/end as a half-open slice.
    # The CLI speaks 1-based inclusive pages.
    if pages:
        with pymupdf.open(str(input_file)) as doc:
            page_count = doc.page_count
        settings["pages"] = _parse_page_spec(pages, page_count)
    else:
        settings["start"] = start - 1 if start else 0
        if end is not None:
            settings["end"] = end

    target = sys.stdout.buffer if use_stdout else str(output)

    converter = Converter(str(input_file), password=password)
    try:
        converter.convert(target, **settings)
    except ConversionException as exc:
        # Surface pdf2docx's own errors (bad password, bad page range) as clean
        # CLI messages rather than tracebacks.
        raise click.ClickException(str(exc)) from exc
    finally:
        # Converter has no context manager protocol.
        converter.close()
        if handler is not None:
            root_logger.removeHandler(handler)
            root_logger.setLevel(previous_level)

    if not use_stdout:
        click.echo(f"Converted to {output}", err=True)


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
    type=click.Choice(["markdown", "md", "docx"]),
    required=True,
    help="Output format",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (defaults to {input}.md or {input}.docx)",
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
@click.option(
    "--pages",
    help="docx only: pages to convert, 1-based, e.g. '1-3,7' (cannot combine with --start/--end)",
)
@click.option(
    "--start",
    type=int,
    help="docx only: first page to convert, 1-based (default: 1)",
)
@click.option(
    "--end",
    type=int,
    help="docx only: last page to convert, 1-based and inclusive (default: last)",
)
@click.option(
    "--password",
    help="docx only: password for an encrypted PDF",
)
@click.option(
    "--ocr-mode",
    type=click.Choice(["none", "ocred"]),
    default="none",
    show_default=True,
    help=(
        "docx only: 'ocred' reads the hidden text layer of an already-OCR-ed PDF "
        "and skips images. This does not run OCR"
    ),
)
@click.option(
    "--multi-processing",
    is_flag=True,
    default=False,
    help="docx only: parse pages in parallel (cannot combine with --pages)",
)
@click.option(
    "--cpu-count",
    type=int,
    help="docx only: worker count for --multi-processing (default: all cores)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="docx only: report per-page conversion progress",
)
def convert(
    input_file: Path,
    output_format: str,
    output: Path | None,
    use_stdout: bool,
    write_images: bool,
    embed_images: bool,
    image_dir: Path | None,
    pages: str | None,
    start: int | None,
    end: int | None,
    password: str | None,
    ocr_mode: str,
    multi_processing: bool,
    cpu_count: int | None,
    verbose: bool,
):
    """Convert PDF to other formats."""
    # Validate mutually exclusive options
    if write_images and embed_images:
        raise click.UsageError(
            "--write-images and --embed-images are mutually exclusive"
        )

    markdown_only = {
        "--write-images": write_images,
        "--embed-images": embed_images,
        "--image-dir": image_dir is not None,
    }
    docx_only = {
        "--pages": pages is not None,
        "--start": start is not None,
        "--end": end is not None,
        "--password": password is not None,
        "--ocr-mode": ocr_mode != "none",
        "--multi-processing": multi_processing,
        "--cpu-count": cpu_count is not None,
        "--verbose": verbose,
    }
    used_by_format = markdown_only if output_format == "docx" else docx_only
    misused = [name for name, given in used_by_format.items() if given]
    if misused:
        other = "markdown" if output_format == "docx" else "docx"
        raise click.UsageError(
            f"{', '.join(misused)} {'are' if len(misused) > 1 else 'is'} only "
            f"valid with --to {other}"
        )

    # Resolve to absolute path to avoid pymupdf-layout path concatenation issues
    input_file = input_file.resolve()

    if output_format == "docx":
        if pages and (start is not None or end is not None):
            raise click.UsageError("--pages cannot be combined with --start/--end")
        # Upstream raises for this too, but only after opening the document.
        if pages and multi_processing:
            raise click.UsageError(
                "--multi-processing works with continuous pages only; "
                "use --start/--end instead of --pages"
            )
        if cpu_count is not None and not multi_processing:
            raise click.UsageError("--cpu-count requires --multi-processing")
        for name, value in (("--start", start), ("--end", end), ("--cpu-count", cpu_count)):
            if value is not None and value < 1:
                raise click.UsageError(f"{name} must be 1 or greater")
        if start is not None and end is not None and end < start:
            raise click.UsageError("--end must not be less than --start")

        _convert_to_docx(
            input_file,
            output,
            use_stdout,
            pages,
            start,
            end,
            password,
            ocr_mode,
            multi_processing,
            cpu_count,
            verbose,
        )
    else:
        _convert_to_markdown(
            input_file, output, use_stdout, write_images, embed_images, image_dir
        )


def find_tesseract() -> Path | None:
    """Find Tesseract executable, checking PATH and common Windows locations.
    This version does not add to the environment path"""
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
