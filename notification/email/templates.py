"""Email template rendering."""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any


class TemplateRenderer:
    """Email template renderer using Python string.Template."""

    def __init__(self, template_dir: str):
        """Initialize template renderer.

        Args:
            template_dir: Directory containing template files
        """
        self.template_dir = Path(template_dir)

    def render(self, template_name: str, data: dict[str, Any]) -> str:
        """Render a template with provided data.

        Args:
            template_name: Name of the template (without .txt extension)
            data: Template data dictionary

        Returns:
            Rendered template string

        Raises:
            FileNotFoundError: If template file doesn't exist
            ValueError: If template rendering fails
        """
        template_path = self.template_dir / f"{template_name}.txt"

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Read template file
        template_content = template_path.read_text()

        # Render using string.Template
        # This uses $variable or ${variable} syntax
        template = Template(template_content)

        try:
            return template.substitute(data)
        except KeyError as e:
            raise ValueError(
                f"Missing required template variable: {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Failed to render template {template_name}: {e}"
            ) from e
