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

The script reconstructs the frozen 205-work subset from the alignment reports
in the parent PawChorale workspace and updates `docs/data/`. It fails closed if
the result is not exactly 205 works.

Public ZIP archives require a reviewed dataset rights notice:

```bash
python3 scripts/build_release.py \
  --build-archives \
  --rights-file /absolute/path/to/RIGHTS_NOTICE.md
```

The four generated archives are written to the ignored `release/` directory.
They belong in a GitHub Release, not in Git history or the GitHub Pages artifact.

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
