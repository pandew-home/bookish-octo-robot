# devops-kb

Knowledge base management for DevOps chatbot.

## Features

- Two-tier knowledge base (Foundation Patterns + Solutions)
- Solution storage and retrieval
- Snapshot management
- Template management

## Installation

```bash
pip install -e .
```

## Usage

```python
from devops_kb import KnowledgeBase, Solution

kb = KnowledgeBase(storage_path="/data/knowledge-base")

# Add a solution
solution = Solution(
    problem_description="Pod failing with ImagePullBackOff",
    resolution_steps="Check image pull secret...",
    tags=["pod", "image", "registry"]
)
solution_id = kb.add_solution(solution)

# Search solutions
results = kb.search_solutions("image pull error")
```
