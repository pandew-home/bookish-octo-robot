#!/usr/bin/env python3
"""
Manual test for K8sGPT Result CRD reading functionality.
This test validates the _format_k8sgpt_result method without requiring pytest.
"""

from datetime import datetime


def format_k8sgpt_result(result: dict) -> dict:
    """
    Format K8sGPT result data into structured dictionary.
    This is a copy of the method from enrichment_engine.py for testing.
    """
    metadata = result.get('metadata', {})
    spec = result.get('spec', {})
    status = result.get('status', {})
    
    # Extract basic info
    kind = spec.get('kind', 'Unknown')
    resource_name = spec.get('name', 'Unknown')
    
    # Extract error details - K8sGPT stores issues in the 'error' field
    error_list = spec.get('error', [])
    
    # Parse problem and solution from error list
    # K8sGPT typically formats errors as text descriptions
    problem = spec.get('details', '')
    solution = ''
    
    if isinstance(error_list, list) and error_list:
        # Combine error messages into problem description
        if not problem:
            problem = ' '.join(str(e) for e in error_list)
        # K8sGPT may provide solutions in the error text
        # Look for solution indicators
        for error_text in error_list:
            if isinstance(error_text, str) and ('solution' in error_text.lower() or 'fix' in error_text.lower()):
                solution = error_text
                break
    
    # Determine severity based on error content and kind
    # Default to 'medium' if not specified
    severity = 'medium'
    problem_lower = problem.lower()
    
    # High severity indicators
    if any(indicator in problem_lower for indicator in [
        'crashloopbackoff', 'imagepullbackoff', 'oomkilled', 
        'failed', 'error', 'critical', 'down', 'unavailable'
    ]):
        severity = 'high'
    # Low severity indicators
    elif any(indicator in problem_lower for indicator in [
        'warning', 'pending', 'info', 'notice'
    ]):
        severity = 'low'
    
    # Extract namespace - may be in metadata or spec
    namespace = metadata.get('namespace', spec.get('namespace', 'default'))
    
    # Extract analyzer name - K8sGPT uses 'backend' field
    analyzer = spec.get('backend', 'Unknown')
    
    # Extract timestamp - use creation timestamp from metadata
    timestamp = metadata.get('creationTimestamp', '')
    if timestamp:
        try:
            # Parse ISO format timestamp
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # Keep as string if parsing fails
            pass
    
    return {
        'name': metadata.get('name', 'unknown'),
        'kind': kind,
        'namespace': namespace,
        'severity': severity,
        'problem': problem if problem else 'No problem description available',
        'solution': solution if solution else 'No solution provided',
        'analyzer': analyzer,
        'timestamp': timestamp,
        'details': {
            'resource_name': resource_name,
            'error': error_list,
            'backend': spec.get('backend', 'Unknown')
        }
    }


def test_complete_result():
    """Test formatting a complete K8sGPT result with all fields."""
    print("Test 1: Complete K8sGPT Result")
    
    mock_result = {
        'metadata': {
            'name': 'result-1',
            'namespace': 'default',
            'creationTimestamp': '2024-01-15T10:30:00Z'
        },
        'spec': {
            'kind': 'Pod',
            'name': 'test-pod',
            'namespace': 'default',
            'details': 'Pod is in CrashLoopBackOff',
            'error': ['Container failed with exit code 1'],
            'backend': 'openai'
        }
    }
    
    formatted = format_k8sgpt_result(mock_result)
    
    # Verify all required fields
    assert formatted['name'] == 'result-1', f"Expected name 'result-1', got {formatted['name']}"
    assert formatted['kind'] == 'Pod', f"Expected kind 'Pod', got {formatted['kind']}"
    assert formatted['namespace'] == 'default', f"Expected namespace 'default', got {formatted['namespace']}"
    assert formatted['severity'] in ['low', 'medium', 'high'], f"Invalid severity: {formatted['severity']}"
    assert 'problem' in formatted, "Missing 'problem' field"
    assert 'solution' in formatted, "Missing 'solution' field"
    assert formatted['analyzer'] == 'openai', f"Expected analyzer 'openai', got {formatted['analyzer']}"
    assert 'timestamp' in formatted, "Missing 'timestamp' field"
    assert 'details' in formatted, "Missing 'details' field"
    
    print("✓ All required fields present")
    print(f"  - Name: {formatted['name']}")
    print(f"  - Kind: {formatted['kind']}")
    print(f"  - Namespace: {formatted['namespace']}")
    print(f"  - Severity: {formatted['severity']}")
    print(f"  - Problem: {formatted['problem']}")
    print(f"  - Solution: {formatted['solution']}")
    print(f"  - Analyzer: {formatted['analyzer']}")
    print(f"  - Timestamp: {formatted['timestamp']}")
    print()


