## Summary of Changes

### 📦 Package Rename
- **Renamed package directory**: `tee/` → `t4t/`
- **Updated all imports**: 754 references changed from `tee.` to `t4t.`

### 📄 Configuration Updates
- **pyproject.toml**:
  - Project name: "tee" → "t4t"
  - Entry point: `t4t = "tee.cli.main:main"` → `t4t = "t4t.cli.main:main"`
  - Include patterns: `include = ["tee*"]` → `include = ["t4t*"]`
  - Source paths: `source = ["tee"]` → `source = ["t4t"]`
  - Coverage settings: `--cov=tee` → `--cov=t4t`

### 🌐 Environment Variables
- **Prefix rename**: `TEE_DB_*` → `T4T_DB_*` 
- **Backward compatibility**: **REMOVED** — only `T4T_DB_*` is supported (pre-release cleanup)
- **Config sections**: `[tool.tee.*]` → `[tool.t4t.*]` — no fallback, only `[tool.t4t.*]`

### 📚 Documentation
- Updated README.md and all documentation files
- MkDocs configuration updated
- Examples and tutorials revised

### ✅ Testing
- Full test suite passes (excluding Snowflake due to expired account)
- CLI commands tested and working:
  - `t4t init` - Project initialization
  - `t4t run` - Model execution  
  - `t4t build` - Build with tests
  - `t4t test` - Test execution
  - `t4t compile` - OTS module compilation
  - `t4t docs` - Documentation generation
  - `t4t debug` - Database connectivity testing
  - `t4t seed` - Seed data loading
  - `t4t import` - Project import functionality
  - `t4t generate-lookups` - Lookup table generation
  - `t4t ots` - OTS module commands

### 📝 Commit Details
- **Commit**: c58b1c2 - "Rename Python package from 'tee' to 't4t'"
- **Files changed**: 425 files
- **Lines added**: 1,350
- **Lines deleted**: 1,259