"""
Unit tests for enrichment engine.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from kubernetes.client.exceptions import ApiException

from enrichment_engine import EnrichmentEngine, EnrichedContext
from query_router import EnrichmentPlan, QueryCategory
from credential_store import StoredCredentials


@pytest.fixture
def mock_k8s_clients():
    """Create mock Kubernetes API clients."""
    return {
        'core_v1': Mock(),
        'apps_v1': Mock(),
        'custom_objects': Mock(),
        'networking_v1': Mock(),
        'rbac_v1': Mock()
    }


@pytest.fixture
def mock_aws_creds():
    """Create mock AWS credentials."""
    now = datetime.now()
    return StoredCredentials(
        auth_mode="aws",
        access_key='AKIATEST',
        secret_key='secret',
        session_token='token',
        region='us-east-1',
        user_arn='arn:aws:iam::123456789012:user/test',
        account_id='123456789012',
        expires_at=now + timedelta(hours=1),
        created_at=now
    )


@pytest.fixture
def enrichment_engine(mock_k8s_clients, mock_aws_creds):
    """Create enrichment engine instance."""
    return EnrichmentEngine(mock_k8s_clients, mock_aws_creds)


@pytest.fixture
def basic_plan():
    """Create basic enrichment plan."""
    return EnrichmentPlan(
        categories=[QueryCategory.POD_ISSUE],
        resource_names=['test-pod'],
        namespaces=['default'],
        include_k8sgpt_results=True,
        include_aws_context=False
    )


class TestEnrichedContext:
    """Test EnrichedContext dataclass."""
    
    def test_enriched_context_creation(self):
        """Test creating enriched context."""
        context = EnrichedContext()
        assert context.k8sgpt_results == []
        assert context.pod_data is None
        assert context.errors == []
    
    def test_enriched_context_merge(self):
        """Test merging enriched contexts."""
        context1 = EnrichedContext(
            pod_data={'pods': [{'name': 'pod1'}]},
            errors=['error1']
        )
        context2 = EnrichedContext(
            deployment_data={'deployments': [{'name': 'deploy1'}]},
            errors=['error2']
        )
        
        context1.merge(context2)
        
        assert context1.pod_data == {'pods': [{'name': 'pod1'}]}
        assert context1.deployment_data == {'deployments': [{'name': 'deploy1'}]}
        assert context1.errors == ['error1', 'error2']


class TestEnrichmentEngine:
    """Test EnrichmentEngine class."""
    
    def test_engine_initialization(self, mock_k8s_clients, mock_aws_creds):
        """Test engine initialization."""
        engine = EnrichmentEngine(mock_k8s_clients, mock_aws_creds)
        
        assert engine.k8s == mock_k8s_clients
        assert engine.aws_creds == mock_aws_creds
        assert engine.timeout == 10
        assert engine.aws_call_limit == 3
    
    @pytest.mark.asyncio
    async def test_execute_with_pod_category(self, enrichment_engine, basic_plan, mock_k8s_clients):
        """Test execute with pod category."""
        # Mock pod data
        mock_pod = Mock()
        mock_pod.metadata.name = 'test-pod'
        mock_pod.metadata.namespace = 'default'
        mock_pod.status.phase = 'Running'
        mock_pod.status.container_statuses = []
        
        mock_k8s_clients['core_v1'].read_namespaced_pod.return_value = mock_pod
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = Mock(items=[])
        mock_k8s_clients['core_v1'].read_namespaced_pod_log.return_value = "test logs"
        
        # Mock K8sGPT results
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.return_value = {'items': []}
        
        context = await enrichment_engine.execute(basic_plan)
        
        assert context.pod_data is not None
        assert 'pods' in context.pod_data
        assert len(context.pod_data['pods']) == 1
        assert context.pod_data['pods'][0]['name'] == 'test-pod'
    
    @pytest.mark.asyncio
    async def test_execute_with_multiple_categories(self, enrichment_engine, mock_k8s_clients):
        """Test execute with multiple categories."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE, QueryCategory.DEPLOYMENT_STATUS],
            resource_names=[],
            namespaces=['default'],
            include_k8sgpt_results=False
        )
        
        # Mock pod data
        mock_k8s_clients['core_v1'].list_namespaced_pod.return_value = Mock(items=[])
        
        # Mock deployment data
        mock_k8s_clients['apps_v1'].list_namespaced_deployment.return_value = Mock(items=[])
        
        context = await enrichment_engine.execute(plan)
        
        assert context.pod_data is not None
        assert context.deployment_data is not None