def test_severity_detection():
    """Test severity detection based on problem content."""
    print("Test 2: Severity Detection")
    
    # Test high severity
    high_severity_result = {
        'metadata': {'name': 'result-high', 'creationTimestamp': '2024-01-15T10:30:00Z'},
        'spec': {
            'kind': 'Pod',
            'name': 'failing-pod',
            'details': 'Pod is in CrashLoopBackOff state',
            'error': ['Container failed'],
            'backend': 'openai'
        }
    }
    
    formatted = format_k8sgpt_result(high_severity_result)
    assert formatted['severity'] == 'high', f"Expected high severity, got {formatted['severity']}"
    print(f"✓ High severity detected correctly: {formatted['problem']}")
    
    # Test low severity
    low_severity_result = {
        'metadata': {'name': 'result-low', 'creationTimestamp': '2024-01-15T10:30:00Z'},
        'spec': {
            'kind': 'Pod',
            'name': 'pending-pod',
            'details': 'Pod is in Pending state - waiting for resources',
            'error': ['Warning: Insufficient resources'],
            'backend': 'openai'
        }
    }
    
    formatted = format_k8sgpt_result(low_severity_result)
    assert formatted['severity'] == 'low', f"Expected low severity, got {formatted['severity']}"
    print(f"✓ Low severity detected correctly: {formatted['problem']}")
    
    # Test medium severity (default)
    medium_severity_result = {
        'metadata': {'name': 'result-medium', 'creationTimestamp': '2024-01-15T10:30:00Z'},
        'spec': {
            'kind': 'Service',
            'name': 'test-service',
            'details': 'Service has no endpoints',
            'error': ['No backend pods available'],
            'backend': 'openai'
        }
    }
    
    formatted = format_k8sgpt_result(medium_severity_result)
    assert formatted['severity'] == 'medium', f"Expected medium severity, got {formatted['severity']}"
    print(f"✓ Medium severity detected correctly: {formatted['problem']}")
    print()


def test_missing_fields():
    """Test handling of missing optional fields."""
    print("Test 3: Missing Optional Fields")
    
    minimal_result = {
        'metadata': {'name': 'minimal-result'},
        'spec': {
            'kind': 'Service',
            'name': 'test-service'
        }
    }
    
    formatted = format_k8sgpt_result(minimal_result)
    
    # Should handle missing fields gracefully
    assert formatted['name'] == 'minimal-result', f"Expected name 'minimal-result', got {formatted['name']}"
    assert formatted['kind'] == 'Service', f"Expected kind 'Service', got {formatted['kind']}"
    assert formatted['namespace'] == 'default', f"Expected default namespace, got {formatted['namespace']}"
    assert formatted['severity'] in ['low', 'medium', 'high'], f"Invalid severity: {formatted['severity']}"
    assert 'problem' in formatted, "Missing 'problem' field"
    assert 'solution' in formatted, "Missing 'solution' field"
    assert 'analyzer' in formatted, "Missing 'analyzer' field"
    assert 'timestamp' in formatted, "Missing 'timestamp' field"
    assert 'details' in formatted, "Missing 'details' field"
    
    print("✓ Missing fields handled gracefully")
    print(f"  - Default namespace: {formatted['namespace']}")
    print(f"  - Default problem: {formatted['problem']}")
    print(f"  - Default solution: {formatted['solution']}")
    print()


def test_timestamp_parsing():
    """Test timestamp parsing."""
    print("Test 4: Timestamp Parsing")
    
    result_with_timestamp = {
        'metadata': {
            'name': 'result-timestamp',
            'creationTimestamp': '2024-01-15T10:30:00Z'
        },
        'spec': {
            'kind': 'Pod',
            'name': 'test-pod',
            'details': 'Test issue',
            'backend': 'openai'
        }
    }
    
    formatted = format_k8sgpt_result(result_with_timestamp)
    assert isinstance(formatted['timestamp'], datetime), f"Expected datetime object, got {type(formatted['timestamp'])}"
    print(f"✓ Timestamp parsed correctly: {formatted['timestamp']}")
    print()


if __name__ == '__main__':
    print("=" * 60)
    print("K8sGPT Result CRD Formatting Tests")
    print("=" * 60)
    print()
    
    try:
        test_complete_result()
        test_severity_detection()
        test_missing_fields()
        test_timestamp_parsing()
        
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        exit(1)
