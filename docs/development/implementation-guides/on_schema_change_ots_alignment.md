# Implementation Plan vs OTS 0.2.1 Alignment Review

## Summary

The implementation plan needs **significant updates** to align with OTS 0.2.1 specification. Key differences identified:

1. ❌ **Missing options**: `"full_refresh"`, `"full_incremental_refresh"`, `"recreate_empty"`
2. ❌ **Wrong default**: Plan says `"ignore"`, OTS says `"fail"`
3. ❌ **Missing structure**: `full_incremental_refresh` configuration not in plan
4. ⚠️ **Schema inference**: Plan suggests LIMIT 0, but we decided on DESCRIBE/DB-specific
5. ✅ **Core approach**: Schema comparison and handling logic is still valid

## Detailed Comparison

### 1. on_schema_change Options

| Implementation Plan | OTS 0.2.1 | Status |
|---------------------|-----------|--------|
| `"ignore"` (default) | ✅ `"ignore"` (optional) | ✅ **KEEP** - but not default |
| `"fail"` | ✅ `"fail"` (default) | ✅ **KEEP** - make it default |
| `"append_new_columns"` | ✅ `"append_new_columns"` | ✅ **KEEP** |
| `"sync_all_columns"` | ✅ `"sync_all_columns"` | ✅ **KEEP** |
| ❌ Missing | ✅ `"full_refresh"` | **ADD** |
| ❌ Missing | ✅ `"full_incremental_refresh"` | **ADD** |
| ❌ Missing | ✅ `"recreate_empty"` | **ADD** |

**Action Required:**
- Keep `"ignore"` option (available but not default)
- Change default from `"ignore"` to `"fail"`
- Add three new options: `"full_refresh"`, `"full_incremental_refresh"`, `"recreate_empty"`

### 2. Type Definitions

**Current Plan:**
```python
OnSchemaChange = Literal["ignore", "append_new_columns", "sync_all_columns", "fail"]
```

**OTS 0.2.1 Required:**
```python
OnSchemaChange = Literal[
    "fail",                    # Default
    "ignore",                  # Available but not default
    "append_new_columns",
    "sync_all_columns",
    "full_refresh",
    "full_incremental_refresh",
    "recreate_empty"
]
```

**Action Required:**
- Update `OnSchemaChange` type to match OTS 0.2.1
- Keep `"ignore"` option (available but not default)
- Add three new options

### 3. full_incremental_refresh Configuration

**Missing from Implementation Plan:** The OTS 0.2.1 spec includes a `full_incremental_refresh` configuration structure that is completely missing from the implementation plan.

**OTS 0.2.1 Structure:**
```python
class FullIncrementalRefreshParameter(TypedDict):
    name: str              # Parameter name (e.g., "@start_date")
    start_value: str        # Initial value
    end_value: str          # End condition (hardcoded or expression)
    step: str               # Increment step

class FullIncrementalRefreshConfig(TypedDict):
    parameters: list[FullIncrementalRefreshParameter]

# At transformation level (not nested under incremental_details)
class ModelMetadata(TypedDict):
    # ... existing fields ...
    full_incremental_refresh: NotRequired[FullIncrementalRefreshConfig | None]
```

**Action Required:**
- Add `FullIncrementalRefreshParameter` type
- Add `FullIncrementalRefreshConfig` type
- Add `full_incremental_refresh` field to `ModelMetadata` (at transformation level, not under `incremental_details`)

### 4. Schema Inference Approach

**Implementation Plan Says:**
- Primary: `SELECT * FROM (query) LIMIT 0` + cursor metadata
- Fallback: `SchemaInferencer` for static analysis

**Decision Made:**
- Use database-specific `DESCRIBE` or equivalent methods
- Create standardized adapter method: `describe_query_schema(sql_query: str)`

**Action Required:**
- Update implementation plan to use `describe_query_schema()` approach
- Remove LIMIT 0 approach
- Add requirement for adapter method implementation

### 5. Default Behavior

**Implementation Plan Says:**
- Default: `"ignore"` (for backward compatibility)

