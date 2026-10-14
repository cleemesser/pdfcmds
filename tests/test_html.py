"""Tests for PDF to HTML conversion (`pdf convert --to html`)."""

import re
from pathlib import Path

import pymupdf
import pytest
from click.testing import CliRunner

from pdfcmds.cli import main

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_PDF = DATA_DIR / "power2022-grokking.pdf"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def cleanup_files():
    """Remove files a test may leave next to the sample PDF."""
    yield
    (DATA_DIR / "power2022-grokking.html").unlink(missing_ok=True)
    for png in DATA_DIR.glob("*.png"):
        png.unlink()


class TestMarkdownToHtml:
    """The rendering rule: pymupdf4llm's own breaks survive, PDF text stays inert."""

    def test_table_cell_breaks_stay_html(self):
        from pdfcmds.cli import _markdown_to_html

        html = _markdown_to_html("|Name|Role|\n|---|---|\n|Ann<br>Lee|PI|\n")
        assert "<br>" in html
        assert "&lt;br&gt;" not in html

    def test_html_in_document_text_stays_escaped(self):
        from pdfcmds.cli import _markdown_to_html

        html = _markdown_to_html("before <script>alert(1)</script> after")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "alert(1)" in html


class TestHtmlDocument:
    """The output is a complete HTML document, not a fragment."""

    def test_default_output_is_a_full_html_document(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main, ["convert", "--to", "html", str(SAMPLE_PDF), "-o", str(output)]
        )
        assert result.exit_code == 0, result.output
        html = output.read_text(encoding="utf-8")
        assert html.lstrip().lower().startswith("<!doctype html>")
        assert '<meta charset="utf-8">' in html.lower()
        assert "<h1" in html or "<h2" in html

    def test_default_output_path_uses_html_suffix(self, runner):
        result = runner.invoke(main, ["convert", "--to", "html", str(SAMPLE_PDF)])
        assert result.exit_code == 0, result.output
        assert (DATA_DIR / "power2022-grokking.html").exists()

    def test_title_falls_back_to_the_file_name(self, runner, tmp_path):
        output = tmp_path / "out.html"
        runner.invoke(main, ["convert", "--to", "html", str(SAMPLE_PDF), "-o", str(output)])
        assert "<title>power2022-grokking</title>" in output.read_text(encoding="utf-8")

    def test_stdout_writes_the_document(self, runner):
        result = runner.invoke(
            main, ["convert", "--to", "html", "--stdout", str(SAMPLE_PDF)]
        )
        assert result.exit_code == 0, result.output
        assert result.stdout.lower().startswith("<!doctype html>")
        assert "</html>" in result.stdout


class TestHtmlPageBoundaries:
    """One section per converted page, numbered the way the PDF numbers them."""

    def _sections(self, html):
        return re.findall(r'<section class="page" id="page-(\d+)" data-page="\1">', html)

    def test_every_page_gets_a_section(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main, ["convert", "--to", "html", str(SAMPLE_PDF), "-o", str(output)]
        )
        assert result.exit_code == 0, result.output
        with pymupdf.open(str(SAMPLE_PDF)) as doc:
            page_count = doc.page_count
        assert self._sections(output.read_text(encoding="utf-8")) == [
            str(n) for n in range(1, page_count + 1)
        ]

    def test_pages_option_selects_those_sections(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main,
            [
                "convert", "--to", "html", str(SAMPLE_PDF),
                "-o", str(output), "--pages", "2-3,5",
            ],
        )
        assert result.exit_code == 0, result.output
        assert self._sections(output.read_text(encoding="utf-8")) == ["2", "3", "5"]

    def test_start_and_end_are_one_based_and_inclusive(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main,
            ["convert", "--to", "html", str(SAMPLE_PDF), "-o", str(output), "--start", "2", "--end", "3"],
        )
        assert result.exit_code == 0, result.output
        assert self._sections(output.read_text(encoding="utf-8")) == ["2", "3"]


class TestHtmlImages:
    """Figures ride inside the document, unless told otherwise."""

    def test_images_are_inlined_by_default(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main, ["convert", "--to", "html", str(SAMPLE_PDF), "-o", str(output)]
        )
        assert result.exit_code == 0, result.output
        html = output.read_text(encoding="utf-8")
        assert '<img src="data:image/' in html
        assert not list(tmp_path.glob("*.png")), "no companion image files expected"

    def test_no_images_leaves_them_out(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main,
            [
                "convert", "--to", "html", str(SAMPLE_PDF),
                "-o", str(output), "--no-images",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "<img" not in output.read_text(encoding="utf-8")


class TestHtmlSecurity:
    """A PDF that carries markup must not inject it into the output."""

    def test_script_text_in_the_pdf_is_not_a_live_tag(self, runner, tmp_path):
        pdf = tmp_path / "evil.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), "<script>alert(1)</script>")
            doc.save(str(pdf))

        output = tmp_path / "out.html"
        result = runner.invoke(
            main, ["convert", "--to", "html", str(pdf), "-o", str(output)]
        )
        assert result.exit_code == 0, result.output
        html = output.read_text(encoding="utf-8")
        assert "<script>" not in html
        assert "alert(1)" in html  # the text is kept, only its markup is neutralised


class TestHtmlEncrypted:
    def _encrypted(self, tmp_path):
        pdf = tmp_path / "encrypted.pdf"
        with pymupdf.open(str(SAMPLE_PDF)) as doc:
            doc.save(
                str(pdf),
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner",
                user_pw="secret",
            )
        return pdf

    def test_correct_password_converts(self, runner, tmp_path):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main,
            [
                "convert", "--to", "html", str(self._encrypted(tmp_path)),
                "-o", str(output), "--password", "secret", "--pages", "1",
            ],
        )
        assert result.exit_code == 0, result.output
        assert output.exists()

    def test_bad_password_is_a_clean_error(self, runner, tmp_path):
        result = runner.invoke(
            main,
            [
                "convert", "--to", "html", str(self._encrypted(tmp_path)),
                "-o", str(tmp_path / "out.html"), "--password", "wrong", "--pages", "1",
            ],
        )
        assert result.exit_code != 0
        assert "Incorrect password" in result.output


class TestHtmlOptionMatrix:
    """Each format keeps to the options it understands."""

    @pytest.mark.parametrize(
        "args, expected",
        [
            (["--to", "html", "--write-images"], "only valid with --to markdown"),
            (["--to", "html", "--embed-images"], "only valid with --to markdown"),
            (["--to", "html", "--image-dir", "x"], "only valid with --to markdown"),
            (["--to", "html", "--multi-processing"], "only valid with --to docx"),
            (["--to", "html", "--ocr-mode", "ocred"], "only valid with --to docx"),
            (["--to", "html", "-v"], "only valid with --to docx"),
            (["--to", "markdown", "--no-images"], "only valid with --to html"),
            (["--to", "docx", "--no-images"], "only valid with --to html"),
        ],
    )
    def test_rejected_combinations(self, runner, args, expected):
        result = runner.invoke(main, ["convert", *args, str(SAMPLE_PDF)])
        assert result.exit_code != 0
        assert expected in result.output

    @pytest.mark.parametrize("flag", [["--pages", "1"], ["--start", "1"], ["--end", "1"]])
    def test_page_options_are_accepted_for_html(self, runner, tmp_path, flag):
        output = tmp_path / "out.html"
        result = runner.invoke(
            main, ["convert", "--to", "html", str(SAMPLE_PDF), "-o", str(output), *flag]
        )
        assert result.exit_code == 0, result.output
