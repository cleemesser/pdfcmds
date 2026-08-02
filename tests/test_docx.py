"""Tests for PDF to DOCX conversion via the vendored pdf2docx."""

import tempfile
import zipfile
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from docx import Document

from pdfcmds.cli import _parse_page_spec, main

DATA_DIR = Path(__file__).parent / "data"
SAMPLE_PDF = DATA_DIR / "power2022-grokking.pdf"

# The sample is a full paper; converting it whole is slow and proves nothing extra,
# so every test restricts the page range unless the range itself is under test.
FIRST_PAGE = ["--start", "1", "--end", "1"]


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def cleanup_files():
    """Remove DOCX files written next to the sample PDF."""
    yield
    for docx in DATA_DIR.glob("*.docx"):
        docx.unlink()


def paragraph_texts(path):
    """Non-empty paragraph texts from a DOCX file."""
    return [p.text for p in Document(str(path)).paragraphs if p.text.strip()]


class TestConvertDocx:
    """Tests for `convert --to docx`."""

    def test_default_output_path(self, runner):
        """Output defaults to {input}.docx next to the PDF."""
        result = runner.invoke(
            main, ["convert", "--to", "docx", str(SAMPLE_PDF), *FIRST_PAGE]
        )
        assert result.exit_code == 0, result.output
        default_output = SAMPLE_PDF.with_suffix(".docx")
        assert default_output.exists()
        assert paragraph_texts(default_output)

    def test_explicit_output_path(self, runner):
        """-o writes to the requested path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.docx"
            result = runner.invoke(
                main,
                ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output_path), *FIRST_PAGE],
            )
            assert result.exit_code == 0, result.output
            assert output_path.exists()
            texts = paragraph_texts(output_path)
            assert texts, "Expected non-empty text in the converted DOCX"
            # The sample is the grokking paper; its title is on page 1.
            assert any("GROKKING" in t.upper() for t in texts)

    def test_stdout_writes_valid_docx(self, runner):
        """--stdout emits the DOCX as bytes, not text."""
        result = runner.invoke(
            main, ["convert", "--to", "docx", str(SAMPLE_PDF), "--stdout", *FIRST_PAGE]
        )
        assert result.exit_code == 0, result.output
        payload = result.stdout_bytes
        # A DOCX is a zip; check the magic number and that it opens.
        assert payload[:2] == b"PK"
        with tempfile.TemporaryDirectory() as tmpdir:
            written = Path(tmpdir) / "from_stdout.docx"
            written.write_bytes(payload)
            assert zipfile.is_zipfile(written)
            assert paragraph_texts(written)

    def test_page_range_limits_content(self, runner):
        """--start/--end are 1-based and inclusive, and actually restrict output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            one_page = Path(tmpdir) / "one.docx"
            three_pages = Path(tmpdir) / "three.docx"
            for output, args in (
                (one_page, ["--start", "1", "--end", "1"]),
                (three_pages, ["--start", "1", "--end", "3"]),
            ):
                result = runner.invoke(
                    main,
                    ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output), *args],
                )
                assert result.exit_code == 0, result.output

            assert len(paragraph_texts(one_page)) < len(paragraph_texts(three_pages))

    def test_start_end_are_one_based_and_inclusive(self, runner):
        """--start/--end select the pages a human would name, not 0-based indexes.

        Asserted structurally rather than by looking for particular words: the
        paper's body text repeats its own title, so vocabulary does not identify
        a page. Each page's opening paragraph does.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = {}
            for label, args in (
                ("page1", ["--start", "1", "--end", "1"]),
                ("page2", ["--start", "2", "--end", "2"]),
                ("both", ["--start", "1", "--end", "2"]),
            ):
                output = Path(tmpdir) / f"{label}.docx"
                result = runner.invoke(
                    main,
                    ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output), *args],
                )
                assert result.exit_code == 0, result.output
                outputs[label] = paragraph_texts(output)

            first_of_page1 = outputs["page1"][0]
            first_of_page2 = outputs["page2"][0]
            assert first_of_page1 != first_of_page2, "pages 1 and 2 should differ"

            # "--start 1 --end 2" is inclusive of both named pages...
            assert first_of_page1 in outputs["both"]
            assert first_of_page2 in outputs["both"]
            # ...and "--start 2" begins at page 2, so page 1 is absent.
            assert first_of_page1 not in outputs["page2"]

    def test_verbose_reports_progress(self, runner):
        """-v surfaces pdf2docx per-page progress; the default run stays quiet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.docx"
            result = runner.invoke(
                main,
                ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output_path), "-v", *FIRST_PAGE],
            )
            assert result.exit_code == 0, result.output
            assert "Parsing pages" in result.output

    def test_ocr_mode_ocred_is_accepted(self, runner):
        """--ocr-mode ocred maps to pdf2docx ocr=2 and must not hit the ocr=1 SystemExit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.docx"
            result = runner.invoke(
                main,
                [
                    "convert", "--to", "docx", str(SAMPLE_PDF),
                    "-o", str(output_path), "--ocr-mode", "ocred", *FIRST_PAGE,
                ],
            )
            # The sample has a real text layer rather than an OCR one, so the
            # output may be sparse; what matters is that it does not blow up.
            assert result.exit_code == 0, result.output
            assert output_path.exists()


class TestDocxOptionValidation:
    """Options must be rejected when they do not apply to the chosen format."""

    @pytest.mark.parametrize(
        "args,expected",
        [
            (["--to", "docx", "--write-images"], "only valid with --to markdown"),
            (["--to", "docx", "--embed-images"], "only valid with --to markdown"),
            (["--to", "docx", "--image-dir", "/tmp/x"], "only valid with --to markdown"),
            (["--to", "markdown", "--pages", "1-2"], "only valid with --to docx"),
            (["--to", "markdown", "--password", "x"], "only valid with --to docx"),
            (["--to", "markdown", "--multi-processing"], "only valid with --to docx"),
            (["--to", "markdown", "-v"], "only valid with --to docx"),
            (["--to", "docx", "--pages", "1-2", "--start", "1"], "cannot be combined"),
            (["--to", "docx", "--pages", "1-2", "--multi-processing"], "continuous pages only"),
            (["--to", "docx", "--cpu-count", "2"], "requires --multi-processing"),
            (["--to", "docx", "--start", "0"], "must be 1 or greater"),
            (["--to", "docx", "--start", "5", "--end", "2"], "must not be less than --start"),
        ],
    )
    def test_rejected_combinations(self, runner, args, expected):
        result = runner.invoke(main, ["convert", *args, str(SAMPLE_PDF)])
        assert result.exit_code != 0
        assert expected in result.output

    def test_bad_password_is_a_clean_error(self, runner, tmp_path):
        """pdf2docx's ConversionException surfaces as a CLI error, not a traceback."""
        import pymupdf

        encrypted = tmp_path / "encrypted.pdf"
        with pymupdf.open(str(SAMPLE_PDF)) as doc:
            doc.save(
                str(encrypted),
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner",
                user_pw="secret",
            )

        result = runner.invoke(
            main,
            [
                "convert", "--to", "docx", str(encrypted),
                "-o", str(tmp_path / "out.docx"),
                "--password", "wrong", *FIRST_PAGE,
            ],
        )
        assert result.exit_code != 0
        assert "Incorrect password" in result.output
        assert not isinstance(result.exception, SystemExit) or result.exit_code == 1

    def test_correct_password_converts(self, runner, tmp_path):
        """--password unlocks an encrypted PDF."""
        import pymupdf

        encrypted = tmp_path / "encrypted.pdf"
        with pymupdf.open(str(SAMPLE_PDF)) as doc:
            doc.save(
                str(encrypted),
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner",
                user_pw="secret",
            )

        output_path = tmp_path / "out.docx"
        result = runner.invoke(
            main,
            [
                "convert", "--to", "docx", str(encrypted),
                "-o", str(output_path), "--password", "secret", *FIRST_PAGE,
            ],
        )
        assert result.exit_code == 0, result.output
        assert paragraph_texts(output_path)