**OTS 0.2.1 Says:**
- Default: `"fail"`

**Decision Made:**
- Default should be `"fail"` (more strict, safer)

**Action Required:**
- Change default to `"fail"`
- Update documentation to reflect this

### 6. Type Mismatch Handling

**Implementation Plan Says:**
- Option D: Only fail with `on_schema_change='fail'`, warn otherwise

**Decision Made:**
- "Detect and fails, a different datatype is a different column"

**OTS 0.2.1 Says:**
- "If a column exists with the same name but different data type, it is treated as a schema change and handled according to the `on_schema_change` setting."

**Resolution Needed:**
There's a slight discrepancy:
- **Decision**: "Detect and fails" suggests immediate failure
- **OTS Spec**: "treated as a schema change and handled according to the `on_schema_change` setting"

**Recommendation:** Follow OTS spec - treat type mismatch as a schema change and handle according to `on_schema_change` setting. This is more flexible and consistent with the spec.

**Action Required:**
- Update plan: Type mismatches are detected as schema changes
- Handle according to `on_schema_change` setting:
  - `"fail"`: Fail immediately ✅
  - `"append_new_columns"`: Treat as new column (add) + missing column (keep old) = may cause issues
  - `"sync_all_columns"`: Replace column (drop old, add new) = data loss
  - Other behaviors: Follow their logic

### 7. Schema Comparison Timing

**Implementation Plan Says:**
- After SQL filtering, before execution

**Decision Confirmed:**
- ✅ After time-based filtering, before actual INSERT/MERGE

**Action Required:**
- ✅ Keep as planned

### 8. Missing Implementation: full_incremental_refresh Logic

**OTS 0.2.1 Requires:**
When `on_schema_change="full_incremental_refresh"`:
1. Drop existing table
2. Recreate table (with full query, no filtering)
3. Run incremental strategy in chunks:
   - For each parameter in `full_incremental_refresh.parameters`:
     - Start with `start_value`
     - Increment by `step` until reaching `end_value`
     - `end_value` expressions are evaluated against **source table(s)**
   - Execute incremental strategy for each chunk
   - Continue until all parameters reach their `end_value`

**Implementation Plan:**
- ❌ This logic is completely missing

**Action Required:**
- Add new section to implementation plan for `full_incremental_refresh` execution logic
- Add chunking logic
- Add source table evaluation for `end_value` expressions

### 9. Missing Implementation: full_refresh Logic

**OTS 0.2.1 Requires:**
When `on_schema_change="full_refresh"`:
1. Drop existing table
2. Recreate table with full transformation output (no incremental filtering)

**Implementation Plan:**
- ❌ This logic is missing

**Action Required:**
- Add implementation for `full_refresh` behavior

### 10. Missing Implementation: recreate_empty Logic

**OTS 0.2.1 Requires:**
When `on_schema_change="recreate_empty"`:
1. Drop existing table
2. Recreate table as empty (no data)

**Implementation Plan:**
- ❌ This logic is missing

**Action Required:**
- Add implementation for `recreate_empty` behavior

## Updated Implementation Checklist

### Phase 1: Foundation (UPDATED)
- [ ] Add `OnSchemaChange` type with all 7 options (keep `"ignore"`, add 3 new)
- [ ] Add `on_schema_change` field to `IncrementalConfig` (default: `"fail"`)
- [ ] Add `FullIncrementalRefreshParameter` type
- [ ] Add `FullIncrementalRefreshConfig` type
- [ ] Add `full_incremental_refresh` field to `ModelMetadata` (transformation level)
- [ ] Update dbt importer to convert `on_schema_change` (remove warning)

### Phase 2: Schema Infrastructure (UPDATED)
- [ ] Create `schema_comparator.py` module
  - [ ] Implement `infer_query_schema()` using `adapter.describe_query_schema()` (NOT LIMIT 0)
  - [ ] Implement `get_table_schema()` using `adapter.get_table_info()`
  - [ ] Implement `compare_schemas()` logic
  - [ ] Type mismatches cause immediate failure (regardless of `on_schema_change`)
