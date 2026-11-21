# Screen layout overrides

These files describe generated CineBook demo seats. They do not imply affiliation or admission
to a real cinema, even when entered from a real hall's plan.

Put an override at `<cinema source_key>/<screen name>.json`, for example
`pune-pvr-phoenix-marketcity/Audi 1.json`. It takes precedence over the assigned template.
Run `scripts/import-cinemas.ps1 -Relayout` to rebuild eligible screens. Booked screens and screens
with live holds are skipped. Legacy cinemas retain their original seats.

The JSON object contains `name`, optional `description`, `rows`, and optional `section_names`.
Rows are front to back, each written as `"A RR.RR"`. Labels must match `[A-Z]+` and be unique.
All patterns must have the same width; pad narrower rows with `.`. Limits: 1–30 rows, 1–40 columns,
and at least one occupied cell. An all-gap row makes a cross-aisle.

- `R`: Regular; `P`: Prime; `L`: Recliner; `W`: accessible Regular; `.`: empty cell or aisle.
- Column positions include gaps; seat numbers skip gaps and restart at 1 on each row.
- `section_names` maps `R`, `P`, `L` to display labels. Accessible seats belong to Regular.

Full example:

```json
{
  "name": "Example demo hall",
  "description": "Aligned centre aisle and rear recliners",
  "rows": ["A RW.WR", "B PP.PP", "C LL.LL"],
  "section_names": {"R": "Regular", "P": "Prime", "L": "Recliner"}
}
```
