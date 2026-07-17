# Workbench UI

- Owns: read-only two-pane SQL-backed spreadsheet payloads for the SYSTEM `workbench_ui` tool surface.
- Does not own: datum mutation, portal-shell legality, or directive-context authority rules.
- Notes: the document table is keyed by `version_hash`, the row grid is keyed by `hyphae_hash`, keyboard navigation resolves to canonical `document` / `row` selections, grouping/lens/source visibility stay query-driven, and overlays are additive summaries only that never rewrite authoritative datum rows.