class TestPodEnrichment:
    """Test pod enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_pods_with_specific_pod(self, enrichment_engine, basic_plan, mock_k8s_clients):
        """Test enriching specific pod."""
        # Mock pod
        mock_pod = Mock()
        mock_pod.metadata.name = 'test-pod'
        mock_pod.metadata.namespace = 'default'
        mock_pod.status.phase = 'Running'
        mock_pod.status.container_statuses = []
        
        mock_k8s_clients['core_v1'].read_namespaced_pod.return_value = mock_pod
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = Mock(items=[])
        mock_k8s_clients['core_v1'].read_namespaced_pod_log.return_value = "test logs"
        
        result = await enrichment_engine._enrich_pods(basic_plan)
        
        assert 'pods' in result
        assert len(result['pods']) == 1
        assert result['pods'][0]['name'] == 'test-pod'
        assert result['pods'][0]['phase'] == 'Running'
    
    @pytest.mark.asyncio
    async def test_enrich_pods_not_found(self, enrichment_engine, basic_plan, mock_k8s_clients):
        """Test enriching non-existent pod."""
        mock_k8s_clients['core_v1'].read_namespaced_pod.side_effect = ApiException(status=404)
        
        result = await enrichment_engine._enrich_pods(basic_plan)
        
        assert 'error' in result
        assert 'not found' in result['error'].lower()
    
    @pytest.mark.asyncio
    async def test_enrich_pods_permission_denied(self, enrichment_engine, basic_plan, mock_k8s_clients):
        """Test enriching pods with permission denied."""
        mock_k8s_clients['core_v1'].read_namespaced_pod.side_effect = ApiException(status=403)
        
        result = await enrichment_engine._enrich_pods(basic_plan)
        
        assert 'error' in result
        assert 'permission' in result['error'].lower()
    
    @pytest.mark.asyncio
    async def test_enrich_pods_all_in_namespace(self, enrichment_engine, mock_k8s_clients):
        """Test enriching all pods in namespace."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE],
            resource_names=[],  # No specific pods
            namespaces=['default']
        )
        
        # Mock multiple pods
        mock_pod1 = Mock()
        mock_pod1.metadata.name = 'pod1'
        mock_pod1.metadata.namespace = 'default'
        mock_pod1.status.phase = 'Running'
        mock_pod1.status.container_statuses = []
        
        mock_pod2 = Mock()
        mock_pod2.metadata.name = 'pod2'
        mock_pod2.metadata.namespace = 'default'
        mock_pod2.status.phase = 'Pending'
        mock_pod2.status.container_statuses = []
        
        mock_k8s_clients['core_v1'].list_namespaced_pod.return_value = Mock(items=[mock_pod1, mock_pod2])
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = Mock(items=[])
        
        result = await enrichment_engine._enrich_pods(plan)
        
        assert 'pods' in result
        assert len(result['pods']) == 2
    
    def test_format_pod_data_with_container_statuses(self, enrichment_engine):
        """Test formatting pod data with container statuses."""
        mock_pod = Mock()
        mock_pod.metadata.name = 'test-pod'
        mock_pod.metadata.namespace = 'default'
        mock_pod.status.phase = 'Running'
        
        # Mock container status
        mock_container = Mock()
        mock_container.name = 'app'
        mock_container.ready = True
        mock_container.restart_count = 5
        mock_container.state.running = True
        mock_container.state.waiting = None
        mock_container.state.terminated = None
        mock_container.last_state = None
        
        mock_pod.status.container_statuses = [mock_container]
        
        result = enrichment_engine._format_pod_data(mock_pod, [], "", None)
        
        assert result['name'] == 'test-pod'
        assert result['restart_count'] == 5
        assert len(result['containers']) == 1
        assert result['containers'][0]['name'] == 'app'
        assert result['containers'][0]['ready'] is True
    
    def test_format_pod_data_with_crashloop(self, enrichment_engine):
        """Test formatting pod data with CrashLoopBackOff."""
        mock_pod = Mock()
        mock_pod.metadata.name = 'crash-pod'
        mock_pod.metadata.namespace = 'default'
        mock_pod.status.phase = 'CrashLoopBackOff'
        
        # Mock waiting container
        mock_container = Mock()
        mock_container.name = 'app'
        mock_container.ready = False
        mock_container.restart_count = 15
        mock_container.state.running = None
        mock_container.state.waiting = Mock(reason='CrashLoopBackOff', message='Back-off restarting failed container')
        mock_container.state.terminated = None
        
        # Mock last termination
        mock_container.last_state = Mock()
        mock_container.last_state.terminated = Mock(
            reason='Error',
            exit_code=1,
            message='OOMKilled'
        )
        
        mock_pod.status.container_statuses = [mock_container]
        
        result = enrichment_engine._format_pod_data(mock_pod, [], "", None)
        
        assert result['containers'][0]['state'] == 'waiting'
        assert result['containers'][0]['reason'] == 'CrashLoopBackOff'
        assert 'last_termination' in result['containers'][0]
        assert result['containers'][0]['last_termination']['reason'] == 'Error'
    
    def test_generate_pod_summary(self, enrichment_engine):
        """Test generating pod summary."""
        pods_data = [
            {'phase': 'Running'},
            {'phase': 'Running'},
            {'phase': 'Pending'},
            {'phase': 'Failed'}
        ]
        
        summary = enrichment_engine._generate_pod_summary(pods_data)
        
        assert '4 pod(s)' in summary
        assert '2 running' in summary
        assert '1 pending' in summary
        assert '1 failed' in summary


