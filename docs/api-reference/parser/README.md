# Parser API

SQL and Python model parsing, dependency analysis, metadata, OTS output, and lookup generation.

## Status

Narrative API reference pages are not written yet. The parser is large; start from the user guide and these entry points.

## Where to look in code

| Area | Python package / module |
|------|-------------------------|
| Project discovery & model orchestration | `tee/parser/core/` (e.g. project parser, orchestration) |
| SQL / Python model builders | `tee/parser/processing/`, `tee/parser/shared/` |
| Function parsers (SQL/Python) | `tee/parser/parsers/` |
| Analysis (dependencies, dimensions) | `tee/parser/analysis/` (e.g. dimensional graph) |
| OTS compile pipeline | `tee/parser/output/ots/` |
| Lookup SQL generation | `tee/parser/output/lookup_generator.py` |
| Tests discovery (parser side) | overlaps with `tee/testing/` |

## User-facing docs

- [Overview](../../user-guide/overview.md)
- [Functions](../../user-guide/functions.md)
- [SQL dialect conversion](../../user-guide/sql-dialect-conversion.md)
- [CLI reference](../../user-guide/cli-reference.md) (`compile`, `generate-lookups`, `docs`)
