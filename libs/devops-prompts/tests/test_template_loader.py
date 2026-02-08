"""Tests for template loader."""

import pytest
import tempfile
from pathlib import Path

from devops_prompts.template_loader import TemplateLoader


@pytest.fixture
def temp_templates_dir():
    """Create temporary templates directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def loader(temp_templates_dir):
    """Create template loader instance with temporary directory."""
    return TemplateLoader(temp_templates_dir)


def test_get_default_base_template(loader):
    """Test getting default base template."""
    template = loader.get_template("base")
    assert template["name"] == "base"
    assert "system_rules" in template
    assert "constraints" in template
    assert "output_format" in template


def test_get_default_troubleshooting_template(loader):
    """Test getting default troubleshooting template."""
    template = loader.get_template("troubleshooting")
    assert template["name"] == "troubleshooting"
    assert "troubleshooting" in template["description"].lower()


def test_get_default_networking_template(loader):
    """Test getting default networking template."""
    template = loader.get_template("networking")
    assert template["name"] == "networking"
    assert "networking" in template["description"].lower()


def test_get_default_deployment_template(loader):
    """Test getting default deployment template."""
    template = loader.get_template("deployment")
    assert template["name"] == "deployment"
    assert "deployment" in template["description"].lower()


def test_get_default_gitops_template(loader):
    """Test getting default gitops template."""
    template = loader.get_template("gitops")
    assert template["name"] == "gitops"
    assert "gitops" in template["description"].lower()


def test_get_default_security_template(loader):
    """Test getting default security template."""
    template = loader.get_template("security")
    assert template["name"] == "security"
    assert "security" in template["description"].lower()


def test_get_default_analysis_template(loader):
    """Test getting default analysis template."""
    template = loader.get_template("analysis")
    assert template["name"] == "analysis"
    assert "analyz" in template["description"].lower()


def test_get_default_general_template(loader):
    """Test getting default general template."""
    template = loader.get_template("general")
    assert template["name"] == "general"
    assert "general" in template["description"].lower()


def test_template_caching(loader):
    """Test that templates are cached."""
    template1 = loader.get_template("troubleshooting")
    template2 = loader.get_template("troubleshooting")
    # Should be the same object due to caching
    assert template1 is template2


def test_clear_cache(loader):
    """Test cache clearing."""
    template1 = loader.get_template("troubleshooting")
    loader.clear_cache()
    template2 = loader.get_template("troubleshooting")
    # Should be different objects after cache clear
    assert template1 is not template2
    # But should have same content
    assert template1 == template2


def test_save_and_load_template(loader, temp_templates_dir):
    """Test saving and loading custom template."""
    custom_template = {
        "name": "custom",
        "description": "Custom test template",
        "system_rules": "Custom rules",
        "constraints": "Custom constraints",
        "output_format": "Custom format"
    }
    
    # Save template
    success = loader.save_template("custom", custom_template)
    assert success
    
    # Verify file was created
    template_file = Path(temp_templates_dir) / "custom.yaml"
    assert template_file.exists()
    
    # Clear cache and load template
    loader.clear_cache()
    loaded_template = loader.get_template("custom")
    
    # Should match saved template (merged with base)
    assert loaded_template["name"] == "custom"
    assert loaded_template["description"] == "Custom test template"
    assert loaded_template["system_rules"] == "Custom rules"