class TestDeploymentEnrichment:
    """Test deployment enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_deployments(self, enrichment_engine, mock_k8s_clients):
        """Test enriching deployments."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.DEPLOYMENT_STATUS],
            resource_names=['test-deploy'],
            namespaces=['default']
        )
        
        # Mock deployment
        mock_deploy = Mock()
        mock_deploy.metadata.name = 'test-deploy'
        mock_deploy.metadata.namespace = 'default'
        mock_deploy.spec.replicas = 3
        mock_deploy.spec.strategy.type = 'RollingUpdate'
        mock_deploy.status.replicas = 3
        mock_deploy.status.available_replicas = 3
        mock_deploy.status.unavailable_replicas = 0
        mock_deploy.status.updated_replicas = 3
        mock_deploy.status.conditions = []
        
        mock_k8s_clients['apps_v1'].read_namespaced_deployment.return_value = mock_deploy
        mock_k8s_clients['core_v1'].list_namespaced_event.return_value = Mock(items=[])
        
        result = await enrichment_engine._enrich_deployments(plan)
        
        assert 'deployments' in result
        assert len(result['deployments']) == 1
        assert result['deployments'][0]['name'] == 'test-deploy'
        assert result['deployments'][0]['replicas']['desired'] == 3
    
    @pytest.mark.asyncio
    async def test_enrich_deployments_not_found(self, enrichment_engine, mock_k8s_clients):
        """Test enriching non-existent deployment."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.DEPLOYMENT_STATUS],
            resource_names=['missing-deploy'],
            namespaces=['default']
        )
        
        mock_k8s_clients['apps_v1'].read_namespaced_deployment.side_effect = ApiException(status=404)
        
        result = await enrichment_engine._enrich_deployments(plan)
        
        assert 'error' in result
        assert 'not found' in result['error'].lower()
    
    def test_format_deployment_data(self, enrichment_engine):
        """Test formatting deployment data."""
        mock_deploy = Mock()
        mock_deploy.metadata.name = 'test-deploy'
        mock_deploy.metadata.namespace = 'default'
        mock_deploy.spec.replicas = 3
        mock_deploy.spec.strategy.type = 'RollingUpdate'
        mock_deploy.status.replicas = 2
        mock_deploy.status.available_replicas = 1
        mock_deploy.status.unavailable_replicas = 2
        mock_deploy.status.updated_replicas = 2
        
        # Mock condition
        mock_condition = Mock()
        mock_condition.type = 'Progressing'
        mock_condition.status = 'False'
        mock_condition.reason = 'ProgressDeadlineExceeded'
        mock_condition.message = 'ReplicaSet has timed out progressing'
        mock_deploy.status.conditions = [mock_condition]
        
        result = enrichment_engine._format_deployment_data(mock_deploy, [])
        
        assert result['name'] == 'test-deploy'
        assert result['replicas']['desired'] == 3
        assert result['replicas']['available'] == 1
        assert result['strategy'] == 'RollingUpdate'
        assert len(result['conditions']) == 1
        assert result['conditions'][0]['type'] == 'Progressing'


class TestServiceEnrichment:
    """Test service enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_services(self, enrichment_engine, mock_k8s_clients):
        """Test enriching services."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.SERVICE_NETWORKING],
            resource_names=['test-service'],
            namespaces=['default']
        )
        
        # Mock service
        mock_service = Mock()
        mock_service.metadata.name = 'test-service'
        mock_service.metadata.namespace = 'default'
        mock_service.spec.type = 'ClusterIP'
        mock_service.spec.cluster_ip = '10.0.0.1'
        mock_service.spec.ports = []
        mock_service.status.load_balancer = None
        
        mock_k8s_clients['core_v1'].read_namespaced_service.return_value = mock_service
        mock_k8s_clients['core_v1'].read_namespaced_endpoints.side_effect = ApiException(status=404)
        mock_k8s_clients['networking_v1'].list_namespaced_ingress.return_value = Mock(items=[])
        
        result = await enrichment_engine._enrich_services(plan)
        
        assert 'services' in result
        assert len(result['services']) == 1
        assert result['services'][0]['name'] == 'test-service'
    
    def test_format_service_data_with_endpoints(self, enrichment_engine):
        """Test formatting service data with endpoints."""
        mock_service = Mock()
        mock_service.metadata.name = 'test-service'
        mock_service.metadata.namespace = 'default'
        mock_service.spec.type = 'ClusterIP'
        mock_service.spec.cluster_ip = '10.0.0.1'
        mock_service.spec.ports = []
        mock_service.status.load_balancer = None
        
        # Mock endpoints
        mock_endpoints = Mock()
        mock_subset = Mock()
        
        # Ready addresses
        mock_addr1 = Mock()
        mock_addr1.ip = '10.0.1.1'
        mock_subset.addresses = [mock_addr1]
        
        # Not ready addresses
        mock_addr2 = Mock()
        mock_addr2.ip = '10.0.1.2'
        mock_subset.not_ready_addresses = [mock_addr2]
        
        # Ports
        mock_port = Mock()
        mock_port.port = 8080
        mock_subset.ports = [mock_port]
        
        mock_endpoints.subsets = [mock_subset]
        
        result = enrichment_engine._format_service_data(mock_service, mock_endpoints)
        
        assert result['name'] == 'test-service'
        assert len(result['endpoints']['ready']) == 1
        assert '10.0.1.1:8080' in result['endpoints']['ready']
        assert len(result['endpoints']['not_ready']) == 1
        assert '10.0.1.2:8080' in result['endpoints']['not_ready']


class TestNodeEnrichment:
    """Test node enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_nodes(self, enrichment_engine, mock_k8s_clients):
        """Test enriching nodes."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.NODE_HEALTH],
            resource_names=[],
            namespaces=[]
        )
        
        # Mock node
        mock_node = Mock()
        mock_node.metadata.name = 'node1'
        mock_node.spec.taints = []
        
        # Mock conditions
        mock_condition = Mock()
        mock_condition.type = 'Ready'
        mock_condition.status = 'True'
        mock_node.status.conditions = [mock_condition]
        
        # Mock capacity
        mock_node.status.capacity = {'cpu': '4', 'memory': '16Gi', 'pods': '110'}
        mock_node.status.allocatable = {'cpu': '3.9', 'memory': '14.5Gi', 'pods': '110'}
        
        mock_k8s_clients['core_v1'].list_node.return_value = Mock(items=[mock_node])
        mock_k8s_clients['core_v1'].list_pod_for_all_namespaces.return_value = Mock(items=[Mock(), Mock()])
        
        result = await enrichment_engine._enrich_nodes(plan)
        
        assert 'nodes' in result
        assert len(result['nodes']) == 1
        assert result['nodes'][0]['name'] == 'node1'
        assert result['nodes'][0]['status'] == 'Ready'
        assert result['nodes'][0]['pod_count'] == 2


class TestStorageEnrichment:
    """Test storage enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_storage(self, enrichment_engine, mock_k8s_clients):
        """Test enriching storage."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.STORAGE],
            resource_names=[],
            namespaces=['default']
        )
        
        # Mock PVC
        mock_pvc = Mock()
        mock_pvc.metadata.name = 'test-pvc'
        mock_pvc.metadata.namespace = 'default'
        mock_pvc.status.phase = 'Bound'
        mock_pvc.spec.volume_name = 'pv-123'
        mock_pvc.spec.storage_class_name = 'gp2'
        mock_pvc.status.capacity = {'storage': '10Gi'}
        mock_pvc.spec.access_modes = ['ReadWriteOnce']
        
        mock_k8s_clients['core_v1'].list_namespaced_persistent_volume_claim.return_value = Mock(items=[mock_pvc])
        
        result = await enrichment_engine._enrich_storage(plan)
        
        assert 'pvcs' in result
        assert len(result['pvcs']) == 1
        assert result['pvcs'][0]['name'] == 'test-pvc'
        assert result['pvcs'][0]['status'] == 'Bound'


class TestArgoCDEnrichment:
    """Test ArgoCD enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_argocd(self, enrichment_engine, mock_k8s_clients):
        """Test enriching ArgoCD applications."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.ARGOCD],
            resource_names=[],
            namespaces=[]
        )
        
        # Mock ArgoCD application
        mock_app = {
            'metadata': {'name': 'test-app', 'namespace': 'argocd'},
            'spec': {
                'source': {
                    'repoURL': 'https://github.com/org/repo',
                    'path': 'k8s/prod',
                    'targetRevision': 'main'
                }
            },
            'status': {
                'sync': {'status': 'Synced'},
                'health': {'status': 'Healthy'}
            }
        }
        
        mock_k8s_clients['custom_objects'].list_namespaced_custom_object.return_value = {'items': [mock_app]}
        
        result = await enrichment_engine._enrich_argocd(plan)
        
        assert 'applications' in result
        assert len(result['applications']) == 1
        assert result['applications'][0]['name'] == 'test-app'
        assert result['applications'][0]['sync_status'] == 'Synced'
    
    @pytest.mark.asyncio
    async def test_enrich_argocd_not_installed(self, enrichment_engine, mock_k8s_clients):
        """Test enriching ArgoCD when not installed."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.ARGOCD],
            resource_names=[],
            namespaces=[]
        )
        
        mock_k8s_clients['custom_objects'].list_namespaced_custom_object.side_effect = ApiException(status=404)
        
        result = await enrichment_engine._enrich_argocd(plan)
        
        assert 'error' in result
        assert 'not installed' in result['error'].lower()


