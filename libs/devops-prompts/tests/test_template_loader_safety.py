"""Safety-related tests for template loader."""

import pytest
from devops_prompts.template_loader import TemplateLoader


@pytest.fixture
def loader():
    return TemplateLoader("/tmp/nonexistent-templates")


def test_base_template_includes_safety_notice(loader):
    template = loader.get_template("base")
    assert "Safety Notice" in template["output_format"], "Safety notice missing in output format"
    assert "destructive/irreversible" in template["constraints"], "Constraints must include destructive/irreversible warning guidance"
