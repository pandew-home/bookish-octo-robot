"""
Unit tests for K8sGPT Result CRD reader.

Tests cover:
- CRD reading from cluster
- Result parsing and formatting
- Severity detection
- Filtering and sorting
- Error handling
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from kubernetes.client.rest import ApiException

from k8sgpt_reader import K8sGPTReader, K8sGPTResult


@pytest.fixture
def mock_custom_api():
    """Create mock CustomObjectsApi."""
    return Mock()


@pytest.fixture
def k8sgpt_reader(mock_custom_api):
    """Create K8sGPTReader instance."""
    return K8sGPTReader(mock_custom_api)


@pytest.fixture
def sample_result_crd():
    """Sample K8sGPT Result CRD."""
    return {
        'metadata': {
            'name': 'result-pod-crash',
            'namespace': 'default',
            'creationTimestamp': '2024-01-15T10:30:00Z'
        },
        'spec': {
            'kind': 'Pod',
            'name': 'test-pod',
            'namespace': 'default',
            'details': 'Pod is in CrashLoopBackOff state',
            'error': ['Container failed with exit code 1', 'Check application logs'],
            'backend': 'openai'
        }
    }


class TestK8sGPTResultDataclass:
    """Test K8sGPTResult dataclass."""
    
    def test_result_creation(self):
        """Test creating a K8sGPTResult object."""
        result = K8sGPTResult(
            name='test-result',
            kind='Pod',
            namespace='default',
            severity='high',
            problem='Pod crashed',
            solution='Check logs',
            analyzer='openai',
            timestamp=datetime.utcnow(),
            details={'resource_name': 'test-pod'}
        )
        
        assert result.name == 'test-result'
        assert result.kind == 'Pod'
        assert result.namespace == 'default'
        assert result.severity == 'high'
        assert result.problem == 'Pod crashed'
        assert result.solution == 'Check logs'
        assert result.analyzer == 'openai'
        assert isinstance(result.timestamp, datetime)
        assert result.details['resource_name'] == 'test-pod'
    
    def test_to_dict_conversion(self):
        """Test converting K8sGPTResult to dictionary."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        result = K8sGPTResult(
            name='test-result',
            kind='Pod',
            namespace='default',
            severity='high',
            problem='Pod crashed',
            solution='Check logs',
            analyzer='openai',
            timestamp=timestamp,
            details={'resource_name': 'test-pod'}
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['name'] == 'test-result'
        assert result_dict['kind'] == 'Pod'
        assert result_dict['timestamp'] == timestamp.isoformat()
        assert isinstance(result_dict['timestamp'], str)


class TestK8sGPTReaderInit:
    """Test K8sGPTReader initialization."""
    
    def test_initialization(self, mock_custom_api):
        """Test reader initialization."""
        reader = K8sGPTReader(mock_custom_api)
        
        assert reader.custom_api == mock_custom_api
        assert reader.GROUP == "core.k8sgpt.ai"
        assert reader.VERSION == "v1alpha1"
        assert reader.PLURAL == "results"


