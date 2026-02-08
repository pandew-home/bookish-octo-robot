"""
Unit tests for solutions API endpoints.

Tests cover:
- Solution submission (POST /api/solutions)
- Solution listing with pagination and filtering (GET /api/solutions)
- Semantic search via RAG (GET /api/kb/search)

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 6.2, 6.3
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Add libs to path before importing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'devops-kb', 'src'))

from devops_kb.solution import Solution

# Mock the problematic imports before importing the router
sys.modules['rag_integration'] = MagicMock()

from api.solutions import router, get_solution_manager


# Create a test FastAPI app
app = FastAPI()
app.include_router(router)

client = TestClient(app)


@pytest.fixture
def mock_session_id():
    """Mock session ID."""
    return "test-session-123"


@pytest.fixture
def sample_solution():
    """Sample solution for testing."""
    return Solution(
        solution_id="solution-123",
        problem_description="Pod stuck in CrashLoopBackOff",
        resolution_steps="Check container logs, fix application error, verify resource limits",
        tags=["pod", "crashloop", "troubleshooting"],
        runbook_url="https://wiki.example.com/pod-crashloop",
        automation_script=None,
        estimated_fix_time_minutes=15,
        cluster_context={},
        created_at=datetime.now()
    )


@pytest.fixture
def sample_solutions():
    """Sample solutions list for testing."""
    return [
        Solution(
            solution_id=f"solution-{i}",
            problem_description=f"Problem {i}",
            resolution_steps=f"Resolution steps for problem {i}",
            tags=["tag1", "tag2"] if i % 2 == 0 else ["tag3", "tag4"],
            runbook_url=None,
            automation_script=None,
            estimated_fix_time_minutes=10 + i,
            cluster_context={},
            created_at=datetime.now()
        )
        for i in range(25)  # 25 solutions for pagination testing
    ]


@pytest.fixture
def mock_solution_manager():
    """Mock SolutionManager with dependency override."""
    manager = Mock()
    
    # Create a function that returns the manager
    def get_manager():
        return manager
    
    # Set up dependency override
    app.dependency_overrides[get_solution_manager] = get_manager
    
    yield manager
    
    # Clean up
    app.dependency_overrides.clear()


class TestSolutionSubmitEndpoint:
    """Tests for POST /api/solutions endpoint."""
    
    def test_submit_solution_success(self, mock_session_id, mock_solution_manager):
        """Test successful solution submission."""
        # Mock successful submission
        mock_solution_manager.submit_solution.return_value = (True, None, "solution-123")
        
        # Make request
        request_data = {
            "title": "Pod stuck in CrashLoopBackOff",
            "description": "Check container logs, fix application error, verify resource limits",
            "tags": ["pod", "crashloop", "troubleshooting"],
            "runbook_url": "https://wiki.example.com/pod-crashloop",
            "estimated_fix_time_minutes": 15
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert data['solution_id'] == "solution-123"
        assert "successfully" in data['message'].lower()
        
        # Verify solution manager was called correctly
        mock_solution_manager.submit_solution.assert_called_once()
        call_args = mock_solution_manager.submit_solution.call_args
        assert call_args.kwargs['title'] == request_data['title']
        assert call_args.kwargs['description'] == request_data['description']
        assert call_args.kwargs['tags'] == request_data['tags']
        assert call_args.kwargs['runbook_url'] == request_data['runbook_url']
        assert call_args.kwargs['estimated_fix_time_minutes'] == request_data['estimated_fix_time_minutes']
        assert call_args.kwargs['user_id'] == mock_session_id
    
    def test_submit_solution_validation_failure(self, mock_session_id, mock_solution_manager):
        """Test solution submission with validation failure."""
        # Mock validation failure
        error_message = "Solution title must be at least 5 characters long."
        mock_solution_manager.submit_solution.return_value = (False, error_message, None)
        
        # Make request with invalid data
        request_data = {
            "title": "Bad",  # Too short
            "description": "This is a valid description with enough characters",
            "tags": ["tag1"]
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this (min_length=1)
        assert response.status_code == 422
    
    def test_submit_solution_missing_required_fields(self, mock_session_id, mock_solution_manager):
        """Test solution submission with missing required fields."""
        # Using mock_solution_manager fixture
        
        
        # Make request with missing title
        request_data = {
            "description": "This is a valid description",
            "tags": ["tag1"]
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this
        assert response.status_code == 422  # Unprocessable Entity
    
    def test_submit_solution_empty_tags(self, mock_session_id, mock_solution_manager):
        """Test solution submission with empty tags list."""
        # Using mock_solution_manager fixture
        
        
        # Mock validation failure for empty tags
        error_message = "At least one tag is required for categorization."
        mock_solution_manager.submit_solution.return_value = (False, error_message, None)
        
        # Make request with empty tags
        request_data = {
            "title": "Valid Title Here",
            "description": "This is a valid description with enough characters",
            "tags": []
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this (min_items=1)
        assert response.status_code == 422
    
    def test_submit_solution_with_optional_fields(self, mock_session_id, mock_solution_manager):
        """Test solution submission with all optional fields."""
        # Using mock_solution_manager fixture
        
        
        # Mock successful submission
        mock_solution_manager.submit_solution.return_value = (True, None, "solution-456")
        
        # Make request with all optional fields
        request_data = {
            "title": "Complete Solution Example",
            "description": "Detailed resolution steps with all optional fields included",
            "tags": ["comprehensive", "example"],
            "runbook_url": "https://wiki.example.com/complete-solution",
            "automation_script": "kubectl rollout restart deployment/my-app",
            "estimated_fix_time_minutes": 30,
            "cluster_context": {
                "cluster_name": "prod-cluster",
                "namespace": "production"
            }
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert data['solution_id'] == "solution-456"
        
        # Verify all fields were passed to solution manager
        call_args = mock_solution_manager.submit_solution.call_args
        assert call_args.kwargs['automation_script'] == request_data['automation_script']
        assert call_args.kwargs['cluster_context'] == request_data['cluster_context']
    
    def test_submit_solution_title_length_validation(self, mock_session_id, mock_solution_manager):
        """Test solution submission with title length validation."""
        # Using mock_solution_manager fixture
        
        
        # Test title too long (>200 characters)
        long_title = "A" * 201
        request_data = {
            "title": long_title,
            "description": "Valid description with enough characters",
            "tags": ["tag1"]
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this
        assert response.status_code == 422
    
    def test_submit_solution_description_length_validation(self, mock_session_id, mock_solution_manager):
        """Test solution submission with description length validation."""
        # Using mock_solution_manager fixture
        
        
        # Test description too short (<20 characters)
        request_data = {
            "title": "Valid Title",
            "description": "Too short",
            "tags": ["tag1"]
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this
        assert response.status_code == 422


class TestSolutionListEndpoint:
    """Tests for GET /api/solutions endpoint."""
    
    def test_list_solutions_no_filter(self, mock_session_id, mock_solution_manager, sample_solutions):
        """Test listing all solutions without filters."""
        # Using mock_solution_manager fixture
        
        
        # Mock get_all_solutions
        mock_solution_manager.get_all_solutions.return_value = sample_solutions[:20]  # First page
        
        # Make request
        response = client.get(
            "/api/solutions",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 20
        assert data['page'] == 1
        assert data['page_size'] == 20
        assert len(data['solutions']) == 20
        assert data['filters_applied']['tags'] is None
        
        # Verify solutions are sorted by creation date (newest first)
        # All solutions should have required fields
        for solution in data['solutions']:
            assert 'id' in solution
            assert 'title' in solution
            assert 'description' in solution
            assert 'tags' in solution
            assert 'created_at' in solution
    
    def test_list_solutions_with_pagination(self, mock_session_id, mock_solution_manager, sample_solutions):
        """Test listing solutions with pagination."""
        # Using mock_solution_manager fixture
        
        
        # Mock get_all_solutions
        mock_solution_manager.get_all_solutions.return_value = sample_solutions
        
        # Make request for page 2 with page_size 10
        response = client.get(
            "/api/solutions?page=2&page_size=10",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 10
        assert data['page'] == 2
        assert data['page_size'] == 10
        assert data['total_pages'] == 3  # 25 solutions / 10 per page = 3 pages
        assert len(data['solutions']) == 10
    
    def test_list_solutions_with_tag_filter(self, mock_session_id, mock_solution_manager, sample_solutions):
        """Test listing solutions filtered by tags."""
        # Using mock_solution_manager fixture
        
        
        # Filter to only solutions with tag1 and tag2 (even indices)
        filtered_solutions = [s for s in sample_solutions if "tag1" in s.tags]
        mock_solution_manager.get_all_solutions.return_value = filtered_solutions
        
        # Make request with tag filter
        response = client.get(
            "/api/solutions?tags=tag1,tag2",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['filters_applied']['tags'] == ['tag1', 'tag2']
        
        # Verify solution manager was called with tag filter
        mock_solution_manager.get_all_solutions.assert_called_once_with(tags=['tag1', 'tag2'])
    
    def test_list_solutions_empty_result(self, mock_session_id, mock_solution_manager):
        """Test listing solutions when no solutions exist."""
        # Using mock_solution_manager fixture
        
        
        # Mock empty result
        mock_solution_manager.get_all_solutions.return_value = []
        
        # Make request
        response = client.get(
            "/api/solutions",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 0
        assert data['total_pages'] == 0
        assert len(data['solutions']) == 0
    
    def test_list_solutions_invalid_page(self, mock_session_id, mock_solution_manager, sample_solutions):
        """Test listing solutions with invalid page number."""
        # Using mock_solution_manager fixture
        
        
        # Mock get_all_solutions
        mock_solution_manager.get_all_solutions.return_value = sample_solutions
        
        # Make request for page beyond total pages
        response = client.get(
            "/api/solutions?page=100&page_size=10",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 400
        assert "does not exist" in response.json()['detail'].lower()
    
    def test_list_solutions_page_size_limits(self, mock_session_id, mock_solution_manager, sample_solutions):
        """Test listing solutions with page size limits."""
        # Using mock_solution_manager fixture
        
        
        # Mock get_all_solutions
        mock_solution_manager.get_all_solutions.return_value = sample_solutions
        
        # Test page_size too large (>100)
        response = client.get(
            "/api/solutions?page_size=101",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this
        assert response.status_code == 422
    
    def test_list_solutions_includes_metadata(self, mock_session_id, mock_solution_manager, sample_solution):
        """Test listing solutions includes all metadata fields."""
        # Using mock_solution_manager fixture
        
        
        # Mock get_all_solutions
        mock_solution_manager.get_all_solutions.return_value = [sample_solution]
        
        # Make request
        response = client.get(
            "/api/solutions",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        solution = data['solutions'][0]
        
        # Check all required fields
        assert solution['id'] == sample_solution.id
        assert solution['title'] == sample_solution.problem_description
        assert solution['description'] == sample_solution.resolution_steps
        assert solution['tags'] == sample_solution.tags
        assert solution['runbook_url'] == sample_solution.runbook_url
        assert solution['estimated_fix_time_minutes'] == sample_solution.estimated_fix_time_minutes
        assert 'created_at' in solution
        assert 'usage_count' in solution


class TestKnowledgeBaseSearchEndpoint:
    """Tests for GET /api/kb/search endpoint."""
    
    @patch('api.solutions.get_rag_integration')
    def test_search_knowledge_base_success(
        self,
        mock_get_rag,
        mock_session_id,
        mock_solution_manager,
        sample_solution
    ):
        """Test successful knowledge base search."""
        # Using mock_solution_manager fixture
        
        
        # Mock RAG integration
        mock_rag = Mock()
        mock_get_rag.return_value = mock_rag
        
        # Mock search results with similarity scores
        mock_rag.search_knowledge_base.return_value = [
            {
                'id': 'solution-123',
                'similarity_score': 0.85,
                'metadata': {'id': 'solution-123'}
            },
            {
                'id': 'solution-456',
                'similarity_score': 0.75,
                'metadata': {'id': 'solution-456'}
            }
        ]
        
        # Mock solution retrieval
        mock_solution_manager.get_solution.return_value = sample_solution
        
        # Make request
        response = client.get(
            "/api/kb/search?query=pod+crashloop",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['query'] == "pod crashloop"
        assert data['count'] == 2
        assert len(data['results']) == 2
        
        # Check search metadata
        assert 'search_metadata' in data
        assert data['search_metadata']['similarity_threshold'] == 0.7
        assert data['search_metadata']['top_k'] == 5
        
        # Verify RAG search was called
        mock_rag.search_knowledge_base.assert_called_once_with("pod crashloop", top_k=5)
    
    @patch('api.solutions.get_rag_integration')
    def test_search_knowledge_base_with_top_k(
        self,
        mock_get_rag,
        mock_session_id,
        mock_solution_manager
    ):
        """Test knowledge base search with custom top_k."""
        # Using mock_solution_manager fixture
        
        
        # Mock RAG integration
        mock_rag = Mock()
        mock_get_rag.return_value = mock_rag
        mock_rag.search_knowledge_base.return_value = []
        
        # Make request with custom top_k
        response = client.get(
            "/api/kb/search?query=test&top_k=10",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        
        # Verify RAG search was called with correct top_k
        mock_rag.search_knowledge_base.assert_called_once_with("test", top_k=10)
    
    @patch('api.solutions.get_rag_integration')
    def test_search_knowledge_base_filters_by_similarity(
        self,
        mock_get_rag,
        mock_session_id,
        mock_solution_manager,
        sample_solution
    ):
        """Test knowledge base search filters results by similarity threshold."""
        # Using mock_solution_manager fixture
        
        
        # Mock RAG integration
        mock_rag = Mock()
        mock_get_rag.return_value = mock_rag
        
        # Mock search results with varying similarity scores
        mock_rag.search_knowledge_base.return_value = [
            {
                'id': 'solution-1',
                'similarity_score': 0.85,  # Above threshold
                'metadata': {'id': 'solution-1'}
            },
            {
                'id': 'solution-2',
                'similarity_score': 0.65,  # Below threshold (0.7)
                'metadata': {'id': 'solution-2'}
            },
            {
                'id': 'solution-3',
                'similarity_score': 0.75,  # Above threshold
                'metadata': {'id': 'solution-3'}
            }
        ]
        
        # Mock solution retrieval
        mock_solution_manager.get_solution.return_value = sample_solution
        
        # Make request
        response = client.get(
            "/api/kb/search?query=test",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        # Should only return 2 results (above 0.7 threshold)
        assert data['count'] == 2
        assert data['search_metadata']['total_results'] == 3
        assert data['search_metadata']['filtered_results'] == 2
        
        # Verify all returned results have similarity >= 0.7
        for result in data['results']:
            assert result['similarity_score'] >= 0.7
    
    @patch('api.solutions.get_rag_integration')
    def test_search_knowledge_base_empty_results(
        self,
        mock_get_rag,
        mock_session_id,
        mock_solution_manager
    ):
        """Test knowledge base search with no results."""
        # Using mock_solution_manager fixture
        
        
        # Mock RAG integration
        mock_rag = Mock()
        mock_get_rag.return_value = mock_rag
        mock_rag.search_knowledge_base.return_value = []
        
        # Make request
        response = client.get(
            "/api/kb/search?query=nonexistent",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        assert data['count'] == 0
        assert len(data['results']) == 0
    
    def test_search_knowledge_base_missing_query(self, mock_session_id, mock_solution_manager):
        """Test knowledge base search without query parameter."""
        # Using mock_solution_manager fixture
        
        
        # Make request without query
        response = client.get(
            "/api/kb/search",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this
        assert response.status_code == 422
    
    def test_search_knowledge_base_query_length_validation(self, mock_session_id, mock_solution_manager):
        """Test knowledge base search with query length validation."""
        # Using mock_solution_manager fixture
        
        
        # Test query too long (>500 characters)
        long_query = "A" * 501
        response = client.get(
            f"/api/kb/search?query={long_query}",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions - FastAPI validation should catch this
        assert response.status_code == 422
    
    @patch('api.solutions.get_rag_integration')
    def test_search_knowledge_base_includes_all_fields(
        self,
        mock_get_rag,
        mock_session_id,
        mock_solution_manager,
        sample_solution
    ):
        """Test knowledge base search results include all required fields."""
        # Using mock_solution_manager fixture
        
        
        # Mock RAG integration
        mock_rag = Mock()
        mock_get_rag.return_value = mock_rag
        
        # Mock search results
        mock_rag.search_knowledge_base.return_value = [
            {
                'id': 'solution-123',
                'similarity_score': 0.85,
                'metadata': {'id': 'solution-123'}
            }
        ]
        
        # Mock solution retrieval
        mock_solution_manager.get_solution.return_value = sample_solution
        
        # Make request
        response = client.get(
            "/api/kb/search?query=test",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        result = data['results'][0]
        
        # Check all required fields (Requirements 6.3)
        assert 'id' in result
        assert 'title' in result
        assert 'description' in result
        assert 'tags' in result
        assert 'similarity_score' in result
        assert 'runbook_url' in result
        assert 'estimated_fix_time_minutes' in result
        
        # Verify values
        assert result['id'] == sample_solution.id
        assert result['title'] == sample_solution.problem_description
        assert result['similarity_score'] == 0.85


class TestSolutionManagerIntegration:
    """Tests for solution manager integration."""
    
    def test_solution_manager_initialization(self, mock_session_id):
        """Test solution manager is properly initialized."""
        with patch('api.solutions.KnowledgeBase') as mock_kb_class:
            with patch('api.solutions.get_rag_integration') as mock_get_rag:
                with patch('api.solutions.SolutionManager') as mock_sm_class:
                    # Mock dependencies
                    mock_kb = Mock()
                    mock_kb_class.return_value = mock_kb
                    
                    mock_rag = Mock()
                    mock_rag.rag_engine = Mock()
                    mock_get_rag.return_value = mock_rag
                    
                    mock_sm = Mock()
                    mock_sm_class.return_value = mock_sm
                    
                    # Make request to trigger initialization
                    response = client.get(
                        "/api/solutions",
                        headers={"X-Session-Id": mock_session_id}
                    )
                    
                    # Verify solution manager was created with correct dependencies
                    mock_sm_class.assert_called_once()
                    call_args = mock_sm_class.call_args
                    assert call_args.kwargs['knowledge_base'] == mock_kb
                    assert call_args.kwargs['rag_engine'] == mock_rag.rag_engine


class TestErrorHandling:
    """Tests for error handling in solutions API."""
    
    def test_submit_solution_manager_error(self, mock_session_id, mock_solution_manager):
        """Test solution submission handles manager errors gracefully."""
        # Using mock_solution_manager fixture
        
        
        # Mock manager error
        mock_solution_manager.submit_solution.side_effect = Exception("Database connection failed")
        
        # Make request
        request_data = {
            "title": "Valid Title",
            "description": "Valid description with enough characters",
            "tags": ["tag1"]
        }
        
        response = client.post(
            "/api/solutions",
            json=request_data,
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 500
        assert "unable" in response.json()['detail'].lower()
    
    def test_list_solutions_manager_error(self, mock_session_id, mock_solution_manager):
        """Test solution listing handles manager errors gracefully."""
        # Using mock_solution_manager fixture
        
        
        # Mock manager error
        mock_solution_manager.get_all_solutions.side_effect = Exception("Database connection failed")
        
        # Make request
        response = client.get(
            "/api/solutions",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 500
        assert "unable" in response.json()['detail'].lower()
    
    @patch('api.solutions.get_rag_integration')
    def test_search_rag_error(
        self,
        mock_get_rag,
        mock_session_id,
        mock_solution_manager
    ):
        """Test knowledge base search handles RAG errors gracefully."""
        # Using mock_solution_manager fixture
        
        
        # Mock RAG integration error
        mock_rag = Mock()
        mock_get_rag.return_value = mock_rag
        mock_rag.search_knowledge_base.side_effect = Exception("FAISS index corrupted")
        
        # Make request
        response = client.get(
            "/api/kb/search?query=test",
            headers={"X-Session-Id": mock_session_id}
        )
        
        # Assertions
        assert response.status_code == 500
        assert "unable" in response.json()['detail'].lower()

