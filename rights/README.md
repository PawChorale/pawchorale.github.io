# PawChorale source-rights audit

This directory records the edition-level rights markers for the 205 works in
the initial curated PawChorale release. It is release-review evidence, not legal
advice.

The audit joins every public PawChorale ID to the exact URL captured in the
original CPDL browser download log, resolves that media file through CPDL's
official MediaWiki API, and reads the `{{Copy|...}}` marker from the matching
edition entry on the work page.

## Audit result (2026-08-03)

| Upstream marker | Works | Release implication |
| --- | ---: | --- |
| CPDL | 172 | Preserve attribution, notices, CPDL terms, and downstream freedoms. |
| Public Domain | 26 | Preserve provenance; verify jurisdiction-specific status where necessary. |
| Creative Commons Attribution Non-Commercial | 3 | Preserve attribution and the non-commercial restriction. |
| Personal | 4 | Obtain and record editor permission or exclude from public download. |

All 205 media URLs and edition markers were resolved. The four `Personal`
editions requiring permission review are:

- ID 169 — *Angelus ad pastores ait a 4* — editor Aristotle Aure Esguerra
- ID 183 — *Beati eritis* — editor Aristotle Aure Esguerra
- ID 190 — *Cantate Domino* — editor Aristotle Aure Esguerra
- ID 270 — *O Saviour of the world* — editor Douglas Walczak

The three Creative Commons Attribution Non-Commercial editions are IDs 5, 140,
and 145.

## Why there is no blanket research-only license

CPDL's own license is designed to preserve the ability to copy, distribute,
perform, record, and modify covered editions. A research-only restriction would
remove freedoms granted by upstream CPDL terms. PawChorale therefore preserves
the applicable edition-level terms instead of replacing them with one more
restrictive dataset license.

## Files

- `source_rights_manifest.csv`: one evidence row per retained work, including
  the exact CPDL media URL, work page, editor, CPDL number, and rights marker.
- `source_rights_summary.json`: machine-readable counts and audit method.

Rebuild the audit from the parent dataset workspace with:

```bash
python3 scripts/audit_cpdl_rights.py
```

Official CPDL references:

- https://www.cpdl.org/wiki/index.php/ChoralWiki:Copyrights
- https://www.cpdl.org/wiki/index.php/CPDL_license