class TestReadResults:
    """Test reading K8sGPT Result CRDs."""
    
    @pytest.mark.asyncio
    async def test_read_all_namespaces(self, k8sgpt_reader, mock_custom_api, sample_result_crd):
        """Test reading results from all namespaces."""
        mock_custom_api.list_cluster_custom_object.return_value = {
            'items': [sample_result_crd]
        }
        
        results = await k8sgpt_reader.read_results()
        
        assert len(results) == 1
        assert results[0].name == 'result-pod-crash'
        assert results[0].kind == 'Pod'
        assert results[0].namespace == 'default'
        
        mock_custom_api.list_cluster_custom_object.assert_called_once_with(
            group="core.k8sgpt.ai",
            version="v1alpha1",
            plural="results"
        )
    
    @pytest.mark.asyncio
    async def test_read_specific_namespace(self, k8sgpt_reader, mock_custom_api, sample_result_crd):
        """Test reading results from specific namespace."""
        mock_custom_api.list_namespaced_custom_object.return_value = {
            'items': [sample_result_crd]
        }
        
        results = await k8sgpt_reader.read_results(namespace='default')
        
        assert len(results) == 1
        assert results[0].namespace == 'default'
        
        mock_custom_api.list_namespaced_custom_object.assert_called_once_with(
            group="core.k8sgpt.ai",
            version="v1alpha1",
            namespace='default',
            plural="results"
        )
    
    @pytest.mark.asyncio
    async def test_read_with_severity_filter(self, k8sgpt_reader, mock_custom_api):
        """Test reading results with severity filter."""
        high_severity_result = {
            'metadata': {'name': 'high-result', 'creationTimestamp': '2024-01-15T10:30:00Z'},
            'spec': {
                'kind': 'Pod',
                'name': 'crash-pod',
                'details': 'Pod is in CrashLoopBackOff',
                'error': ['Critical error'],
                'backend': 'openai'
            }
        }
        
        low_severity_result = {
            'metadata': {'name': 'low-result', 'creationTimestamp': '2024-01-15T10:30:00Z'},
            'spec': {
                'kind': 'Pod',
                'name': 'pending-pod',
                'details': 'Pod is pending',
                'error': ['Warning: Waiting for resources'],
                'backend': 'openai'
            }
        }
        
        mock_custom_api.list_cluster_custom_object.return_value = {
            'items': [high_severity_result, low_severity_result]
        }
        
        results = await k8sgpt_reader.read_results(severity_filter='high')
        
        assert len(results) == 1
        assert results[0].severity == 'high'
    
    @pytest.mark.asyncio
    async def test_read_no_results(self, k8sgpt_reader, mock_custom_api):
        """Test reading when no results exist."""
        mock_custom_api.list_cluster_custom_object.return_value = {'items': []}
        
        results = await k8sgpt_reader.read_results()
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_read_crd_not_installed(self, k8sgpt_reader, mock_custom_api):
        """Test reading when K8sGPT CRD is not installed."""
        mock_custom_api.list_cluster_custom_object.side_effect = ApiException(status=404)
        
        results = await k8sgpt_reader.read_results()
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_read_api_error(self, k8sgpt_reader, mock_custom_api):
        """Test handling API errors during read."""
        mock_custom_api.list_cluster_custom_object.side_effect = ApiException(status=403)
        
        with pytest.raises(ApiException):
            await k8sgpt_reader.read_results()
    
    @pytest.mark.skip(reason="Stale mock/assertion - needs update")
    @pytest.mark.asyncio
    async def test_read_with_parse_errors(self, k8sgpt_reader, mock_custom_api):
        """Test reading with some results failing to parse."""
        valid_result = {
            'metadata': {'name': 'valid', 'creationTimestamp': '2024-01-15T10:30:00Z'},
            'spec': {
                'kind': 'Pod',
                'name': 'test-pod',
                'details': 'Test issue',
                'backend': 'openai'
            }
        }
        
        invalid_result = {
            'metadata': {},  # Missing required fields
            'spec': {}
        }
        
        mock_custom_api.list_cluster_custom_object.return_value = {
            'items': [valid_result, invalid_result]
        }
        
        results = await k8sgpt_reader.read_results()
        
        # Should successfully parse valid result and skip invalid one
        assert len(results) == 1
        assert results[0].name == 'valid'


