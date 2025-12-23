"""Tests for PDF conversion."""

import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from pdfcmds.cli import main

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_PDF = DATA_DIR / "paper-with-figures.pdf"
# Relative path from project root for testing relative path handling
SAMPLE_PDF_RELATIVE = "tests/data/paper-with-figures.pdf"


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def cleanup_files():
    """Clean up any files created during tests."""
    yield
    # pymupdf-layout writes images next to the PDF, so clean them up
    for png in DATA_DIR.glob("*.png"):
        png.unlink()
    # Clean up default .md output files
    default_md = DATA_DIR / "paper-with-figures.md"
    if default_md.exists():
        default_md.unlink()


class TestConvert:
    """Tests for the convert command."""

    def test_convert_to_markdown_default_output(self, runner):
        """Test converting PDF to markdown with default output file."""
        result = runner.invoke(main, ["convert", "--to", "markdown", str(SAMPLE_PDF)])
        assert result.exit_code == 0
        # Check default output file was created
        default_output = SAMPLE_PDF.with_suffix(".md")
        assert default_output.exists()
        content = default_output.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_convert_to_markdown_stdout(self, runner):
        """Test converting PDF to markdown with --stdout flag."""
        result = runner.invoke(
            main, ["convert", "--to", "markdown", "--stdout", str(SAMPLE_PDF)]
        )
        assert result.exit_code == 0
        # Output should be in stdout, not a file
        assert len(result.output) > 0

    def test_convert_to_markdown_file(self, runner):
        """Test converting PDF to markdown output to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            result = runner.invoke(
                main,
                [
                    "convert",
                    "--to",
                    "markdown",
                    str(SAMPLE_PDF),
                    "-o",
                    str(output_path),
                ],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert len(content) > 0

    def test_convert_with_image_extraction(self, runner):
        """Test converting PDF to markdown with image extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            image_dir = Path(tmpdir) / "images"
            result = runner.invoke(
                main,
                [
                    "convert",
                    "--to",
                    "markdown",
                    str(SAMPLE_PDF),
                    "-o",
                    str(output_path),
                    "--write-images",
                    "--image-dir",
                    str(image_dir),
                ],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            # Check that markdown contains image references
            assert "![" in content, "Expected markdown to contain image references"
            assert ".png" in content, "Expected markdown to reference PNG images"
            # Verify images were extracted to the specified directory (not PDF directory)
            image_files = list(image_dir.glob("*.png"))
            assert len(image_files) > 0, "Expected at least one image in --image-dir"
            # Verify no images were left in PDF directory (the bug we fixed)
            pdf_dir_images = list(DATA_DIR.glob("*.png"))
            assert len(pdf_dir_images) == 0, "Images should not be in PDF directory"

    def test_convert_with_relative_path_and_images(self, runner):
        """Test converting PDF using relative path with image extraction.

        This test ensures that relative paths are handled correctly by pymupdf-layout.
        Previously, relative paths caused image save errors.
        """
        # Change to project root so relative path is valid
        project_root = DATA_DIR.parent.parent
        original_cwd = os.getcwd()
        try:
            os.chdir(project_root)
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "output.md"
                result = runner.invoke(
                    main,
                    [
                        "convert",
                        "--to",
                        "markdown",
                        SAMPLE_PDF_RELATIVE,  # Use relative path
                        "-o",
                        str(output_path),
                        "--write-images",
                    ],
                )
                assert result.exit_code == 0, f"Command failed: {result.output}"
                assert output_path.exists()
        finally:
            os.chdir(original_cwd)

    def test_convert_with_embed_images(self, runner):
        """Test converting PDF to markdown with embedded base64 images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            result = runner.invoke(
                main,
                [
                    "convert",
                    "--to",
                    "markdown",
                    str(SAMPLE_PDF),
                    "-o",
                    str(output_path),
                    "--embed-images",
                ],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            # Check that markdown contains base64 embedded images
            assert "data:image" in content, (
                "Expected markdown to contain base64 embedded images"
            )

    def test_write_and_embed_images_mutually_exclusive(self, runner):
        """Test that --write-images and --embed-images cannot be used together."""
        result = runner.invoke(
            main,
            [
                "convert",
                "--to",
                "markdown",
                str(SAMPLE_PDF),
                "--write-images",
                "--embed-images",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestCheck:
    """Tests for the check command."""

    def test_check_runs(self, runner):
        """Test that check command runs without error."""
        result = runner.invoke(main, ["check"])
        assert result.exit_code == 0
        assert "Tesseract OCR:" in result.output