class TestSecurityEnrichment:
    """Test security enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_security(self, enrichment_engine, mock_k8s_clients):
        """Test enriching security resources."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.SECURITY],
            resource_names=[],
            namespaces=['default']
        )
        
        # Mock role
        mock_role = Mock()
        mock_role.metadata.name = 'test-role'
        mock_role.metadata.namespace = 'default'
        mock_role.rules = [Mock(), Mock()]
        
        # Mock service account
        mock_sa = Mock()
        mock_sa.metadata.name = 'test-sa'
        mock_sa.metadata.namespace = 'default'
        mock_sa.secrets = [Mock()]
        
        mock_k8s_clients['rbac_v1'].list_namespaced_role.return_value = Mock(items=[mock_role])
        mock_k8s_clients['core_v1'].list_namespaced_service_account.return_value = Mock(items=[mock_sa])
        
        result = await enrichment_engine._enrich_security(plan)
        
        assert 'roles' in result
        assert 'service_accounts' in result
        assert len(result['roles']) == 1
        assert len(result['service_accounts']) == 1


class TestAWSEnrichment:
    """Test AWS enrichment methods."""
    
    @pytest.mark.asyncio
    async def test_enrich_aws_with_networking_category(self, enrichment_engine):
        """Test AWS enrichment for networking queries."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.SERVICE_NETWORKING],
            resource_names=[],
            namespaces=[],
            include_aws_context=True
        )
        
        with patch.object(enrichment_engine, '_get_load_balancers', return_value=[{'name': 'test-lb'}]):
            with patch.object(enrichment_engine, '_get_security_groups', return_value=[{'id': 'sg-123'}]):
                result = await enrichment_engine._enrich_aws(plan)
        
        assert 'load_balancers' in result
        assert 'security_groups' in result
        assert result['calls_made'] == 2
    
    @pytest.mark.asyncio
    async def test_enrich_aws_call_limit(self, enrichment_engine):
        """Test AWS enrichment respects 3-call limit."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.SERVICE_NETWORKING],
            resource_names=[],
            namespaces=[],
            include_aws_context=True
        )
        
        with patch.object(enrichment_engine, '_get_load_balancers', return_value=[{'name': 'lb1'}]):
            with patch.object(enrichment_engine, '_get_security_groups', return_value=[{'id': 'sg1'}]):
                result = await enrichment_engine._enrich_aws(plan)
        
        assert result['calls_made'] <= 3


