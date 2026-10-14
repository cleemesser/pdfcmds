# HTML output renders the markdown pipeline, not PyMuPDF's HTML

`pdf convert --to html` had to produce Reading HTML (see `GLOSSARY.md`): semantic content —
headings, paragraphs, tables, lists, figures — that reflows, rather than a page replica.
PyMuPDF can emit HTML itself (`page.get_text("html")`), and we chose instead to run the
existing markdown pipeline (`pymupdf4llm.to_markdown`) through a Markdown renderer (mistune)
and wrap the result in a standalone document.

PyMuPDF's own HTML is geometry, not meaning: every line becomes an absolutely positioned
`<p style="top:…;left:…">` inside a fixed `612pt × 792pt` div, no heading level or table
structure is reconstructed, and upstream documents that it loses paragraph grouping
(pymupdf/PyMuPDF#1228). Measured on the 21-page sample in this repo: 327 KB of positioned
markup against 69 KB of markdown. There is also no native Markdown→HTML in PyMuPDF —
`Story` has no HTML writer and `pymupdf.open()` cannot open a `.md` file — so a renderer
dependency is unavoidable either way.

Rendering the markdown means HTML inherits everything the markdown path already does well
(reading order, heading levels, OCR, ~99% of the text layer on our samples) and inherits its
weaknesses too, tables above all. That inheritance is the point: one pipeline, one place to
fix content quality, and `--to html` can be checked against `--to markdown` at any time.

## Considered options

- `page.get_text("html")` / `"xhtml"` — page replica, no semantic structure, 5× the bytes.
- Vendor or fork pymupdf4llm to emit HTML directly, as `pdf2docx` was vendored — better
  tables eventually, but it makes us the maintainer of a second AGPL copy.
- Shell out to pandoc — quality floor is fine, but it adds a non-Python dependency to a
  tool that currently installs with one `pip install`.

## Consequences

- mistune is now a runtime dependency (BSD-3, no dependencies of its own on Python ≥ 3.11).
- Table output is only as good as pymupdf4llm's. Upstream's `table_output="html"` (≥ 1.28)
  would improve it, but moving off the pinned 0.3.4 changes `--to markdown` output too, so
  that bump is its own decision, not a side effect of this one.
- Text is escaped on render, so markup written inside a PDF stays inert; pymupdf4llm's own
  `<br>` breaks are restored after rendering (see `_markdown_to_html`).
