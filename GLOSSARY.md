# pdfcmds

A command-line tool that converts a PDF into another document format. `pdf convert --to <format>`
picks the target format. These are the words this project uses for that job.

## Language

**Semantic content**:
The text and structure of a document — its headings, paragraphs, tables and lists — as opposed
to where that content sits on the printed page.
_Avoid_: layout, position

**Reading HTML**:
HTML that carries a document's semantic content and reflows to fit any window. The target of
`pdf convert --to html`.
_Avoid_: page replica, HTML view

**Page replica**:
HTML that reproduces the geometry of the printed page on screen: fixed page size, text pinned
to coordinates. Deliberately not what `--to html` produces.
_Avoid_: faithful HTML

**Self-contained output**:
A converted document that needs no companion files, because its images travel inside it.
_Avoid_: single file, bundled output

**Image**:
A picture carried out of a PDF page. Vector drawings on a page are not images.
_Avoid_: figure, graphic

**Standalone document**:
An HTML file a browser can open on its own, because it declares its own character encoding
and title.
_Avoid_: fragment, full page