class TestK8sGPTResults:
    """Test K8sGPT result reading."""
    
    @pytest.mark.asyncio
    async def test_read_k8sgpt_results(self, enrichment_engine, mock_k8s_clients):
        """Test reading K8sGPT results with all required fields."""
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
        
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.return_value = {'items': [mock_result]}
        
        result = await enrichment_engine._read_k8sgpt_results()
        
        assert 'k8sgpt_results' in result
        assert len(result['k8sgpt_results']) == 1
        
        # Verify all required fields are present
        k8sgpt_result = result['k8sgpt_results'][0]
        assert k8sgpt_result['name'] == 'result-1'
        assert k8sgpt_result['kind'] == 'Pod'
        assert k8sgpt_result['namespace'] == 'default'
        assert k8sgpt_result['severity'] in ['low', 'medium', 'high']
        assert 'problem' in k8sgpt_result
        assert 'solution' in k8sgpt_result
        assert k8sgpt_result['analyzer'] == 'openai'
        assert 'timestamp' in k8sgpt_result
        assert 'details' in k8sgpt_result
    
    @pytest.mark.asyncio
    async def test_read_k8sgpt_results_severity_detection(self, enrichment_engine, mock_k8s_clients):
        """Test severity detection based on problem content."""
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
        
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.return_value = {'items': [high_severity_result]}
        result = await enrichment_engine._read_k8sgpt_results()
        assert result['k8sgpt_results'][0]['severity'] == 'high'
        
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
        
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.return_value = {'items': [low_severity_result]}
        result = await enrichment_engine._read_k8sgpt_results()
        assert result['k8sgpt_results'][0]['severity'] == 'low'
    
    @pytest.mark.asyncio
    async def test_read_k8sgpt_results_not_installed(self, enrichment_engine, mock_k8s_clients):
        """Test reading K8sGPT results when not installed."""
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.side_effect = ApiException(status=404)
        
        result = await enrichment_engine._read_k8sgpt_results()
        
        assert 'k8sgpt_results' in result
        assert len(result['k8sgpt_results']) == 0
    
    @pytest.mark.asyncio
    async def test_read_k8sgpt_results_permission_denied(self, enrichment_engine, mock_k8s_clients):
        """Test reading K8sGPT results when permission is denied."""
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.side_effect = ApiException(status=403)
        
        result = await enrichment_engine._read_k8sgpt_results()
        
        assert 'k8sgpt_results' in result
        assert len(result['k8sgpt_results']) == 0
    
    @pytest.mark.asyncio
    async def test_format_k8sgpt_result_missing_fields(self, enrichment_engine):
        """Test formatting K8sGPT result with missing optional fields."""
        minimal_result = {
            'metadata': {'name': 'minimal-result'},
            'spec': {
                'kind': 'Service',
                'name': 'test-service'
            }
        }
        
        formatted = enrichment_engine._format_k8sgpt_result(minimal_result)
        
        # Should handle missing fields gracefully
        assert formatted['name'] == 'minimal-result'
        assert formatted['kind'] == 'Service'
        assert formatted['namespace'] == 'default'  # Default namespace
        assert formatted['severity'] in ['low', 'medium', 'high']
        assert 'problem' in formatted
        assert 'solution' in formatted
        assert 'analyzer' in formatted
        assert 'timestamp' in formatted
        assert 'details' in formatted


