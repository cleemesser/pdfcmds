"""
Test demonstrating pymupdf-layout bug: image_path parameter is ignored.

When pymupdf.layout.activate() is called before importing pymupdf4llm,
the image_path parameter passed to to_markdown() is ignored. Images are
written to the source PDF's directory instead of the specified path.

This test is expected to FAIL until the upstream bug is fixed.
"""

import tempfile
from pathlib import Path
import pytest

# Activate layout BEFORE importing pymupdf4llm
import pymupdf.layout

pymupdf.layout.activate()
import pymupdf4llm  # ignore: E402

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_PDF = DATA_DIR / "paper-with-figures.pdf"


@pytest.fixture
def cleanup_pdf_dir_images():
    """Clean up any PNG images created in the PDF's directory during test."""
    existing = set(DATA_DIR.glob("*.png"))
    yield
    # Remove any new PNGs created during the test
    for png in set(DATA_DIR.glob("*.png")) - existing:
        png.unlink()


@pytest.mark.xfail(reason="pymupdf-layout bug: image_path parameter is ignored")
def test_image_path_parameter_respected(cleanup_pdf_dir_images):
    """Test that image_path parameter is respected by to_markdown().

    Expected: Images written to the specified image_path directory
    Actual (bug): Images written to the PDF's parent directory
    """
    pdf_path = SAMPLE_PDF.resolve()
    pdf_dir = pdf_path.parent
    existing_images = set(pdf_dir.glob("*.png"))

    with tempfile.TemporaryDirectory() as tmpdir:
        image_dir = Path(tmpdir) / "images"
        image_dir.mkdir()

        pymupdf4llm.to_markdown(
            str(pdf_path),
            write_images=True,
            image_path=str(image_dir),
        )

        # Check where images actually went
        images_in_requested_dir = list(image_dir.glob("*.png"))
        images_in_pdf_dir = list(set(pdf_dir.glob("*.png")) - existing_images)

        # This assertion fails due to the bug
        assert len(images_in_requested_dir) > 0, (
            f"Expected images in {image_dir}, but found {len(images_in_pdf_dir)} "
            f"in PDF directory instead"
        )
        assert len(images_in_pdf_dir) == 0, (
            f"Images should not be written to PDF directory, "
            f"but found {len(images_in_pdf_dir)} there"
        )
