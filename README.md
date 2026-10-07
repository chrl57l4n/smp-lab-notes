# SMP Lab Notes

Source of the site **SMP Lab Notes**: measurements, builds and failures from the
[Sovereign Memory Protocol](https://github.com/chrl57l4n/sovereign-memory-protocol).

- `notes/` — one Markdown file per note. This is the original; the site is built from it.
- `pages/` — static pages (About).
- `assets/` — the stylesheet. No external fonts, scripts or services.
- `build.py` — builds the site into `docs/` (requires `markdown-it-py`).
- `docs/` — the built site, served by GitHub Pages.

A published note is not silently changed. Corrections are appended to the note with a date.
