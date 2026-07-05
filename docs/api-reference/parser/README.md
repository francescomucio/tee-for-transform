# Parser API

SQL and Python model parsing, dependency analysis, metadata, OTS output, and lookup generation.

## Status

Narrative API reference pages are not written yet. The parser is large; start from the user guide and these entry points.

## Where to look in code

| Area | Python package / module |
|------|-------------------------|
| Project discovery & model orchestration | `t4t/parser/core/` (e.g. project parser, orchestration) |
| SQL / Python model builders | `t4t/parser/processing/`, `t4t/parser/shared/` |
| Function parsers (SQL/Python) | `t4t/parser/parsers/` |
| Analysis (dependencies, dimensions) | `t4t/parser/analysis/` (e.g. dimensional graph) |
| OTS compile pipeline | `t4t/parser/output/ots/` |
| Lookup SQL generation | `t4t/parser/output/lookup_generator.py` |
| Tests discovery (parser side) | overlaps with `t4t/testing/` |

## User-facing docs

- [Overview](../../user-guide/overview.md)
- [Functions](../../user-guide/functions.md)
- [SQL dialect conversion](../../user-guide/sql-dialect-conversion.md)
- [CLI reference](../../user-guide/cli-reference.md) (`compile`, `generate-lookups`, `docs`)
