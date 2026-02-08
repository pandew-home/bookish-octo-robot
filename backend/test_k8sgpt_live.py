#!/usr/bin/env python3
"""
Live K8sGPT Result CRD Test Script

This script connects to a real Kubernetes cluster and reads K8sGPT Result CRDs
to validate our implementation against actual data.

Usage:
    python test_k8sgpt_live.py --cluster <cluster-name> --region <aws-region>

Requirements:
    - Valid AWS credentials (Kion)
    - Access to EKS cluster
    - K8sGPT operator installed in target cluster
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, '.')

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from k8sgpt_reader import K8sGPTReader, K8sGPTResult
from weather_calculator import WeatherCalculator, WeatherState
from eks_auth import get_eks_bearer_token
from cluster_manager import get_k8s_clients


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_result(result: K8sGPTResult):
    """Print a formatted K8sGPT result."""
    severity_emoji = {
        'high': '🔴',
        'medium': '🟡',
        'low': '🟢'
    }
    
    emoji = severity_emoji.get(result.severity, '⚪')
    
    print(f"\n{emoji} {result.name}")
    print(f"   Kind: {result.kind}")
    print(f"   Namespace: {result.namespace}")
    print(f"   Severity: {result.severity.upper()}")
    print(f"   Problem: {result.problem[:100]}...")
    print(f"   Solution: {result.solution[:100]}...")
    print(f"   Analyzer: {result.analyzer}")
    print(f"   Timestamp: {result.timestamp}")


def print_weather(weather_response):
    """Print formatted weather response."""
    weather_emoji = {
        'sunny': '☀️',
        'partly_cloudy': '🌤️',
        'cloudy': '☁️',
        'rainy': '🌧️',
        'stormy': '⛈️',
        'unknown': '❓'
    }
    
    emoji = weather_emoji.get(weather_response.weather_state.value, '❓')
    
    print(f"\n{emoji} Weather State: {weather_response.weather_state.value.upper()}")
    print(f"   Cluster: {weather_response.cluster_name}")
    print(f"   Version: {weather_response.cluster_version}")
    print(f"   Total Issues: {weather_response.k8sgpt_result_count}")
    print(f"   Timestamp: {weather_response.timestamp}")


async def test_read_results(cluster_name: str, region: str):
    """Test reading K8sGPT results from a live cluster."""
    
    print_section("K8sGPT Live Test")
    print(f"Cluster: {cluster_name}")
    print(f"Region: {region}")
    
    try:
        # Get AWS credentials from environment
        print("\n📋 Step 1: Loading AWS credentials...")
        # Note: In production, this would come from Kion credentials
        # For testing, use AWS CLI credentials or environment variables
        
        # Get K8s clients
        print("📋 Step 2: Creating Kubernetes clients...")
        # Note: This is simplified - in production use cluster_manager.get_k8s_clients()
        config.load_kube_config()  # Load from ~/.kube/config for testing
        custom_api = client.CustomObjectsApi()
        core_api = client.CoreV1Api()
        
        print("✓ Kubernetes clients created")
        
        # Create K8sGPT reader
        print("\n📋 Step 3: Reading K8sGPT Result CRDs...")
        reader = K8sGPTReader(custom_api)
        
        # Read all results
        results = await reader.read_results()
        
        print(f"✓ Found {len(results)} K8sGPT Result CRDs")
        
        if len(results) == 0:
            print("\n⚠️  No K8sGPT results found. This could mean:")
            print("   - K8sGPT operator is not installed")
            print("   - Cluster is healthy (no issues detected)")
            print("   - K8sGPT hasn't completed its first scan yet")
            return
        
        # Display results
        print_section("K8sGPT Results")
        
        for result in results:
            print_result(result)
        
        # Test severity counting
        print_section("Severity Analysis")
        
        calculator = WeatherCalculator()
        severity_counts = calculator._count_by_severity(results)
        
        print(f"\n🔴 High Severity: {severity_counts['high']}")
        print(f"🟡 Medium Severity: {severity_counts['medium']}")
        print(f"🟢 Low Severity: {severity_counts['low']}")
        
        # Calculate weather
        print_section("Weather Calculation")
        
        # Get cluster version
        version_info = core_api.get_code()
        cluster_version = f"{version_info.major}.{version_info.minor}"
        
        weather_response = calculator.calculate_weather(
            results=results,
            cluster_name=cluster_name,
            cluster_version=cluster_version
        )
        
        print_weather(weather_response)
        
        # Display top issues
        if weather_response.top_issues:
            print("\n📊 Top Issues:")
            for i, issue in enumerate(weather_response.top_issues, 1):
                severity_emoji = {
                    'high': '🔴',
                    'medium': '🟡',
                    'low': '🟢'
                }
                emoji = severity_emoji.get(issue.severity, '⚪')
                print(f"   {i}. {emoji} {issue.kind}/{issue.name} ({issue.namespace})")
                print(f"      {issue.problem[:80]}...")
        
        # Test filtering
        print_section("Filtering Tests")
        
        # Filter by severity
        high_severity = await reader.read_results(severity_filter='high')
        print(f"\n🔴 High severity results: {len(high_severity)}")
        
        # Filter by namespace
        namespaces = set(r.namespace for r in results)
        print(f"\n📦 Namespaces with issues: {', '.join(namespaces)}")
        
        for ns in namespaces:
            ns_results = reader.filter_by_relevance(results, namespaces=[ns])
            print(f"   - {ns}: {len(ns_results)} issues")
        
        # Filter by kind
        kinds = set(r.kind for r in results)
        print(f"\n🔧 Resource kinds with issues: {', '.join(kinds)}")
        
        for kind in kinds:
            kind_results = reader.filter_by_relevance(results, kinds=[kind])
            print(f"   - {kind}: {len(kind_results)} issues")
        
        # Test sorting
        print_section("Sorting Test")
        
        sorted_results = reader.sort_by_severity(results)
        print("\n📊 Results sorted by severity:")
        for i, result in enumerate(sorted_results[:5], 1):
            print(f"   {i}. [{result.severity.upper()}] {result.kind}/{result.name}")
        
        # Export to JSON
        print_section("JSON Export")
        
        weather_dict = weather_response.to_dict()
        print("\n📄 Weather Response JSON:")
        print(json.dumps(weather_dict, indent=2))
        
        # Save to file
        output_file = f"k8sgpt_results_{cluster_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                'weather': weather_dict,
                'results': [r.to_dict() for r in results]
            }, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")
        
        # Summary
        print_section("Test Summary")
        print(f"\n✓ Successfully read {len(results)} K8sGPT Result CRDs")
        print(f"✓ Weather state: {weather_response.weather_state.value}")
        print(f"✓ All parsing and filtering operations completed successfully")
        print("\n🎉 Live test completed successfully!")
        
    except ApiException as e:
        if e.status == 404:
            print("\n❌ K8sGPT Result CRDs not found")
            print("   The K8sGPT operator may not be installed in this cluster.")
            print("\n   To install K8sGPT:")
            print("   1. helm repo add k8sgpt https://charts.k8sgpt.ai/")
            print("   2. helm install k8sgpt k8sgpt/k8sgpt-operator")
        elif e.status == 403:
            print("\n❌ Permission denied")
            print("   Your service account does not have permission to read K8sGPT Result CRDs.")
            print("\n   Required RBAC permissions:")
            print("   - apiGroups: [core.k8sgpt.ai]")
            print("   - resources: [results]")
            print("   - verbs: [get, list]")
        else:
            print(f"\n❌ Kubernetes API error: {e}")
            print(f"   Status: {e.status}")
            print(f"   Reason: {e.reason}")
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Test K8sGPT Result CRD reading against a live cluster'
    )
    parser.add_argument(
        '--cluster',
        required=True,
        help='EKS cluster name'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--namespace',
        help='Filter by namespace (optional)'
    )
    
    args = parser.parse_args()
    
    # Run async test
    asyncio.run(test_read_results(args.cluster, args.region))


if __name__ == '__main__':
    main()
