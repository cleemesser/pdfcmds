"""Tests for PDF conversion."""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from pdfcmds.cli import main

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_PDF = DATA_DIR / "paper-with-figures.pdf"


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def cleanup_images():
    """Clean up any images created during tests."""
    yield
    # pymupdf-layout writes images next to the PDF, so clean them up
    for png in DATA_DIR.glob("*.png"):
        png.unlink()


class TestConvert:
    """Tests for the convert command."""

    def test_convert_to_markdown_stdout(self, runner):
        """Test converting PDF to markdown output to stdout."""
        result = runner.invoke(main, ["convert", "--to", "markdown", str(SAMPLE_PDF)])
        assert result.exit_code == 0
        assert len(result.output) > 0
        # Check that we got some markdown content
        assert "#" in result.output or result.output.strip()

    def test_convert_to_markdown_file(self, runner):
        """Test converting PDF to markdown output to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            result = runner.invoke(
                main,
                ["convert", "--to", "markdown", str(SAMPLE_PDF), "-o", str(output_path)],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert len(content) > 0

    def test_convert_with_image_extraction(self, runner):
        """Test converting PDF to markdown with image extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            result = runner.invoke(
                main,
                [
                    "convert",
                    "--to", "markdown",
                    str(SAMPLE_PDF),
                    "-o", str(output_path),
                    "--write-images",
                ],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            # Check that markdown contains image references
            assert "![" in content, "Expected markdown to contain image references"
            assert ".png" in content, "Expected markdown to reference PNG images"
            # Verify images were actually created (pymupdf-layout writes them next to PDF)
            image_files = list(DATA_DIR.glob("*.png"))
            assert len(image_files) > 0, "Expected at least one image to be extracted"


class TestCheck:
    """Tests for the check command."""

    def test_check_runs(self, runner):
        """Test that check command runs without error."""
        result = runner.invoke(main, ["check"])
        assert result.exit_code == 0
        assert "Tesseract OCR:" in result.output
