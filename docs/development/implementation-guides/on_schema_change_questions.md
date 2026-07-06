# Questions Before Implementing on_schema_change

## 1. OTS Specification Status

**Question**: The documentation mentions "Implementation should wait for OTS specification update" (line 147 of `06-on-schema-change.md`). Should I proceed with implementation now, or wait for the OTS spec to be updated first?

**Context**: The OTS issue is referenced, but the implementation plan is ready.

**Recommendation**: Proceed with implementation - we can align with OTS spec later if needed.

---

## 2. Schema Inference Approach

**Question**: What's the preferred approach for inferring query schema?

**Options**:
- **A**: `SELECT * FROM (query) LIMIT 0` + cursor metadata (most reliable, database-agnostic)
- **B**: Database-specific `DESCRIBE` or `EXPLAIN` commands (some adapters already use this)
- **C**: Reuse/adapt existing `SchemaInferencer` (static analysis, may miss complex queries)
- **D**: Hybrid approach (try A, fallback to B or C)

**Current usage**: DuckDB adapter uses `DESCRIBE` for table schema.

**Recommendation**: Option A (LIMIT 0) as primary, with database-specific fallbacks if needed.

---

## 3. Type Mismatch Handling

**Question**: How should we handle type mismatches (same column name, different type)?

**Options**:
- **A**: Detect and fail (even with `append_new_columns` or `sync_all_columns`)
- **B**: Detect and warn, but continue (may cause runtime errors)
- **C**: Attempt type conversion (complex, database-specific)
- **D**: Only fail with `on_schema_change='fail'`, warn otherwise

**Documentation says**: "Type changes may require manual intervention" and "Support for column type changes (may require separate configuration)" - future enhancement.

**Recommendation**: Option D - detect and log warning for all behaviors except `fail`, which should raise error. Type conversion is future work.

---

## 4. Column Order Handling

**Question**: How should we handle column order differences?

**Context**:
- INSERT statements may insert data into wrong columns if order differs
- Some adapters (Snowflake) already handle this by explicitly listing columns in INSERT
- Documentation mentions "Support for column reordering" as future enhancement

**Options**:
- **A**: Detect and warn, but rely on explicit column lists in INSERT (current Snowflake behavior)
- **B**: Reorder columns in INSERT statements to match table order
- **C**: Only warn, don't attempt to fix

**Current behavior**: Snowflake adapter's `execute_append` already uses explicit column lists.

**Recommendation**: Option A - detect and warn, but rely on adapters to use explicit column lists (which they should already do for safety).

---

## 5. Database-Specific Limitations

**Question**: How should we handle database-specific limitations (e.g., BigQuery DROP COLUMN restrictions)?

**Options**:
- **A**: Fail with clear error message explaining the limitation
- **B**: Warn and skip the operation (partial sync)
- **C**: Check adapter capabilities and disable unsupported features

**Current pattern**: Adapters have fallback methods (e.g., `execute_incremental_append` falls back to `create_table`).

**Recommendation**: Option A - fail with clear error. Users should know when operations can't be performed. We can add capability checks later.

---

## 6. Default Behavior

**Question**: Should `on_schema_change` default to `"ignore"` or be required?

**Context**:
- Documentation says "ignore (default)"
- Backward compatibility is important
- If not specified, should we default or require explicit setting?

**Recommendation**: Default to `"ignore"` for backward compatibility. This matches dbt's behavior.

---

## 7. Error Handling Strategy

**Question**: What should happen if schema comparison fails (e.g., query execution error, table info unavailable)?

**Options**:
- **A**: Fail the entire transformation
- **B**: Log warning and proceed with `ignore` behavior
- **C**: Only fail if `on_schema_change='fail'`, otherwise warn and continue

**Recommendation**: Option C - if schema comparison fails and `on_schema_change` is not `'fail'`, log warning and proceed. If it's `'fail'`, raise error.

---

## 8. Performance & Caching

**Question**: Should we cache schema comparison results within a single execution?

**Context**:
- Schema comparison requires query execution (LIMIT 0) and table info query
- Same query/table might be checked multiple times
- Overhead is probably minimal but could add up

**Recommendation**: Simple in-memory cache for the duration of a single model execution. Don't persist across runs.

---

## 9. Testing Strategy

**Question**: Should I implement tests as I go, or focus on implementation first?

**Options**:
- **A**: TDD - write tests first, then implementation
- **B**: Implementation first, then comprehensive tests
- **C**: Mixed - unit tests as I go, integration tests at the end

**Recommendation**: Option C - write unit tests for schema comparison and handler logic as I implement, then add integration tests at the end.

---

## 10. Adapter Method Implementation Order

**Question**: Should I implement `add_column()` and `drop_column()` in all adapters at once, or start with one adapter as a reference?

**Options**:
- **A**: Implement in all adapters simultaneously
- **B**: Start with DuckDB (simplest), then Snowflake, then others
- **C**: Start with Snowflake (most common), then others

**Recommendation**: Option B - start with DuckDB as it's simplest and good for testing, then Snowflake (most used), then PostgreSQL and BigQuery.

---

## 11. Column Type Information

**Question**: When adding columns, how should we determine the SQL type from the inferred schema?

**Context**:
- `get_table_info()` returns types like `"VARCHAR"`, `"INTEGER"`, etc.
- Query schema inference might return different type formats
- Need to normalize for DDL generation

**Options**:
- **A**: Use the type as-is from query inference
- **B**: Map to database-specific types using adapter's dialect
- **C**: Use a generic type mapping

**Recommendation**: Option A initially - use the type from query inference. If it fails, we can add type mapping later. Most databases are flexible with type casting.

---

## 12. Integration Point Confirmation

**Question**: Confirm the exact integration point in the execution flow.

**Current flow**:
1. Get state
2. Generate time filter
3. Apply filter to SQL
4. Execute strategy (calls adapter method)

**Proposed flow**:
1. Get state
2. Generate time filter
3. Apply filter to SQL
4. **NEW: Check schema changes (if table exists and on_schema_change is set)**
5. Execute strategy

**Confirmation needed**: Is this the right place, or should schema checking happen earlier/later?

**Recommendation**: This placement is correct - after SQL is filtered but before execution, so we're comparing the actual query that will run.

---

## Summary of Recommendations

Based on the codebase patterns and documentation:

1. ✅ Proceed with implementation (don't wait for OTS spec)
2. ✅ Use LIMIT 0 query for schema inference (primary approach)
3. ✅ Type mismatches: warn for all behaviors except `fail` (which raises error)
4. ✅ Column order: warn, rely on explicit column lists in adapters
5. ✅ Database limitations: fail with clear error message
6. ✅ Default to `"ignore"` for backward compatibility
7. ✅ Schema comparison failures: warn and continue (unless `on_schema_change='fail'`)
8. ✅ Simple in-memory cache for single execution
9. ✅ Mixed testing approach (unit tests as I go, integration at end)
10. ✅ Start with DuckDB adapter, then Snowflake, then others
11. ✅ Use inferred types as-is initially
12. ✅ Integration point confirmed (after SQL filtering, before execution)
