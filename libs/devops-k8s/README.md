# devops-k8s

Kubernetes utilities for DevOps chatbot.

## Features

- Cluster health monitoring
- Snapshot capture and comparison
- RBAC helpers
- Kubernetes API client utilities

## Installation

```bash
pip install -e .
```

## Usage

```python
from devops_k8s import HealthMonitor

monitor = HealthMonitor()
weather = monitor.get_current_weather()
print(f"Cluster health: {weather.state}")
```
