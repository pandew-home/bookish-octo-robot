"""
Unit tests for weather and results API endpoints.

Tests cover:
- Weather calculation endpoint
- Weather details endpoint
- Results listing with filtering
- Result detail retrieval with enrichment

Requirements: 3.2, 3.3, 3.4, 3.5, 12.2, 12.5
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.weather import router
from k8sgpt_reader import K8sGPTResult
from weather_calculator import WeatherState, ClusterToolInfo
from kubernetes.client.rest import ApiException


# Create a test FastAPI app
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)

client = TestClient(app)


@pytest.fixture
def mock_session_id():
    """Mock session ID."""
    return "test-session-123"


@pytest.fixture
def mock_cluster():
    """Mock cluster metadata."""
    return {
        'name': 'test-cluster',
        'version': '1.28',
        'endpoint': 'https://test-cluster.eks.amazonaws.com',
        'region': 'us-east-1',
        'status': 'ACTIVE'
    }


@pytest.fixture
def mock_k8s_clients():
    """Mock Kubernetes API clients."""
    return {
        'core_v1': Mock(),
        'apps_v1': Mock(),
        'custom_objects': Mock(),
        'networking_v1': Mock(),
        'rbac_v1': Mock()
    }


@pytest.fixture
def sample_k8sgpt_results():
    """Sample K8sGPT results for testing."""
    return [
        K8sGPTResult(
            name='pod-issue-1',
            kind='Pod',
            namespace='default',
            severity='high',
            problem='Pod is in CrashLoopBackOff state',
            solution='Check container logs and fix application error',
            analyzer='PodAnalyzer',
            timestamp=datetime.utcnow(),
            details={'resource_name': 'my-app-pod'}
        ),
        K8sGPTResult(
            name='deployment-issue-1',
            kind='Deployment',
            namespace='production',
            severity='medium',
            problem='Deployment has insufficient replicas',
            solution='Scale deployment to desired replicas',
            analyzer='DeploymentAnalyzer',
            timestamp=datetime.utcnow(),
            details={'resource_name': 'my-app-deployment'}
        ),
        K8sGPTResult(
            name='service-issue-1',
            kind='Service',
            namespace='default',
            severity='low',
            problem='Service has no endpoints',
            solution='Check pod selector labels',
            analyzer='ServiceAnalyzer',
            timestamp=datetime.utcnow(),
            details={'resource_name': 'my-service'}
        )
    ]


class TestWeatherEndpoint:
    """Tests for GET /api/weather endpoint."""
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_weather_with_results(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test weather endpoint with K8sGPT results."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        # Mock K8sGPT reader
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock node list
        mock_node = Mock()
        mock_node.metadata.name = 'node-1'
        mock_nodes = Mock()
        mock_nodes.items = [mock_node]
        mock_k8s_clients['core_v1'].list_node.return_value = mock_nodes
        
        # Mock pod list
        mock_pod = Mock()
        mock_pod.status.phase = 'Running'
        mock_pods = Mock()
        mock_pods.items = [mock_pod, mock_pod, mock_pod]
        mock_k8s_clients['core_v1'].list_pod_for_all_namespaces.return_value = mock_pods
        
        # Make request
        response = client.get(
            "/api/weather",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['cluster_name'] == 'test-cluster'
        assert data['cluster_version'] == '1.28'
        assert data['k8sgpt_result_count'] == 3
        assert data['weather_state'] in ['sunny', 'partly_cloudy', 'cloudy', 'rainy', 'stormy']
        assert 'top_issues' in data
        assert len(data['top_issues']) <= 5
        assert data['node_count'] == 1
        assert data['pod_summary']['total'] == 3
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_weather_no_k8sgpt_crd(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        mock_session_id
    ):
        """Test weather endpoint when K8sGPT CRD is not installed."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        # Mock K8sGPT reader to raise 404
        mock_reader = Mock()
        api_exception = ApiException(status=404)
        mock_reader.read_results = AsyncMock(side_effect=api_exception)
        mock_reader_class.return_value = mock_reader
        
        # Mock node list
        mock_nodes = Mock()
        mock_nodes.items = []
        mock_k8s_clients['core_v1'].list_node.return_value = mock_nodes
        
        # Mock pod list
        mock_pods = Mock()
        mock_pods.items = []
        mock_k8s_clients['core_v1'].list_pod_for_all_namespaces.return_value = mock_pods
        
        # Make request
        response = client.get(
            "/api/weather",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - should return sunny weather with 0 results
        assert response.status_code == 200
        data = response.json()
        
        assert data['k8sgpt_result_count'] == 0
        assert data['weather_state'] == 'sunny'
        assert len(data['top_issues']) == 0
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_weather_calculation_stormy(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        mock_session_id
    ):
        """Test weather calculation returns stormy state for critical issues."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        # Create multiple high severity results
        high_severity_results = [
            K8sGPTResult(
                name=f'critical-issue-{i}',
                kind='Pod',
                namespace='default',
                severity='high',
                problem=f'Critical issue {i}',
                solution='Fix immediately',
                analyzer='PodAnalyzer',
                timestamp=datetime.utcnow(),
                details={'resource_name': f'pod-{i}'}
            )
            for i in range(3)
        ]
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=high_severity_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock node and pod lists
        mock_k8s_clients['core_v1'].list_node.return_value = Mock(items=[])
        mock_k8s_clients['core_v1'].list_pod_for_all_namespaces.return_value = Mock(items=[])
        
        # Make request
        response = client.get(
            "/api/weather",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        # With 3 high severity issues, should be stormy
        assert data['weather_state'] == 'stormy'
        assert data['k8sgpt_result_count'] == 3


class TestWeatherDetailsEndpoint:
    """Tests for GET /api/weather/details endpoint."""
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_weather_details_with_metadata(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test weather details endpoint includes all results and metadata."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock node list with conditions
        mock_node = Mock()
        mock_node.metadata.name = 'node-1'
        mock_node.status.node_info.kubelet_version = 'v1.28.0'
        mock_condition = Mock()
        mock_condition.type = 'Ready'
        mock_condition.status = 'True'
        mock_node.status.conditions = [mock_condition]
        mock_nodes = Mock()
        mock_nodes.items = [mock_node]
        mock_k8s_clients['core_v1'].list_node.return_value = mock_nodes
        
        # Mock namespace list
        mock_namespaces = Mock()
        mock_namespaces.items = [Mock(), Mock(), Mock()]
        mock_k8s_clients['core_v1'].list_namespace.return_value = mock_namespaces
        
        # Make request
        response = client.get(
            "/api/weather/details",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['cluster_name'] == 'test-cluster'
        assert data['k8sgpt_result_count'] == 3
        assert len(data['all_results']) == 3
        
        # Check cluster metadata
        assert 'cluster_metadata' in data
        metadata = data['cluster_metadata']
        assert metadata['name'] == 'test-cluster'
        assert metadata['version'] == '1.28'
        assert metadata['node_count'] == 1
        assert metadata['namespace_count'] == 3
        assert len(metadata['nodes']) == 1
        assert metadata['nodes'][0]['name'] == 'node-1'
        assert metadata['nodes'][0]['status'] == 'Ready'


class TestResultsListEndpoint:
    """Tests for GET /api/results endpoint."""
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_list_results_no_filter(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test listing all results without filters."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader.sort_by_severity.return_value = sample_k8sgpt_results
        mock_reader_class.return_value = mock_reader
        
        # Make request
        response = client.get(
            "/api/results",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 3
        assert len(data['results']) == 3
        assert data['filters_applied']['severity'] is None
        assert data['filters_applied']['namespace'] is None
        assert data['filters_applied']['kind'] is None
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_list_results_with_severity_filter(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test listing results filtered by severity."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        # Filter to only high severity
        high_severity_results = [r for r in sample_k8sgpt_results if r.severity == 'high']
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=high_severity_results)
        mock_reader.sort_by_severity.return_value = high_severity_results
        mock_reader_class.return_value = mock_reader
        
        # Make request with severity filter
        response = client.get(
            "/api/results?severity=high",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 1
        assert data['filters_applied']['severity'] == 'high'
        assert all(r['severity'] == 'high' for r in data['results'])
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_list_results_with_namespace_filter(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test listing results filtered by namespace."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        # Filter to only default namespace
        default_ns_results = [r for r in sample_k8sgpt_results if r.namespace == 'default']
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=default_ns_results)
        mock_reader.sort_by_severity.return_value = default_ns_results
        mock_reader_class.return_value = mock_reader
        
        # Make request with namespace filter
        response = client.get(
            "/api/results?namespace=default",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 2
        assert data['filters_applied']['namespace'] == 'default'
        assert all(r['namespace'] == 'default' for r in data['results'])
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_list_results_with_kind_filter(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test listing results filtered by resource kind."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        # Filter to only Pod results (kind filter is applied in endpoint)
        pod_results = [r for r in sample_k8sgpt_results if r.kind == 'Pod']
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        # sort_by_severity should return the filtered results
        mock_reader.sort_by_severity.return_value = pod_results
        mock_reader_class.return_value = mock_reader
        
        # Make request with kind filter
        response = client.get(
            "/api/results?kind=Pod",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        # Should filter to only Pod results
        assert data['count'] == 1
        assert data['filters_applied']['kind'] == 'Pod'
        assert all(r['kind'] == 'Pod' for r in data['results'])


class TestResultDetailEndpoint:
    """Tests for GET /api/results/{id} endpoint."""
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_get_result_detail(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test getting detail for a specific result."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock pod read for enrichment
        mock_pod = Mock()
        mock_pod.status.phase = 'Running'
        mock_pod.status.conditions = []
        mock_pod.status.container_statuses = []
        mock_k8s_clients['core_v1'].read_namespaced_pod.return_value = mock_pod
        
        # Mock events
        mock_events = Mock()
        mock_events.items = []
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = mock_events
        
        # Make request
        result_id = 'pod-issue-1'
        response = client.get(
            f"/api/results/{result_id}",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert 'result' in data
        assert data['result']['name'] == result_id
        assert data['result']['kind'] == 'Pod'
        assert data['result']['severity'] == 'high'
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_get_result_detail_with_enrichment(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test getting result detail includes enrichment data."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock pod read with detailed status
        mock_pod = Mock()
        mock_pod.status.phase = 'CrashLoopBackOff'
        
        mock_condition = Mock()
        mock_condition.type = 'Ready'
        mock_condition.status = 'False'
        mock_condition.reason = 'ContainersNotReady'
        mock_condition.message = 'containers with unready status: [app]'
        mock_pod.status.conditions = [mock_condition]
        
        mock_container_status = Mock()
        mock_container_status.name = 'app'
        mock_container_status.ready = False
        mock_container_status.restart_count = 5
        mock_container_status.state = 'waiting'
        mock_pod.status.container_statuses = [mock_container_status]
        
        mock_k8s_clients['core_v1'].read_namespaced_pod.return_value = mock_pod
        
        # Mock events
        mock_event = Mock()
        mock_event.type = 'Warning'
        mock_event.reason = 'BackOff'
        mock_event.message = 'Back-off restarting failed container'
        mock_event.last_timestamp = datetime.utcnow()
        mock_events = Mock()
        mock_events.items = [mock_event]
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = mock_events
        
        # Make request
        result_id = 'pod-issue-1'
        response = client.get(
            f"/api/results/{result_id}",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert 'enrichment' in data
        assert data['enrichment'] is not None
        
        # Check pod status enrichment
        if 'pod_status' in data['enrichment']:
            pod_status = data['enrichment']['pod_status']
            assert pod_status['phase'] == 'CrashLoopBackOff'
            assert len(pod_status['conditions']) > 0
            assert len(pod_status['container_statuses']) > 0
        
        # Check events enrichment
        if 'recent_events' in data['enrichment']:
            events = data['enrichment']['recent_events']
            assert len(events) > 0
            assert events[0]['type'] == 'Warning'
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_get_result_detail_not_found(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test getting detail for non-existent result returns 404."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Make request for non-existent result
        result_id = 'non-existent-result'
        response = client.get(
            f"/api/results/{result_id}",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 404
        assert 'not found' in response.json()['detail'].lower()


class TestMetadataInclusion:
    """Tests for metadata inclusion in responses."""
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_weather_includes_cluster_metadata(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test weather response includes cluster metadata."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock K8s API calls
        mock_k8s_clients['core_v1'].list_node.return_value = Mock(items=[Mock()])
        mock_k8s_clients['core_v1'].list_pod_for_all_namespaces.return_value = Mock(items=[])
        
        # Make request
        response = client.get(
            "/api/weather",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        # Check required metadata fields
        assert 'cluster_name' in data
        assert 'cluster_version' in data
        assert 'k8sgpt_result_count' in data
        assert 'timestamp' in data
        assert 'node_count' in data
        assert 'pod_summary' in data
        
        # Verify values
        assert data['cluster_name'] == 'test-cluster'
        assert data['cluster_version'] == '1.28'
        assert data['k8sgpt_result_count'] == 3
    
    @patch('api.weather.get_selected_cluster')
    @patch('api.weather.get_k8s_clients_for_session')
    @patch('api.weather.K8sGPTReader')
    async def test_result_includes_analyzer_metadata(
        self,
        mock_reader_class,
        mock_get_clients,
        mock_get_cluster,
        mock_cluster,
        mock_k8s_clients,
        sample_k8sgpt_results,
        mock_session_id
    ):
        """Test result detail includes analyzer metadata."""
        # Setup mocks
        mock_get_cluster.return_value = mock_cluster
        mock_get_clients.return_value = mock_k8s_clients
        
        mock_reader = Mock()
        mock_reader.read_results = AsyncMock(return_value=sample_k8sgpt_results)
        mock_reader_class.return_value = mock_reader
        
        # Mock K8s API calls
        mock_k8s_clients['core_v1'].read_namespaced_pod.return_value = Mock(
            status=Mock(phase='Running', conditions=[], container_statuses=[])
        )
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = Mock(items=[])
        
        # Make request
        result_id = 'pod-issue-1'
        response = client.get(
            f"/api/results/{result_id}",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        result = data['result']
        
        # Check required metadata fields (Requirements 12.5)
        assert 'analyzer' in result
        assert 'severity' in result
        assert 'timestamp' in result
        
        # Verify values
        assert result['analyzer'] == 'PodAnalyzer'
        assert result['severity'] == 'high'
        assert result['timestamp'] is not None
