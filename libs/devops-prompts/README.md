# devops-prompts

Prompt engineering and query routing for DevOps chatbot.

## Features

- Query type detection and routing
- Domain validation (DevOps-only queries)
- Template loading from YAML files
- Time range extraction

## Installation

```bash
pip install -e .
```

## Usage

```python
from devops_prompts import QueryRouter, DomainValidator, TemplateLoader

# Validate query is DevOps-related
validator = DomainValidator()
if validator.is_devops_query("Why is my pod failing?"):
    # Route to appropriate template
    router = QueryRouter()
    query_type = router.detect_query_type("Why is my pod failing?")
    
    # Load template
    loader = TemplateLoader()
    template = loader.get_template(query_type)
```