class TestParsePageSpec:
    """Unit tests for the --pages spec parser.

    Specs are 1-based and inclusive; the parser returns 0-based indexes.
    """

    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("1", [0]),
            ("3", [2]),
            ("1-3", [0, 1, 2]),
            ("1-3,7", [0, 1, 2, 6]),
            ("2-2", [1]),
            # Whitespace around tokens is tolerated.
            (" 1 - 3 , 7 ", [0, 1, 2, 6]),
            # Open-ended: "8-" runs to the last page.
            ("8-", [7, 8, 9]),
            ("1-2,9-", [0, 1, 8, 9]),
            # Duplicates and overlaps are preserved in the order given.
            ("1-3,2", [0, 1, 2, 1]),
            ("3,1", [2, 0]),
            ("1,1", [0, 0]),
        ],
    )
    def test_valid_specs(self, spec, expected):
        assert _parse_page_spec(spec, page_count=10) == expected

    @pytest.mark.parametrize(
        "spec,message",
        [
            ("7-3", "reversed page range"),
            ("10-2", "reversed page range"),
            ("abc", "invalid page"),
            ("1-2-3", "invalid page"),
            ("-5", "invalid page"),  # only trailing open-ended ranges are supported
            ("1,,2", "empty page"),
            ("", "empty page"),
            # Clamping cannot rescue a spec that selects nothing at all.
            ("50-60", "selects no pages"),
            ("99", "selects no pages"),
        ],
    )
    def test_rejected_specs(self, spec, message):
        with pytest.raises(click.UsageError, match=message):
            _parse_page_spec(spec, page_count=10)

    def test_reversed_range_suggests_the_fix(self):
        with pytest.raises(click.UsageError, match="did you mean '3-7'"):
            _parse_page_spec("7-3", page_count=10)

    def test_out_of_range_is_clamped(self):
        """A range running past the end is clamped, not rejected."""
        assert _parse_page_spec("8-99", page_count=10) == [7, 8, 9]
        assert _parse_page_spec("0-3", page_count=10) == [0, 1, 2]

    def test_clamping_warns(self, runner, tmp_path):
        result = runner.invoke(
            main,
            [
                "convert", "--to", "docx", str(SAMPLE_PDF),
                "-o", str(tmp_path / "out.docx"), "--pages", "1-9999",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "clamped" in result.output


class TestPagesOption:
    """End-to-end behaviour of --pages."""

    def test_pages_selects_those_pages(self, runner, tmp_path):
        """--pages 1,2 matches --start 1 --end 2."""
        by_pages = tmp_path / "by_pages.docx"
        by_range = tmp_path / "by_range.docx"
        for output, args in (
            (by_pages, ["--pages", "1,2"]),
            (by_range, ["--start", "1", "--end", "2"]),
        ):
            result = runner.invoke(
                main,
                ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output), *args],
            )
            assert result.exit_code == 0, result.output

        assert paragraph_texts(by_pages) == paragraph_texts(by_range)

    def test_pages_is_one_based(self, runner, tmp_path):
        """--pages 1 is the first page, not the second."""
        by_pages = tmp_path / "by_pages.docx"
        by_range = tmp_path / "by_range.docx"
        for output, args in (
            (by_pages, ["--pages", "1"]),
            (by_range, ["--start", "1", "--end", "1"]),
        ):
            result = runner.invoke(
                main,
                ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output), *args],
            )
            assert result.exit_code == 0, result.output

        assert paragraph_texts(by_pages) == paragraph_texts(by_range)

    def test_out_of_order_pages_emit_in_document_order(self, runner, tmp_path):
        """pdf2docx marks pages then writes them in document order.

        The parser preserves the order typed, but that ordering is not
        observable in the DOCX -- worth pinning so nobody expects otherwise.
        """
        reversed_spec = tmp_path / "reversed.docx"
        forward_spec = tmp_path / "forward.docx"
        for output, spec in ((reversed_spec, "2,1"), (forward_spec, "1,2")):
            result = runner.invoke(
                main,
                ["convert", "--to", "docx", str(SAMPLE_PDF), "-o", str(output), "--pages", spec],
            )
            assert result.exit_code == 0, result.output

        assert paragraph_texts(reversed_spec) == paragraph_texts(forward_spec)
