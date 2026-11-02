# Spacer engine snapshot

The files in `src/spacer_pipeline/engine/` were copied from the original
`project_helpers` helper library (not included in this repository).

Included files:

- `knitout_writer.py`
- `knitting_helper.py`
- `shaping_helper.py`
- `spacer_helper.py`

At repository creation, the only changes were converting the three cross-file
imports to package-relative imports. The packaged `SpacerHelper` has since
gained exact-range stepping and spacer-aware short-row episodes for the panel
compiler. The original `project_helpers` source remains unchanged.
