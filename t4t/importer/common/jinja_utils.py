"""
Common utilities for Jinja template analysis in importers.
"""

import re


def has_complex_jinja(content: str) -> bool:
    """
    Detect complex Jinja patterns that require special handling.

    Complex patterns include:
    - Loops: {% for ... %}
    - Complex conditionals: {% if ... %} with {% else %} or {% elif %}
    - Multiple if statements

    Args:
        content: Content to analyze (SQL, macro body, etc.)

    Returns:
        True if complex Jinja patterns are detected
    """
    # Check for loops
    if re.search(r"{%\s*for\s+", content, re.IGNORECASE):
        return True

    # Check for complex conditionals (multiple branches)
    if_pattern = r"{%\s*if\s+"
    else_pattern = r"{%\s*else\s*%}"
    elif_pattern = r"{%\s*elif\s+"

    if_count = len(re.findall(if_pattern, content, re.IGNORECASE))
    else_count = len(re.findall(else_pattern, content, re.IGNORECASE))
    elif_count = len(re.findall(elif_pattern, content, re.IGNORECASE))

    # If there are multiple branches, it's complex
    return bool(else_count > 0 or elif_count > 0 or if_count > 1)


def has_dbt_specific_functions(content: str) -> bool:
    """
    Check if content uses dbt-specific functions that can't be easily converted.

    Args:
        content: Content to analyze

    Returns:
        True if dbt-specific functions are found
    """
    dbt_specific = ["ref(", "source(", "var(", "target.", "this.", "config("]
    content_lower = content.lower()
    return any(func in content_lower for func in dbt_specific)


def has_adapter_specific_features(content: str) -> bool:
    """
    Check if content uses adapter-specific features.

    Args:
        content: Content to analyze

    Returns:
        True if adapter-specific features are found
    """
    return "adapter." in content.lower()


def get_complex_jinja_reason(content: str) -> str:
    """
    Get reason why content contains complex Jinja.

    Args:
        content: Content to analyze

    Returns:
        Reason string describing the complex pattern found
    """
    if re.search(r"{%\s*for\s+", content, re.IGNORECASE):
        return "Contains Jinja loops ({% for %})"

    if_pattern = r"{%\s*if\s+"
    else_pattern = r"{%\s*else\s*%}"
    elif_pattern = r"{%\s*elif\s+"

    if_count = len(re.findall(if_pattern, content, re.IGNORECASE))
    else_count = len(re.findall(else_pattern, content, re.IGNORECASE))
    elif_count = len(re.findall(elif_pattern, content, re.IGNORECASE))

    if else_count > 0:
        return "Contains Jinja conditionals with {% else %}"
    if elif_count > 0:
        return "Contains Jinja conditionals with {% elif %}"
    if if_count > 1:
        return f"Contains multiple Jinja conditionals ({if_count} if statements)"

    return "Contains complex Jinja patterns"