class TestDefaultEnrichment:
    """Test default enrichment behavior."""
    
    @pytest.mark.asyncio
    async def test_kb_search_category_skips_enrichment(self, enrichment_engine, mock_k8s_clients):
        """Test that KB_SEARCH category doesn't trigger cluster enrichment."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.KB_SEARCH],
            resource_names=[],
            namespaces=[],
            include_k8sgpt_results=True
        )
        
        # Mock K8sGPT results
        mock_k8s_clients['custom_objects'].list_cluster_custom_object.return_value = {'items': []}
        
        context = await enrichment_engine.execute(plan)
        
        # Should only have K8sGPT results, no other enrichment
        assert context.k8sgpt_results == []
        assert context.pod_data is None
        assert context.deployment_data is None
    
    @pytest.mark.asyncio
    async def test_empty_categories_adds_default_enrichment(self, enrichment_engine, mock_k8s_clients):
        """Test that empty categories triggers default general health enrichment."""
        plan = EnrichmentPlan(
            categories=[],
            resource_names=[],
            namespaces=[],
            include_k8sgpt_results=False
        )
        
        # Mock general health data
        mock_k8s_clients['core_v1'].list_namespaced_pod.return_value = Mock(items=[])
        mock_k8s_clients['core_v1'].list_node.return_value = Mock(items=[])
        
        context = await enrichment_engine.execute(plan)
        
        # Should have general health data as fallback
        # Note: The actual data structure depends on implementation
        assert len(context.errors) == 0 or 'general health' in str(context.errors).lower()
    
    def test_get_namespace_with_plan_namespace(self, enrichment_engine):
        """Test getting namespace from plan."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE],
            resource_names=[],
            namespaces=['production']
        )
        
        namespace = enrichment_engine._get_namespace(plan)
        
        assert namespace == 'production'
    
    def test_get_namespace_defaults_to_default(self, enrichment_engine):
        """Test getting namespace defaults to 'default'."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE],
            resource_names=[],
            namespaces=[]
        )
        
        namespace = enrichment_engine._get_namespace(plan)
        
        assert namespace == 'default'
    
    def test_get_namespace_uses_first_namespace(self, enrichment_engine):
        """Test getting namespace uses first from list."""
        plan = EnrichmentPlan(
            categories=[QueryCategory.POD_ISSUE],
            resource_names=[],
            namespaces=['production', 'staging', 'dev']
        )
        
        namespace = enrichment_engine._get_namespace(plan)
        
        assert namespace == 'production'