- [ ] Create `schema_change_handler.py` module
  - [ ] Implement `handle_schema_changes()` with all 7 behaviors:
    - [ ] `"fail"` - raise error (default)
    - [ ] `"ignore"` - ignore schema differences, proceed anyway
    - [ ] `"append_new_columns"` - add new columns only
    - [ ] `"sync_all_columns"` - add new, remove missing
    - [ ] `"full_refresh"` - drop and recreate with full query
    - [ ] `"full_incremental_refresh"` - drop, recreate, then chunked incremental
    - [ ] `"recreate_empty"` - drop and recreate empty
  - [ ] Implement DDL generation for `add_column` and `drop_column`

### Phase 3: Adapter Methods (UPDATED)
- [ ] Add `describe_query_schema(sql_query: str)` abstract method to `DatabaseAdapter`
- [ ] Add `add_column()` abstract method to `DatabaseAdapter`
- [ ] Add `drop_column()` abstract method to `DatabaseAdapter`
- [ ] Implement in DuckDB adapter (first)
- [ ] Implement in Snowflake adapter
- [ ] Implement in PostgreSQL adapter
- [ ] Implement in BigQuery adapter
- [ ] Add default DDL generation fallback

### Phase 4: Integration (UPDATED)
- [ ] Update `IncrementalExecutor.execute_append_strategy()` to accept `on_schema_change`
- [ ] Update `IncrementalExecutor.execute_merge_strategy()` to accept `on_schema_change`
- [ ] Update `IncrementalExecutor.execute_delete_insert_strategy()` to accept `on_schema_change`
- [ ] Add schema change handling before strategy execution (after filtering)
- [ ] Implement `full_refresh` logic
- [ ] Implement `recreate_empty` logic
- [ ] Implement `full_incremental_refresh` chunking logic:
  - [ ] Parameter value resolution
  - [ ] Chunk iteration logic
  - [ ] Source table evaluation for `end_value` expressions
  - [ ] Incremental execution per chunk
- [ ] Update `MaterializationHandler._execute_incremental_materialization()` to:
  - [ ] Extract `on_schema_change` (default: `"fail"`)
  - [ ] Extract `full_incremental_refresh` config
  - [ ] Pass both to executor methods

### Phase 5: Testing (UPDATED)
- [ ] Unit tests for `SchemaComparator`
- [ ] Unit tests for `SchemaChangeHandler` (all 7 behaviors)
- [ ] Integration tests for each `on_schema_change` behavior
- [ ] Tests for `full_incremental_refresh` chunking logic
- [ ] Tests for source table evaluation of `end_value` expressions
- [ ] Database-specific tests for DDL generation
- [ ] Test with dbt importer conversion
- [ ] Test type mismatch failure behavior

## Key Gaps Identified

1. **Missing Options**: Three new options not in original plan (`"full_refresh"`, `"full_incremental_refresh"`, `"recreate_empty"`)
2. **Missing Structure**: `full_incremental_refresh` config structure
3. **Missing Logic**: Implementation for 3 new behaviors
4. **Default Change**: Should be `"fail"` not `"ignore"` (but `"ignore"` is still available)
5. **Schema Inference**: Should use `describe_query_schema()` not LIMIT 0
6. **Type Mismatches**: Treated as schema changes, handled per `on_schema_change` setting

## Recommendations

1. **Update Implementation Guide**: Revise `on_schema_change_implementation.md` to match OTS 0.2.1
2. **Add New Sections**: Document `full_incremental_refresh` implementation
3. **Update Type Definitions First**: Get types right before implementation
4. **Implement in Order**:
   - Simple behaviors first (`fail`, `append_new_columns`, `sync_all_columns`, `full_refresh`, `recreate_empty`)
   - Complex behavior last (`full_incremental_refresh`)
5. **Test Thoroughly**: Especially `full_incremental_refresh` chunking logic

## Next Steps

1. Update implementation guide document
2. Update type definitions
3. Create detailed design for `full_incremental_refresh` chunking logic
4. Proceed with implementation following updated plan
