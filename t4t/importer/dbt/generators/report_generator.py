"""
Import report generator for dbt importer.

Generates comprehensive import reports in Markdown and JSON formats.
"""

import json
import logging
from pathlib import Path
from typing import Any

from t4t.importer.dbt.constants import CONVERSION_LOG_FILE, IMPORT_REPORT_FILE

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates import reports for dbt project imports."""

    def __init__(self, target_path: Path, verbose: bool = False) -> None:
        """
        Initialize report generator.

        Args:
            target_path: Path where t4t project was created
            verbose: Enable verbose logging
        """
        self.target_path = Path(target_path).resolve()
        self.verbose = verbose

    def generate_reports(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None = None,
        variables_info: dict[str, Any] | None = None,
        seed_results: dict[str, Any] | None = None,
        test_results: dict[str, Any] | None = None,
        packages_info: dict[str, Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        ots_compilation_result: dict[str, Any] | None = None,
    ) -> None:
        """
        Generate import reports (Markdown and JSON).

        Args:
            conversion_results: Model conversion results
            macro_results: Macro conversion results (optional)
            variables_info: Variables extraction results (optional)
            seed_results: Seed conversion results (optional)
            test_results: Test conversion results (optional)
            packages_info: Packages information (optional)
            validation_result: Validation results (optional)
            ots_compilation_result: OTS compilation results (optional)
        """
        # Generate Markdown report
        self._generate_markdown_report(
            conversion_results,
            macro_results,
            variables_info,
            seed_results,
            test_results,
            packages_info,
            validation_result,
            ots_compilation_result,
        )

        # Generate JSON log
        self._generate_json_log(
            conversion_results,
            macro_results,
            variables_info,
            seed_results,
            test_results,
            packages_info,
            validation_result,
            ots_compilation_result,
        )

        if self.verbose:
            logger.info("Generated import reports")

    def _generate_markdown_report(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        variables_info: dict[str, Any] | None,
        seed_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None = None,
        packages_info: dict[str, Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        ots_compilation_result: dict[str, Any] | None = None,
    ) -> None:
        """Generate Markdown import report."""
        lines = []
        lines.extend(self._generate_header())
        lines.extend(
            self._generate_summary_section(
                conversion_results,
                macro_results,
                seed_results,
                test_results,
                validation_result,
                ots_compilation_result,
            )
        )
        lines.extend(self._generate_validation_section(validation_result))
        lines.extend(self._generate_ots_compilation_section(ots_compilation_result))
        lines.extend(self._generate_models_section(conversion_results))
        lines.extend(self._generate_variables_section(variables_info))
        lines.extend(self._generate_tests_section(test_results))
        lines.extend(self._generate_macros_section(macro_results))
        lines.extend(self._generate_packages_section(packages_info))
        lines.extend(
            self._generate_warnings_section(conversion_results, macro_results, test_results)
        )
        lines.extend(
            self._generate_unsupported_features_section(
                conversion_results, macro_results, test_results
            )
        )

        # Write report
        report_file = self.target_path / IMPORT_REPORT_FILE
        report_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Generated import report: {report_file}")

    def _generate_header(self) -> list[str]:
        """Generate report header."""
        return [
            "# dbt Import Report",
            "",
            "This report summarizes the import of a dbt project into t4t format.",
            "",
        ]

    def _generate_summary_section(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        seed_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None,
        validation_result: dict[str, Any] | None = None,
        ots_compilation_result: dict[str, Any] | None = None,
    ) -> list[str]:
        """Generate summary statistics section."""
        lines = [
            "## Summary Statistics",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total Models | {conversion_results.get('total', 0)} |",
            f"| Converted Models | {conversion_results.get('converted', 0)} |",
            f"| Python Models | {conversion_results.get('python_models', 0)} |",
            f"| Errors | {conversion_results.get('errors', 0)} |",
        ]

        if macro_results:
            lines.append(f"| Macros Converted | {macro_results.get('converted', 0)} |")
            lines.append(f"| Macros Unconvertible | {macro_results.get('unconvertible', 0)} |")

        if seed_results:
            lines.append(f"| Seeds Copied | {seed_results.get('copied', 0)} |")

        if test_results:
            lines.append(f"| Tests Converted | {test_results.get('converted', 0)} |")
            lines.append(f"| Tests Skipped (Freshness) | {test_results.get('skipped', 0)} |")
            lines.append(f"| Test Errors | {test_results.get('errors', 0)} |")

        if validation_result:
            status = "✅ Passed" if validation_result.get("is_valid", False) else "❌ Failed"
            error_count = validation_result.get("error_count", 0)
            lines.append(f"| Validation Status | {status} |")
            lines.append(f"| Validation Errors | {error_count} |")

        if ots_compilation_result:
            status = "✅ Success" if ots_compilation_result.get("success", False) else "❌ Failed"
            lines.append(f"| OTS Compilation Status | {status} |")
            if ots_compilation_result.get("success"):
                lines.append(
                    f"| OTS Modules Generated | {ots_compilation_result.get('ots_modules_count', 0)} |"
                )

        lines.extend(["", "---", ""])
        return lines

    def _generate_validation_section(self, validation_result: dict[str, Any] | None) -> list[str]:
        """Generate validation results section."""
        if not validation_result:
            return []

        lines = ["## Validation Results", ""]

        if validation_result.get("is_valid", False):
            lines.append("✅ **All validation checks passed**")
        else:
            lines.append(
                f"❌ **Validation failed with {validation_result.get('error_count', 0)} error(s)**"
            )

        lines.append("")

        # Syntax errors
        syntax_errors = validation_result.get("syntax_errors", [])
        if syntax_errors:
            lines.append("### Syntax Errors")
            lines.append("")
            for error in syntax_errors:
                file = error.get("file", "unknown")
                err_msg = error.get("error", "Unknown error")
                lines.append(f"- **{file}**: {err_msg}")
            lines.append("")

        # Dependency errors
        dep_errors = validation_result.get("dependency_errors", [])
        if dep_errors:
            lines.append("### Dependency Errors")
            lines.append("")
            for error in dep_errors:
                file = error.get("file", "unknown")
                err_msg = error.get("error", "Unknown error")
                lines.append(f"- **{file}**: {err_msg}")
            lines.append("")

        # Metadata errors
        meta_errors = validation_result.get("metadata_errors", [])
        if meta_errors:
            lines.append("### Metadata Errors")
            lines.append("")
            for error in meta_errors:
                file = error.get("file", "unknown")
                err_msg = error.get("error", "Unknown error")
                lines.append(f"- **{file}**: {err_msg}")
            lines.append("")

        # Execution errors
        exec_errors = validation_result.get("execution_errors", [])
        if exec_errors:
            lines.append("### Execution Errors")
            lines.append("")
            for error in exec_errors:
                err_msg = error.get("error", "Unknown error")
                lines.append(f"- {err_msg}")
            lines.append("")

        lines.extend(["---", ""])
        return lines

    def _generate_ots_compilation_section(
        self, ots_compilation_result: dict[str, Any] | None
    ) -> list[str]:
        """Generate OTS compilation results section."""
        if not ots_compilation_result:
            return []

        lines = ["## OTS Compilation Results", ""]

        if ots_compilation_result.get("success", False):
            lines.append("✅ **OTS compilation successful**")
            lines.append("")
            lines.append(
                f"- **OTS Modules Generated**: {ots_compilation_result.get('ots_modules_count', 0)}"
            )
            lines.append(
                f"- **Parsed Models**: {ots_compilation_result.get('parsed_models_count', 0)}"
            )
            lines.append(
                f"- **Parsed Functions**: {ots_compilation_result.get('parsed_functions_count', 0)}"
            )
            output_folder = ots_compilation_result.get("output_folder", "")
            if output_folder:
                lines.append(f"- **Output Location**: `{output_folder}`")
        else:
            lines.append("❌ **OTS compilation failed**")
            lines.append("")
            error = ots_compilation_result.get("error", "Unknown error")
            lines.append(f"**Error**: {error}")

        lines.extend(["", "---", ""])
        return lines

    def _generate_models_section(self, conversion_results: dict[str, Any]) -> list[str]:
        """Generate model conversion details section."""
        lines = ["## Model Conversion Details", ""]
        conversion_log = conversion_results.get("conversion_log", [])
        if conversion_log:
            lines.append("| Model | Status | Table Name | Warnings |")
            lines.append("|-------|--------|------------|----------|")
            for entry in conversion_log:
                model = entry.get("model", "unknown")
                status = entry.get("status", "unknown")
                table_name = entry.get("table_name", "-")
                warnings = entry.get("warnings", [])
                warnings_str = "; ".join(warnings[:2]) if warnings else "-"
                if len(warnings) > 2:
                    warnings_str += f" (+{len(warnings) - 2} more)"
                lines.append(f"| {model} | {status} | {table_name} | {warnings_str} |")
        else:
            lines.append("No models were converted.")
        lines.extend(["", "---", ""])
        return lines

    def _generate_variables_section(self, variables_info: dict[str, Any] | None) -> list[str]:
        """Generate variables section."""
        if not variables_info:
            return []

        lines = ["## Variables", ""]
        variables = variables_info.get("variables", {})
        if variables:
            lines.append("| Variable | Default Value | Defined In | Used In |")
            lines.append("|----------|---------------|------------|---------|")
            for var_name, var_info in sorted(variables.items()):
                default = var_info.get("default_value", "-")
                defined_in = var_info.get("defined_in", "-")
                used_in = var_info.get("used_in", [])
                used_in_str = ", ".join(used_in[:3]) if used_in else "-"
                if len(used_in) > 3:
                    used_in_str += f" (+{len(used_in) - 3} more)"
                lines.append(f"| {var_name} | {default} | {defined_in} | {used_in_str} |")
        else:
            lines.append("No variables found in the project.")
        lines.extend(["", "---", ""])
        return lines

    def _generate_tests_section(self, test_results: dict[str, Any] | None) -> list[str]:
        """Generate tests section."""
        if not test_results:
            return []

        lines = ["## Tests", ""]
        test_log = test_results.get("conversion_log", [])
        if test_log:
            lines.append("| Test File | Status | Notes |")
            lines.append("|-----------|--------|-------|")
            for entry in test_log:
                test_file = entry.get("rel_path", "unknown")
                if entry.get("converted"):
                    status = "✅ Converted"
                    notes = entry.get("target_file", "-")
                elif entry.get("skipped"):
                    status = "⏭️ Skipped"
                    warnings = entry.get("warnings", [])
                    notes = warnings[0] if warnings else "Freshness test"
                elif entry.get("errors"):
                    status = "❌ Error"
                    errors = entry.get("errors", [])
                    notes = errors[0] if errors else "Unknown error"
                else:
                    status = "❓ Unknown"
                    notes = "-"
                lines.append(f"| {test_file} | {status} | {notes} |")
        else:
            lines.append("No tests found in the project.")
        lines.extend(["", "---", ""])
        return lines

    def _generate_macros_section(self, macro_results: dict[str, Any] | None) -> list[str]:
        """Generate macros section."""
        if not macro_results:
            return []

        lines = ["## Macros", ""]
        macro_log = macro_results.get("conversion_log", [])
        if macro_log:
            lines.append("| Macro | Status | Notes |")
            lines.append("|-------|--------|-------|")
            for entry in macro_log:
                macro = entry.get("macro", "unknown")
                status = entry.get("status", "unknown")
                reason = entry.get("reason", entry.get("udf_name", "-"))
                lines.append(f"| {macro} | {status} | {reason} |")
        else:
            lines.append("No macros found in the project.")
        lines.extend(["", "---", ""])
        return lines

    def _generate_warnings_section(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None,
    ) -> list[str]:
        """Generate warnings and recommendations section."""
        lines = ["## Warnings and Recommendations", ""]
        warnings = self._collect_all_warnings(conversion_results, macro_results, test_results)
        if warnings:
            for warning in warnings:
                lines.append(f"- {warning}")
        else:
            lines.append("No warnings.")
        lines.extend(["", "---", ""])
        return lines

    def _generate_packages_section(self, packages_info: dict[str, Any] | None) -> list[str]:
        """Generate packages section."""
        if not packages_info or not packages_info.get("has_packages"):
            return []

        lines = ["## dbt Packages", ""]
        packages = packages_info.get("packages", [])
        if packages:
            lines.append("This project uses the following dbt packages:")
            lines.append("")
            for pkg in packages:
                if isinstance(pkg, dict):
                    pkg_name = pkg.get("package", "unknown")
                    pkg_version = pkg.get("version", "latest")
                    lines.append(f"- **{pkg_name}** (version: {pkg_version})")
            lines.append("")
            lines.append(
                "⚠️ **Note**: Package macros and models may need to be manually converted or inlined. "
                "Check the dbt_packages directory for installed packages."
            )
        else:
            lines.append("dbt packages detected but package list not found.")
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines

    def _generate_unsupported_features_section(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None,
    ) -> list[str]:
        """Generate unsupported features section."""
        lines = ["## Unsupported Features", ""]
        unsupported = self._collect_unsupported_features(
            conversion_results, macro_results, test_results
        )
        if unsupported:
            for feature in unsupported:
                lines.append(f"- {feature}")
        else:
            lines.append("All features were successfully converted.")
        lines.append("")
        return lines

    def _generate_json_log(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        variables_info: dict[str, Any] | None,
        seed_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None = None,
        packages_info: dict[str, Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        ots_compilation_result: dict[str, Any] | None = None,
    ) -> None:
        """Generate JSON conversion log."""
        log_data = {
            "summary": {
                "total_models": conversion_results.get("total", 0),
                "converted_models": conversion_results.get("converted", 0),
                "python_models": conversion_results.get("python_models", 0),
                "errors": conversion_results.get("errors", 0),
            },
            "models": conversion_results.get("conversion_log", []),
        }

        if validation_result:
            log_data["validation"] = validation_result

        if ots_compilation_result:
            log_data["ots_compilation"] = ots_compilation_result

        if macro_results:
            log_data["macros"] = {
                "converted": macro_results.get("converted", 0),
                "unconvertible": macro_results.get("unconvertible", 0),
                "total": macro_results.get("total", 0),
                "conversion_log": macro_results.get("conversion_log", []),
            }

        if variables_info:
            log_data["variables"] = variables_info

        if seed_results:
            log_data["seeds"] = seed_results

        if test_results:
            log_data["tests"] = {
                "converted": test_results.get("converted", 0),
                "skipped": test_results.get("skipped", 0),
                "errors": test_results.get("errors", 0),
                "total": test_results.get("total", 0),
                "conversion_log": test_results.get("conversion_log", []),
            }

        if packages_info:
            log_data["packages"] = packages_info

        # Write JSON log
        log_file = self.target_path / CONVERSION_LOG_FILE
        with log_file.open("w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Generated conversion log: {log_file}")

    def _collect_all_warnings(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None = None,
    ) -> list[str]:
        """Collect all warnings from conversion results."""
        warnings = []

        # Collect from model conversion
        conversion_log = conversion_results.get("conversion_log", [])
        for entry in conversion_log:
            entry_warnings = entry.get("warnings", [])
            warnings.extend(entry_warnings)

        # Collect from macro conversion
        if macro_results:
            macro_log = macro_results.get("conversion_log", [])
            for entry in macro_log:
                if entry.get("status") == "unconvertible":
                    reason = entry.get("reason", "Unknown reason")
                    warnings.append(f"Macro {entry.get('macro')} could not be converted: {reason}")

        # Collect from test conversion
        if test_results:
            test_log = test_results.get("conversion_log", [])
            for entry in test_log:
                entry_warnings = entry.get("warnings", [])
                warnings.extend(entry_warnings)

        return list(set(warnings))  # Remove duplicates

    def _collect_unsupported_features(
        self,
        conversion_results: dict[str, Any],
        macro_results: dict[str, Any] | None,
        test_results: dict[str, Any] | None = None,
    ) -> list[str]:
        """Collect list of unsupported features."""
        features = []

        # Check for unsupported incremental strategies
        conversion_log = conversion_results.get("conversion_log", [])
        for entry in conversion_log:
            warnings = entry.get("warnings", [])
            for warning in warnings:
                if "Unsupported incremental strategy" in warning:
                    features.append(warning)

        # Check for unconvertible macros
        if macro_results:
            macro_log = macro_results.get("conversion_log", [])
            for entry in macro_log:
                if entry.get("status") == "unconvertible":
                    features.append(
                        f"Macro {entry.get('macro')}: {entry.get('reason', 'Unknown reason')}"
                    )

        # Check for skipped freshness tests
        if test_results:
            test_log = test_results.get("conversion_log", [])
            for entry in test_log:
                if entry.get("skipped"):
                    test_file = entry.get("rel_path", "unknown")
                    features.append(
                        f"Source freshness test {test_file}: Not supported in t4t yet (see issue #01-freshness-tests)"
                    )

        return features