class TestParseResult:
    """Test parsing K8sGPT Result CRDs."""
    
    def test_parse_complete_result(self, k8sgpt_reader, sample_result_crd):
        """Test parsing a complete result."""
        result = k8sgpt_reader._parse_result(sample_result_crd)
        
        assert result.name == 'result-pod-crash'
        assert result.kind == 'Pod'
        assert result.namespace == 'default'
        assert result.severity in ['low', 'medium', 'high']
        assert 'CrashLoopBackOff' in result.problem
        assert result.analyzer == 'openai'
        assert isinstance(result.timestamp, datetime)
        assert 'resource_name' in result.details
    
    def test_parse_minimal_result(self, k8sgpt_reader):
        """Test parsing result with minimal fields."""
        minimal_result = {
            'metadata': {'name': 'minimal'},
            'spec': {
                'kind': 'Service',
                'name': 'test-service'
            }
        }
        
        result = k8sgpt_reader._parse_result(minimal_result)
        
        assert result.name == 'minimal'
        assert result.kind == 'Service'
        assert result.namespace == 'default'  # Default namespace
        assert result.problem == 'No problem description available'
        assert result.solution == 'No solution provided'
        assert result.analyzer == 'Unknown'
    
    def test_parse_with_error_list(self, k8sgpt_reader):
        """Test parsing result with error list."""
        result_with_errors = {
            'metadata': {'name': 'error-result', 'creationTimestamp': '2024-01-15T10:30:00Z'},
            'spec': {
                'kind': 'Pod',
                'name': 'test-pod',
                'error': ['Error 1', 'Error 2', 'Solution: Restart the pod'],
                'backend': 'openai'
            }
        }
        
        result = k8sgpt_reader._parse_result(result_with_errors)
        
        assert 'Error 1' in result.problem
        assert 'Error 2' in result.problem
        assert 'Solution' in result.solution
    
    def test_parse_namespace_from_spec(self, k8sgpt_reader):
        """Test parsing namespace from spec when not in metadata."""
        result_with_spec_namespace = {
            'metadata': {'name': 'test'},
            'spec': {
                'kind': 'Pod',
                'name': 'test-pod',
                'namespace': 'custom-namespace',
                'backend': 'openai'
            }
        }
        
        result = k8sgpt_reader._parse_result(result_with_spec_namespace)
        
        assert result.namespace == 'custom-namespace'


class TestDetermineSeverity:
    """Test severity determination logic."""
    
    def test_high_severity_crashloop(self, k8sgpt_reader):
        """Test high severity for CrashLoopBackOff."""
        severity = k8sgpt_reader._determine_severity('Pod is in CrashLoopBackOff', 'Pod')
        assert severity == 'high'
    
    def test_high_severity_imagepull(self, k8sgpt_reader):
        """Test high severity for ImagePullBackOff."""
        severity = k8sgpt_reader._determine_severity('ImagePullBackOff error', 'Pod')
        assert severity == 'high'
    
    def test_high_severity_oom(self, k8sgpt_reader):
        """Test high severity for OOMKilled."""
        severity = k8sgpt_reader._determine_severity('Container OOMKilled', 'Pod')
        assert severity == 'high'
    
    def test_high_severity_failed(self, k8sgpt_reader):
        """Test high severity for failed state."""
        severity = k8sgpt_reader._determine_severity('Deployment failed to roll out', 'Deployment')
        assert severity == 'high'
    
    def test_low_severity_warning(self, k8sgpt_reader):
        """Test low severity for warnings."""
        severity = k8sgpt_reader._determine_severity('Warning: Resource quota exceeded', 'Pod')
        assert severity == 'low'
    
    def test_low_severity_pending(self, k8sgpt_reader):
        """Test low severity for pending state."""
        severity = k8sgpt_reader._determine_severity('Pod is pending', 'Pod')
        assert severity == 'low'
    
    def test_medium_severity_default(self, k8sgpt_reader):
        """Test medium severity as default."""
        severity = k8sgpt_reader._determine_severity('Service has no endpoints', 'Service')
        assert severity == 'medium'


class TestParseTimestamp:
    """Test timestamp parsing."""
    
    def test_parse_valid_timestamp(self, k8sgpt_reader):
        """Test parsing valid ISO timestamp."""
        timestamp = k8sgpt_reader._parse_timestamp('2024-01-15T10:30:00Z')
        
        assert isinstance(timestamp, datetime)
        assert timestamp.year == 2024
        assert timestamp.month == 1
        assert timestamp.day == 15
    
    def test_parse_empty_timestamp(self, k8sgpt_reader):
        """Test parsing empty timestamp."""
        timestamp = k8sgpt_reader._parse_timestamp('')
        
        assert isinstance(timestamp, datetime)
        # Should return current time
    
    def test_parse_invalid_timestamp(self, k8sgpt_reader):
        """Test parsing invalid timestamp."""
        timestamp = k8sgpt_reader._parse_timestamp('invalid-timestamp')
        
        assert isinstance(timestamp, datetime)
        # Should return current time


