# PawChorale website

The source for [pawchorale.github.io](https://pawchorale.github.io/), the public
website and release catalog for the PawChorale choral audio–MIDI dataset.

## Local preview

The deployed website is fully static and has no build-time dependencies:

```bash
python3 -m http.server 8000 --directory docs
```

Then open <http://localhost:8000>.

## Rebuild release metadata

From this repository:

```bash
python3 scripts/build_release.py
```

The script reconstructs the frozen 200-work subset from the alignment reports,
`config/release_exclusions.csv`, and `organized_mp3_200` in the parent
PawChorale workspace. It updates `docs/data/` and fails closed if the result is
not exactly 200 works.

Public ZIP archives require a reviewed dataset rights notice:

```bash
python3 scripts/build_release.py \
  --build-archives \
  --rights-file /absolute/path/to/RIGHTS_NOTICE.md \
  --personal-permissions-file /absolute/path/to/PERSONAL_EDITION_PERMISSIONS.md
```

The four generated archives are written to the ignored `release/` directory.
They belong in a GitHub Release, not in Git history or the GitHub Pages artifact.
The permission file is required because CPDL marks four retained source editions
as `Personal`; the packager fails closed until those permissions are documented.

## Rebuild the source-rights audit

```bash
python3 scripts/audit_cpdl_rights.py
```

The audit resolves the exact CPDL edition marker for every retained work and
writes the evidence to `rights/`. Do not replace those upstream terms with one
blanket research-only license.

## Rebuild the interactive demo

The website demo uses retained work 93 because it is compact and has strong
work-level alignment. Rebuild its piano-roll data and copy its media with:

```bash
conda run --no-capture-output -n hanyu_env python scripts/build_demo.py
```

The generated demo includes synchronized master/SATB audio, four MIDI files,
source manifests, and a compact JSON note representation for the piano roll.

## Deployment

A push to `main` deploys the contents of `docs/` through GitHub Pages. The
dataset archives are separate GitHub Release assets so the Pages deployment
stays small and fast.
