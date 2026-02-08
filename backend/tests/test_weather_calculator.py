"""
Unit tests for Weather Calculator.

Tests cover:
- Weather state calculation
- Severity counting
- Top issues selection
- Error handling
"""

import pytest
from datetime import datetime

from weather_calculator import (
    WeatherCalculator,
    WeatherState,
    K8sGPTResultSummary,
    ClusterToolInfo,
    WeatherResponse
)
from k8sgpt_reader import K8sGPTResult


@pytest.fixture
def weather_calculator():
    """Create WeatherCalculator instance."""
    return WeatherCalculator()


@pytest.fixture
def sample_high_severity_result():
    """Create high severity result."""
    return K8sGPTResult(
        name='high-result',
        kind='Pod',
        namespace='default',
        severity='high',
        problem='Pod is in CrashLoopBackOff',
        solution='Check logs',
        analyzer='openai',
        timestamp=datetime.utcnow(),
        details={'resource_name': 'crash-pod'}
    )


@pytest.fixture
def sample_medium_severity_result():
    """Create medium severity result."""
    return K8sGPTResult(
        name='medium-result',
        kind='Service',
        namespace='default',
        severity='medium',
        problem='Service has no endpoints',
        solution='Check backend pods',
        analyzer='openai',
        timestamp=datetime.utcnow(),
        details={'resource_name': 'test-service'}
    )


@pytest.fixture
def sample_low_severity_result():
    """Create low severity result."""
    return K8sGPTResult(
        name='low-result',
        kind='Pod',
        namespace='default',
        severity='low',
        problem='Pod is pending',
        solution='Wait for resources',
        analyzer='openai',
        timestamp=datetime.utcnow(),
        details={'resource_name': 'pending-pod'}
    )


class TestWeatherStateEnum:
    """Test WeatherState enum."""
    
    def test_weather_states(self):
        """Test all weather state values."""
        assert WeatherState.SUNNY.value == "sunny"
        assert WeatherState.PARTLY_CLOUDY.value == "partly_cloudy"
        assert WeatherState.CLOUDY.value == "cloudy"
        assert WeatherState.RAINY.value == "rainy"
        assert WeatherState.STORMY.value == "stormy"
        assert WeatherState.UNKNOWN.value == "unknown"


class TestK8sGPTResultSummary:
    """Test K8sGPTResultSummary dataclass."""
    
    def test_summary_creation(self):
        """Test creating a result summary."""
        summary = K8sGPTResultSummary(
            name='test-result',
            kind='Pod',
            namespace='default',
            severity='high',
            problem='Test problem',
            timestamp='2024-01-15T10:30:00'
        )
        
        assert summary.name == 'test-result'
        assert summary.kind == 'Pod'
        assert summary.namespace == 'default'
        assert summary.severity == 'high'
        assert summary.problem == 'Test problem'
    
    def test_summary_to_dict(self):
        """Test converting summary to dictionary."""
        summary = K8sGPTResultSummary(
            name='test-result',
            kind='Pod',
            namespace='default',
            severity='high',
            problem='Test problem',
            timestamp='2024-01-15T10:30:00'
        )
        
        summary_dict = summary.to_dict()
        
        assert summary_dict['name'] == 'test-result'
        assert summary_dict['kind'] == 'Pod'
        assert isinstance(summary_dict, dict)


class TestClusterToolInfo:
    """Test ClusterToolInfo dataclass."""
    
    def test_tool_info_creation(self):
        """Test creating tool info."""
        tool = ClusterToolInfo(
            name='k8sgpt',
            version='0.3.0',
            status='running'
        )
        
        assert tool.name == 'k8sgpt'
        assert tool.version == '0.3.0'
        assert tool.status == 'running'
    
    def test_tool_info_to_dict(self):
        """Test converting tool info to dictionary."""
        tool = ClusterToolInfo(
            name='k8sgpt',
            version='0.3.0',
            status='running'
        )
        
        tool_dict = tool.to_dict()
        
        assert tool_dict['name'] == 'k8sgpt'
        assert isinstance(tool_dict, dict)


class TestWeatherResponse:
    """Test WeatherResponse dataclass."""
    
    def test_response_creation(self):
        """Test creating a weather response."""
        response = WeatherResponse(
            weather_state=WeatherState.SUNNY,
            cluster_name='test-cluster',
            cluster_version='1.28',
            k8sgpt_result_count=0,
            top_issues=[],
            cluster_tools=[],
            timestamp=datetime.utcnow()
        )
        
        assert response.weather_state == WeatherState.SUNNY
        assert response.cluster_name == 'test-cluster'
        assert response.cluster_version == '1.28'
        assert response.k8sgpt_result_count == 0
    
    def test_response_to_dict(self):
        """Test converting response to dictionary."""
        timestamp = datetime.utcnow()
        response = WeatherResponse(
            weather_state=WeatherState.SUNNY,
            cluster_name='test-cluster',
            cluster_version='1.28',
            k8sgpt_result_count=0,
            top_issues=[],
            cluster_tools=[],
            timestamp=timestamp
        )
        
        response_dict = response.to_dict()
        
        assert response_dict['weather_state'] == 'sunny'
        assert response_dict['cluster_name'] == 'test-cluster'
        assert response_dict['timestamp'] == timestamp.isoformat()
        assert isinstance(response_dict, dict)


