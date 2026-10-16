# Phase 4 Package Audit (D-21, D-24, D-28)

Gathered 2026-10-17 from `https://pypi.org/pypi/<name>/json` and `https://api.osv.dev/v1/query` (read-only fetches, nothing installed). Transitive set resolved with `uv pip compile` (Python 3.13) from the seven pins; nothing was written to `pyproject.toml` or `uv.lock`.
slopcheck did not run, so every legitimacy disposition is `[ASSUMED]` until a human confirms (T-04-SC).

## Direct packages (approved in D-24)

| Package | Pinned version | Latest on PyPI | Licence (PyPI) | First release | Pinned version uploaded | Source repository (evidence for legitimacy) | Files | Yanked | OSV advisories at pin | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|
| pypdfium2 | 5.14.0 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licences | 2021-12-03 | 2026-10-04 | github.com/pypdfium2-team/pypdfium2 (owner: pypdfium2-team) | 23 | no | none | [ASSUMED] |
| Pillow | 12.3.0 | 12.3.0 | MIT-CMU (HPND family) | 2010-07-31 | 2026-07-01 | github.com/python-pillow/Pillow (owner: python-pillow) | 87 | no | none | [ASSUMED] |
| python-docx | 1.2.0 | 1.2.0 | MIT | 2014-01-05 | 2025-06-16 | github.com/python-openxml/python-docx (owner: python-openxml) | 2 | no | none | [ASSUMED] |
| python-pptx | 1.0.2 | 1.0.2 | MIT | 2013-01-26 | 2024-08-07 | github.com/scanny/python-pptx (owner: scanny) | 2 | no | none | [ASSUMED] |
| openpyxl | 3.1.5 | 3.1.5 | MIT | 2010-08-11 | 2024-06-28 | foss.heptapod.net/openpyxl/openpyxl (Heptapod, not GitHub) | 2 | no | none | [ASSUMED] |
| lxml | 6.1.3 | 6.1.3 | BSD-3-Clause | 2007-07-03 | 2026-09-02 | github.com/lxml/lxml (owner: lxml; also launchpad) | 176 | no | none | [ASSUMED] |
| beautifulsoup4 | 4.15.0 | 4.15.0 | MIT | 2013-10-02 | 2026-06-07 | crummy.com/software/BeautifulSoup (PyPI lists no repository URL; homepage only) | 2 | no | none | [ASSUMED] |

All seven pinned versions equal the latest release; none is yanked and none carries an OSV advisory, so no pin was changed from the research.

## Transitive set (from `uv pip compile`)

| Package | Version | Pulled in by | Licence | First release | Version uploaded | Source repository | OSV advisories | Disposition |
|---|---|---|---|---|---|---|---|---|
| XlsxWriter | 3.2.9 | python-pptx | BSD-2-Clause | 2013-02-17 | 2025-09-16 | github.com/jmcnamara/XlsxWriter | none | [ASSUMED] |
| et-xmlfile | 2.0.0 | openpyxl | MIT | 2015-03-30 | 2024-10-25 | foss.heptapod.net/openpyxl/et_xmlfile | none | [ASSUMED] |
| soupsieve | 3.0.3 | beautifulsoup4 | MIT | 2018-12-08 | 2026-10-12 | github.com/facelessuser/soupsieve | none | [ASSUMED] |
| typing-extensions | 4.16.0 | python-docx, python-pptx, beautifulsoup4 | PSF-2.0 | 2017-09-17 | 2026-07-02 | github.com/python/typing_extensions | none | already locked, unchanged |

Notes:
- `pypdfium2_raw` is not a dependency of pypdfium2 5.x (the resolver does not list it), so it has no row.
- `Pillow` and `lxml` are also pulled in by python-pptx / python-docx; they are pinned directly.
- `charset-normalizer` is already locked at 3.5.2 (via requests); it becomes a direct dependency at that version. `chardet` is not added (D-28).

## Points for the human to weigh

1. soupsieve 3.0.3 was uploaded 2026-10-12 (5 days before this audit). The 3.0 major appeared 2026-10-10 and three releases followed within three days. It is a very young transitive release of a long-lived project (first release 2018). Option: add a direct constraint `soupsieve<3` (latest 2.x) at install time, or accept 3.0.3.
2. pypdfium2 5.14.0 was uploaded 2026-10-04 (13 days old); it followed 5.14.0b1 (2026-10-02) and 5.13.0 (2026-08-13); 5.13.0 is the older stable fallback. The project dates from 2021 and the repository owner matches.
3. Pillow's licence field reads `MIT-CMU` (the HPND-compatible permissive licence the research assumed).
4. openpyxl and et-xmlfile are hosted on Heptapod (foss.heptapod.net), not GitHub; this is the project's long-standing home.

## Install command (runs only after the human answers "approved")

```
uv add "pypdfium2==5.14.0" "Pillow==12.3.0" "python-docx==1.2.0" "python-pptx==1.0.2" "openpyxl==3.1.5" "lxml==6.1.3" "beautifulsoup4==4.15.0" "charset-normalizer==3.5.2"
uv lock --check
```

`charset-normalizer` becomes a direct dependency and `chardet` is not added (D-28). `pdfplumber`, `readability-lxml`, `html-text`, `infinity-sdk`, `hanziconv`, `defusedxml` and every npm package stay out (D-21, D-24).