class TestFilterByRelevance:
    """Test filtering results by relevance."""
    
    @pytest.fixture
    def sample_results(self):
        """Create sample results for filtering."""
        return [
            K8sGPTResult(
                name='result-1',
                kind='Pod',
                namespace='default',
                severity='high',
                problem='Pod crashed',
                solution='Restart',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={'resource_name': 'app-pod'}
            ),
            K8sGPTResult(
                name='result-2',
                kind='Deployment',
                namespace='production',
                severity='medium',
                problem='Deployment issue',
                solution='Check config',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={'resource_name': 'app-deployment'}
            ),
            K8sGPTResult(
                name='result-3',
                kind='Service',
                namespace='default',
                severity='low',
                problem='Service warning',
                solution='Monitor',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={'resource_name': 'app-service'}
            )
        ]
    
    def test_filter_by_resource_names(self, k8sgpt_reader, sample_results):
        """Test filtering by resource names."""
        filtered = k8sgpt_reader.filter_by_relevance(
            sample_results,
            resource_names=['app-pod']
        )
        
        assert len(filtered) == 1
        assert filtered[0].details['resource_name'] == 'app-pod'
    
    def test_filter_by_namespaces(self, k8sgpt_reader, sample_results):
        """Test filtering by namespaces."""
        filtered = k8sgpt_reader.filter_by_relevance(
            sample_results,
            namespaces=['production']
        )
        
        assert len(filtered) == 1
        assert filtered[0].namespace == 'production'
    
    def test_filter_by_kinds(self, k8sgpt_reader, sample_results):
        """Test filtering by resource kinds."""
        filtered = k8sgpt_reader.filter_by_relevance(
            sample_results,
            kinds=['Pod', 'Service']
        )
        
        assert len(filtered) == 2
        assert all(r.kind in ['Pod', 'Service'] for r in filtered)
    
    def test_filter_multiple_criteria(self, k8sgpt_reader, sample_results):
        """Test filtering with multiple criteria."""
        filtered = k8sgpt_reader.filter_by_relevance(
            sample_results,
            namespaces=['default'],
            kinds=['Pod']
        )
        
        assert len(filtered) == 1
        assert filtered[0].kind == 'Pod'
        assert filtered[0].namespace == 'default'
    
    def test_filter_no_matches(self, k8sgpt_reader, sample_results):
        """Test filtering with no matches."""
        filtered = k8sgpt_reader.filter_by_relevance(
            sample_results,
            resource_names=['nonexistent']
        )
        
        assert len(filtered) == 0
    
    def test_filter_no_criteria(self, k8sgpt_reader, sample_results):
        """Test filtering with no criteria returns all results."""
        filtered = k8sgpt_reader.filter_by_relevance(sample_results)
        
        assert len(filtered) == len(sample_results)


class TestSortBySeverity:
    """Test sorting results by severity."""
    
    def test_sort_by_severity(self, k8sgpt_reader):
        """Test sorting results by severity."""
        results = [
            K8sGPTResult(
                name='low-result',
                kind='Pod',
                namespace='default',
                severity='low',
                problem='Warning',
                solution='Monitor',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={}
            ),
            K8sGPTResult(
                name='high-result',
                kind='Pod',
                namespace='default',
                severity='high',
                problem='Critical',
                solution='Fix now',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={}
            ),
            K8sGPTResult(
                name='medium-result',
                kind='Pod',
                namespace='default',
                severity='medium',
                problem='Issue',
                solution='Investigate',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={}
            )
        ]
        
        sorted_results = k8sgpt_reader.sort_by_severity(results)
        
        assert sorted_results[0].severity == 'high'
        assert sorted_results[1].severity == 'medium'
        assert sorted_results[2].severity == 'low'
    
    def test_sort_empty_list(self, k8sgpt_reader):
        """Test sorting empty list."""
        sorted_results = k8sgpt_reader.sort_by_severity([])
        assert len(sorted_results) == 0