class TestCountBySeverity:
    """Test severity counting."""
    
    def test_count_empty_list(self, weather_calculator):
        """Test counting with empty list."""
        counts = weather_calculator._count_by_severity([])
        
        assert counts['high'] == 0
        assert counts['medium'] == 0
        assert counts['low'] == 0
    
    def test_count_single_severity(
        self,
        weather_calculator,
        sample_high_severity_result
    ):
        """Test counting with single severity."""
        counts = weather_calculator._count_by_severity([sample_high_severity_result])
        
        assert counts['high'] == 1
        assert counts['medium'] == 0
        assert counts['low'] == 0
    
    def test_count_mixed_severities(
        self,
        weather_calculator,
        sample_high_severity_result,
        sample_medium_severity_result,
        sample_low_severity_result
    ):
        """Test counting with mixed severities."""
        results = [
            sample_high_severity_result,
            sample_medium_severity_result,
            sample_low_severity_result,
            sample_low_severity_result
        ]
        
        counts = weather_calculator._count_by_severity(results)
        
        assert counts['high'] == 1
        assert counts['medium'] == 1
        assert counts['low'] == 2


class TestDetermineWeatherState:
    """Test weather state determination."""
    
    def test_sunny_state(self, weather_calculator):
        """Test sunny state (0 issues)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 0, 'low': 0},
            0
        )
        assert state == WeatherState.SUNNY
    
    def test_partly_cloudy_state(self, weather_calculator):
        """Test partly cloudy state (1-2 low severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 0, 'low': 1},
            1
        )
        assert state == WeatherState.PARTLY_CLOUDY
        
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 0, 'low': 2},
            2
        )
        assert state == WeatherState.PARTLY_CLOUDY
    
    def test_cloudy_state_low_severity(self, weather_calculator):
        """Test cloudy state (3-5 low severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 0, 'low': 3},
            3
        )
        assert state == WeatherState.CLOUDY
        
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 0, 'low': 5},
            5
        )
        assert state == WeatherState.CLOUDY
    
    def test_cloudy_state_medium_severity(self, weather_calculator):
        """Test cloudy state (1-2 medium severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 1, 'low': 0},
            1
        )
        assert state == WeatherState.CLOUDY
        
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 2, 'low': 0},
            2
        )
        assert state == WeatherState.CLOUDY
    
    def test_rainy_state_high_severity(self, weather_calculator):
        """Test rainy state (1 high severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 1, 'medium': 0, 'low': 0},
            1
        )
        assert state == WeatherState.RAINY
    
    def test_rainy_state_medium_severity(self, weather_calculator):
        """Test rainy state (3+ medium severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 3, 'low': 0},
            3
        )
        assert state == WeatherState.RAINY
    
    def test_rainy_state_low_severity(self, weather_calculator):
        """Test rainy state (6+ low severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 0, 'low': 6},
            6
        )
        assert state == WeatherState.RAINY
    
    def test_stormy_state_high_severity(self, weather_calculator):
        """Test stormy state (2+ high severity)."""
        state = weather_calculator._determine_weather_state(
            {'high': 2, 'medium': 0, 'low': 0},
            2
        )
        assert state == WeatherState.STORMY
    
    def test_stormy_state_total_count(self, weather_calculator):
        """Test stormy state (10+ total issues)."""
        state = weather_calculator._determine_weather_state(
            {'high': 0, 'medium': 5, 'low': 5},
            10
        )
        assert state == WeatherState.STORMY


class TestGetTopIssues:
    """Test top issues selection."""
    
    def test_get_top_issues_empty(self, weather_calculator):
        """Test getting top issues from empty list."""
        top_issues = weather_calculator._get_top_issues([])
        assert len(top_issues) == 0
    
    def test_get_top_issues_sorted_by_severity(
        self,
        weather_calculator,
        sample_high_severity_result,
        sample_medium_severity_result,
        sample_low_severity_result
    ):
        """Test top issues are sorted by severity."""
        results = [
            sample_low_severity_result,
            sample_high_severity_result,
            sample_medium_severity_result
        ]
        
        top_issues = weather_calculator._get_top_issues(results)
        
        assert len(top_issues) == 3
        assert top_issues[0].severity == 'high'
        assert top_issues[1].severity == 'medium'
        assert top_issues[2].severity == 'low'
    
    def test_get_top_issues_limit(self, weather_calculator):
        """Test top issues respects limit."""
        results = [
            K8sGPTResult(
                name=f'result-{i}',
                kind='Pod',
                namespace='default',
                severity='low',
                problem=f'Problem {i}',
                solution='Fix it',
                analyzer='openai',
                timestamp=datetime.utcnow(),
                details={}
            )
            for i in range(10)
        ]
        
        top_issues = weather_calculator._get_top_issues(results, limit=5)
        
        assert len(top_issues) == 5
    
    def test_get_top_issues_truncates_long_problems(self, weather_calculator):
        """Test long problem descriptions are truncated."""
        long_problem = "A" * 300
        result = K8sGPTResult(
            name='long-result',
            kind='Pod',
            namespace='default',
            severity='high',
            problem=long_problem,
            solution='Fix it',
            analyzer='openai',
            timestamp=datetime.utcnow(),
            details={}
        )
        
        top_issues = weather_calculator._get_top_issues([result])
        
        assert len(top_issues) == 1
        assert len(top_issues[0].problem) == 200
        assert top_issues[0].problem.endswith('...')
    
    def test_get_top_issues_preserves_short_problems(self, weather_calculator):
        """Test short problem descriptions are not truncated."""
        short_problem = "Short problem"
        result = K8sGPTResult(
            name='short-result',
            kind='Pod',
            namespace='default',
            severity='high',
            problem=short_problem,
            solution='Fix it',
            analyzer='openai',
            timestamp=datetime.utcnow(),
            details={}
        )
        
        top_issues = weather_calculator._get_top_issues([result])
        
        assert len(top_issues) == 1
        assert top_issues[0].problem == short_problem


class TestCalculateWeather:
    """Test complete weather calculation."""
    
    def test_calculate_sunny_weather(self, weather_calculator):
        """Test calculating sunny weather (no issues)."""
        response = weather_calculator.calculate_weather(
            results=[],
            cluster_name='test-cluster',
            cluster_version='1.28'
        )
        
        assert response.weather_state == WeatherState.SUNNY
        assert response.cluster_name == 'test-cluster'
        assert response.cluster_version == '1.28'
        assert response.k8sgpt_result_count == 0
        assert len(response.top_issues) == 0
    
    def test_calculate_partly_cloudy_weather(
        self,
        weather_calculator,
        sample_low_severity_result
    ):
        """Test calculating partly cloudy weather."""
        response = weather_calculator.calculate_weather(
            results=[sample_low_severity_result],
            cluster_name='test-cluster',
            cluster_version='1.28'
        )
        
        assert response.weather_state == WeatherState.PARTLY_CLOUDY
        assert response.k8sgpt_result_count == 1
        assert len(response.top_issues) == 1
    
    def test_calculate_cloudy_weather(
        self,
        weather_calculator,
        sample_medium_severity_result
    ):
        """Test calculating cloudy weather."""
        response = weather_calculator.calculate_weather(
            results=[sample_medium_severity_result],
            cluster_name='test-cluster',
            cluster_version='1.28'
        )
        
        assert response.weather_state == WeatherState.CLOUDY
        assert response.k8sgpt_result_count == 1
    
    def test_calculate_rainy_weather(
        self,
        weather_calculator,
        sample_high_severity_result
    ):
        """Test calculating rainy weather."""
        response = weather_calculator.calculate_weather(
            results=[sample_high_severity_result],
            cluster_name='test-cluster',
            cluster_version='1.28'
        )
        
        assert response.weather_state == WeatherState.RAINY
        assert response.k8sgpt_result_count == 1
    
    def test_calculate_stormy_weather(
        self,
        weather_calculator,
        sample_high_severity_result
    ):
        """Test calculating stormy weather."""
        results = [sample_high_severity_result, sample_high_severity_result]
        
        response = weather_calculator.calculate_weather(
            results=results,
            cluster_name='test-cluster',
            cluster_version='1.28'
        )
        
        assert response.weather_state == WeatherState.STORMY
        assert response.k8sgpt_result_count == 2
    
    def test_calculate_with_cluster_tools(
        self,
        weather_calculator,
        sample_low_severity_result
    ):
        """Test calculating weather with cluster tools."""
        tools = [
            ClusterToolInfo(name='k8sgpt', version='0.3.0', status='running'),
            ClusterToolInfo(name='argocd', version='2.9.0', status='running')
        ]
        
        response = weather_calculator.calculate_weather(
            results=[sample_low_severity_result],
            cluster_name='test-cluster',
            cluster_version='1.28',
            cluster_tools=tools
        )
        
        assert len(response.cluster_tools) == 2
        assert response.cluster_tools[0].name == 'k8sgpt'
    
    def test_calculate_includes_timestamp(
        self,
        weather_calculator,
        sample_low_severity_result
    ):
        """Test weather response includes timestamp."""
        response = weather_calculator.calculate_weather(
            results=[sample_low_severity_result],
            cluster_name='test-cluster',
            cluster_version='1.28'
        )
        
        assert isinstance(response.timestamp, datetime)


class TestCreateErrorResponse:
    """Test error response creation."""
    
    def test_create_error_response(self, weather_calculator):
        """Test creating error response."""
        response = weather_calculator.create_error_response(
            cluster_name='test-cluster',
            error_message='Failed to read CRDs'
        )
        
        assert response.weather_state == WeatherState.UNKNOWN
        assert response.cluster_name == 'test-cluster'
        assert response.cluster_version == 'unknown'
        assert response.k8sgpt_result_count == 0
        assert len(response.top_issues) == 0
        assert len(response.cluster_tools) == 0
        assert isinstance(response.timestamp, datetime)
