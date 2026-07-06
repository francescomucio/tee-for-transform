# Documentation Site

t4t can generate an interactive static HTML documentation site that visualizes your project's dependency graph, similar to dbt docs. This documentation site provides a comprehensive view of your models, functions, tests, and their relationships.

## Generating Documentation

Use the `docs` command to generate the documentation site:

```bash
t4t docs <project_folder> [options]
```

**Example:**
```bash
# Generate docs for your project
t4t docs ./my_project

# With custom output directory
t4t docs ./my_project --output-dir ./documentation

# With variables
t4t docs ./my_project --vars '{"env": "prod"}'

# Skip regenerating lookup models before building the site
t4t docs ./my_project --skip-lookups

# Infer dimensional links from fact column names (see CLI reference)
t4t docs ./my_project --infer-dim-from-column-names
```

The documentation will be generated in `output/docs/` by default (or your custom output directory). For all flags, see the `docs` command in [CLI Reference](cli-reference.md).

### Dimensional relationships in docs

The generator builds a **dimensional relationship graph** from model metadata. Fact columns with **`dimension`** (and optional **`fk_to`**) drive semantic links in the data-model payload. Logical dimension names are resolved using the same **auto-built registry** as the parser: dimension tables are discovered from `table_type` / `dim_*` naming and hierarchy level names, as described in the [Model API reference](../api-reference/models.md#dimension-shorthand-and-automatic-registry).

## Features

### Interactive Dependency Graph

The main page features an interactive dependency graph that visualizes relationships between:
- **Tables** - Materialized models (blue)
- **Views** - View materialized models (lighter blue)
- **Functions** - User-defined functions (gray)
- **Tests** - Data quality tests (orange)

**Graph Interactions:**
- **Click** a node to select it and highlight its dependencies and dependents
- **Double-click** a node to navigate to its detail page
- **Filter** using the text input (supports dbt-style patterns)
- **Toggle** object types using the legend buttons

### Sidebar Navigation

The left sidebar provides:
- **Project Statistics**: Model and node counts
- **Collapsible Tree**: Hierarchical navigation organized by:
  - Schema folders
  - Model groups (tables/views)
  - Function groups (UDFs)
  - Individual models, functions, and tests

**Sidebar Features:**
- **Auto-sizing**: Automatically adjusts width based on longest model name
- **Collapsible**: Click the toggle button to collapse/expand
- **Clickable**: Click any item to filter the graph to that object
- **Double-click**: Navigate to detail pages

### Filtering

The filter input supports dbt-style filtering patterns:

```bash
# Filter by exact name
+my_schema.my_table+

# Filter by schema
my_schema.*

# Filter by pattern
*users*
*_summary

# Filter by type
tag:production
```

**Filter Actions:**
- Typing in the filter box immediately updates the graph
- Clicking a node in the sidebar updates the filter
- The filter shows only matching nodes and their connections

### Legend Toggle

The legend allows you to show/hide different object types:
- **Tables** - Toggle table visibility
- **Views** - Toggle view visibility
- **Functions** - Toggle function visibility
- **Tests** - Toggle test visibility

**Toggle Behavior:**
- Click a legend item to toggle that type
- Disabled types show with strikethrough
- The graph redraws automatically when types are toggled
- Edges (arrows) connected to hidden nodes are also hidden

### Model Detail Pages

Each model has a dedicated detail page accessible by:
- Double-clicking a node in the graph
- Double-clicking an item in the sidebar
- Direct navigation to `model_{safe_name}.html`

**Detail Page Contents:**
- **Model Metadata**: Name, description, materialization type
- **Schema**: Column definitions with types, descriptions, and tests
- **Original SQL**: The SQL as written in your source file
- **Compiled SQL**: The SQL after variable substitution and resolution
- **Dependencies**: Clickable list of models/functions this model depends on
- **Dependents**: Clickable list of models that depend on this model
- **Tests**: Associated data quality tests
- **Incremental Configuration**: If applicable, incremental materialization settings

## Visual Design

The documentation site uses a modern, light theme with:
- **Color Scheme**: High-contrast, accessible colors
- **Typography**: Inter font family for readability
- **Layout**: Responsive design that works on different screen sizes
- **Icons**: Distinct icons for different object types:
  - 📅 Tables
  - 🏞️ Views
  - 🧩 Functions
  - 🧪 Tests
  - 🗃️ Schemas

## File Structure

The generated documentation site has the following structure:

```
output/docs/
├── index.html              # Main interactive page
├── model_*.html            # Individual model detail pages
├── graph_data.json         # Graph data for JavaScript
└── assets/                 # CSS and JavaScript (embedded in HTML)
```

## Serving the Documentation

The documentation site is completely static and can be:

1. **Opened directly** in a web browser:
   ```bash
   open output/docs/index.html  # macOS
   xdg-open output/docs/index.html  # Linux
   start output/docs/index.html  # Windows
   ```

2. **Served via web server**:
   ```bash
   # Python
   python -m http.server 8000 --directory output/docs

   # Node.js
   npx serve output/docs

   # Any static file server
   ```

3. **Deployed to hosting**:
   - GitHub Pages
   - Netlify
   - Vercel
   - Any static hosting service

## Use Cases

The documentation site is useful for:

- **Project Overview**: Get a visual understanding of your data pipeline
- **Dependency Analysis**: Understand how models relate to each other
- **Onboarding**: Help new team members understand the project structure
- **Documentation**: Share project documentation with stakeholders
- **Debugging**: Visualize dependencies when troubleshooting issues
- **Planning**: Understand impact of changes before making them

## Tips

1. **Regular Updates**: Regenerate docs after significant changes to keep them current
2. **CI/CD Integration**: Generate docs as part of your CI/CD pipeline
3. **Version Control**: Consider committing generated docs or hosting them separately
4. **Custom Output**: Use `--output-dir` to generate docs in a location suitable for deployment

## Related Documentation

- [CLI Reference](cli-reference.md) - Complete command reference
- [Models API](../api-reference/models.md) - Model creation and metadata
- [Tags and Metadata](tags-and-metadata.md) - Adding descriptions and metadata to models
