# Three Streamlined Options for Model Building

All three options allow you to have **just the import and metadata** - no function calls needed (or minimal).

## Option 1: Auto-executing Class (RECOMMENDED) ⭐

**Cleanest and most Pythonic**

```python
from model_builder_options import ModelBuilder
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "number",
            "description": "Unique identifier for the record",
            "tests": ["not_null", "unique"]
        }
    ]
}

ModelBuilder()  # That's it! Auto-executes when script is run as main
```

**Pros:**
- Very clean - just instantiate the class
- Automatically finds `metadata` variable
- Clear intent - you're building a model
- Works well with type checkers

**Cons:**
- Requires one line after metadata definition

---

## Option 2: Simple Function Call

**Simplest function name**

```python
from model_builder_options import build
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "number",
            "description": "Unique identifier for the record",
            "tests": ["not_null", "unique"]
        }
    ]
}

build()  # Finds metadata automatically
```

**Pros:**
- Shortest function name (`build()`)
- Automatically finds `metadata` variable
- Very simple to use

**Cons:**
- Requires one line after metadata definition
- Less explicit about what it's building

---

## Option 3: Setup at Top (Most Automatic)

**Truly automatic - executes at module end**

```python
from model_builder_options import setup_auto_build
from t4t.typing import ModelMetadata

setup_auto_build()  # Set up auto-execution at top

metadata: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "number",
            "description": "Unique identifier for the record",
            "tests": ["not_null", "unique"]
        }
    ]
}

# Automatically executes when module finishes loading - no call needed!
```

**Pros:**
- Most automatic - no call after metadata
- Setup happens at top, execution at end
- Clean separation

**Cons:**
- Requires setup call at top
- Less obvious when execution happens
- Uses `atexit` which may have timing issues

---

## Comparison

| Option | Lines After Metadata | Auto-finds metadata | Clarity | Recommended |
|--------|---------------------|-------------------|---------|-------------|
| Option 1: `ModelBuilder()` | 1 | ✅ | ⭐⭐⭐⭐⭐ | ✅ Yes |
| Option 2: `build()` | 1 | ✅ | ⭐⭐⭐⭐ | ✅ Yes |
| Option 3: `setup_auto_build()` | 0 | ✅ | ⭐⭐⭐ | ⚠️ Maybe |

## Recommendation

**Use Option 1 (`ModelBuilder()`)** - it's the cleanest, most Pythonic, and clearest about intent while still being very streamlined.

