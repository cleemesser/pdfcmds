"""Tests for relative image path handling in markdown output."""

import os
import re
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from pdfcmds.cli import _make_image_paths_relative, _try_relative, main

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_PDF = DATA_DIR / "power2022-grokking.pdf"
SAMPLE_PDF_RELATIVE = "tests/data/power2022-grokking.pdf"


@pytest.fixture
def runner():
    return CliRunner()


def _extract_image_paths(md_text: str) -> list[str]:
    """Extract all image paths from markdown image syntax."""
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text)


class TestTryRelative:
    """Unit tests for _try_relative helper."""

    def test_absolute_path_made_relative(self):
        output_dir = Path("/project/docs")
        result = _try_relative("/project/docs/images/fig.png", output_dir)
        assert result == "images/fig.png"

    def test_absolute_path_outside_output_dir_unchanged(self):
        output_dir = Path("/project/docs")
        result = _try_relative("/other/place/fig.png", output_dir)
        assert result == "/other/place/fig.png"

    def test_cwd_relative_path_made_relative_to_output_dir(self, tmp_path):
        """Key bug test: CWD-relative paths should be relativized to output_dir."""
        # Simulate: CWD is /project, image path is "sub/dir/images/fig.png",
        # output_dir is /project/sub/dir
        img_dir = tmp_path / "sub" / "dir" / "images"
        img_dir.mkdir(parents=True)
        img_file = img_dir / "fig.png"
        img_file.touch()

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _try_relative("sub/dir/images/fig.png", tmp_path / "sub" / "dir")
            assert result == "images/fig.png"
        finally:
            os.chdir(original_cwd)

    def test_relative_path_same_dir(self, tmp_path):
        """Relative path already in output_dir should become just the filename."""
        img_file = tmp_path / "fig.png"
        img_file.touch()

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _try_relative("fig.png", tmp_path)
            assert result == "fig.png"
        finally:
            os.chdir(original_cwd)


class TestMakeImagePathsRelative:
    """Unit tests for _make_image_paths_relative."""

    def test_absolute_paths_converted(self):
        md = "![fig1](/docs/images/a.png)\ntext\n![fig2](/docs/images/b.png)"
        result = _make_image_paths_relative(md, Path("/docs"))
        assert "![fig1](images/a.png)" in result
        assert "![fig2](images/b.png)" in result

    def test_already_relative_paths_unchanged(self, tmp_path):
        """Paths already relative to output_dir should stay the same."""
        img_dir = tmp_path / "images"
        img_dir.mkdir()
        (img_dir / "a.png").touch()

        md = "![](images/a.png)"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _make_image_paths_relative(md, tmp_path)
            assert result == "![](images/a.png)"
        finally:
            os.chdir(original_cwd)

    def test_cwd_relative_paths_with_extra_prefix(self, tmp_path):
        """Reproduces the bug: CWD-relative paths with extra directory prefix."""
        # Setup: CWD=/project, output in /project/tests/data/out.md
        # pymupdf emits path: tests/data/stem_images/img.png
        # Correct relative from output_dir: stem_images/img.png
        sub = tmp_path / "tests" / "data" / "stem_images"
        sub.mkdir(parents=True)
        (sub / "img.png").touch()

        md = "![](tests/data/stem_images/img.png)"
        output_dir = tmp_path / "tests" / "data"

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _make_image_paths_relative(md, output_dir)
            assert result == "![](stem_images/img.png)"
        finally:
            os.chdir(original_cwd)

    def test_non_image_markdown_untouched(self):
        md = "# Title\n[link](http://example.com)\nsome text"
        result = _make_image_paths_relative(md, Path("/docs"))
        assert result == md


class TestConvertImagePaths:
    """Integration tests for image path correctness in convert output."""

    def test_write_images_paths_are_relative(self, runner):
        """All image paths in output should be relative, not absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            image_dir = Path(tmpdir) / "images"
            result = runner.invoke(
                main,
                [
                    "convert", "--to", "markdown",
                    str(SAMPLE_PDF),
                    "-o", str(output_path),
                    "--write-images",
                    "--image-dir", str(image_dir),
                ],
            )
            assert result.exit_code == 0
            content = output_path.read_text(encoding="utf-8")
            img_paths = _extract_image_paths(content)
            assert len(img_paths) > 0, "Expected image references in output"
            for p in img_paths:
                assert not Path(p).is_absolute(), f"Image path should be relative: {p}"

    def test_write_images_no_extra_prefix(self, runner):
        """Image paths should not contain extra directory prefixes from CWD."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            image_dir = Path(tmpdir) / "my_images"
            result = runner.invoke(
                main,
                [
                    "convert", "--to", "markdown",
                    str(SAMPLE_PDF),
                    "-o", str(output_path),
                    "--write-images",
                    "--image-dir", str(image_dir),
                ],
            )
            assert result.exit_code == 0
            content = output_path.read_text(encoding="utf-8")
            img_paths = _extract_image_paths(content)
            for p in img_paths:
                assert p.startswith("my_images/"), (
                    f"Expected path to start with 'my_images/', got: {p}"
                )

    def test_relative_input_path_image_links(self, runner):
        """Using a relative input path should still produce correct relative image links."""
        project_root = DATA_DIR.parent.parent
        original_cwd = os.getcwd()
        try:
            os.chdir(project_root)
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "output.md"
                image_dir = Path(tmpdir) / "imgs"
                result = runner.invoke(
                    main,
                    [
                        "convert", "--to", "markdown",
                        SAMPLE_PDF_RELATIVE,
                        "-o", str(output_path),
                        "--write-images",
                        "--image-dir", str(image_dir),
                    ],
                )
                assert result.exit_code == 0
                content = output_path.read_text(encoding="utf-8")
                img_paths = _extract_image_paths(content)
                for p in img_paths:
                    assert not Path(p).is_absolute(), (
                        f"Image path should be relative: {p}"
                    )
                    # Should not contain CWD-relative prefix like "tests/data/"
                    assert not p.startswith("tests/"), (
                        f"Image path has extra CWD prefix: {p}"
                    )
        finally:
            os.chdir(original_cwd)

    def test_default_image_dir_paths(self, runner):
        """Default image dir (stem_images) should produce clean relative paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy PDF to tmpdir so default image dir is created there
            import shutil
            tmp_pdf = Path(tmpdir) / "test.pdf"
            shutil.copy2(SAMPLE_PDF, tmp_pdf)
            output_path = Path(tmpdir) / "test.md"
            result = runner.invoke(
                main,
                [
                    "convert", "--to", "markdown",
                    str(tmp_pdf),
                    "-o", str(output_path),
                    "--write-images",
                ],
            )
            assert result.exit_code == 0
            content = output_path.read_text(encoding="utf-8")
            img_paths = _extract_image_paths(content)
            for p in img_paths:
                assert p.startswith("test_images/"), (
                    f"Expected path like 'test_images/...', got: {p}"
                )
