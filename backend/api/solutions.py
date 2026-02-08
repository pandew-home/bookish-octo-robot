"""
API endpoints for knowledge base solutions management.

This module provides endpoints for:
- Solution submission (POST /api/solutions)
- Solution listing with pagination and filtering (GET /api/solutions)
- Semantic search via RAG (GET /api/kb/search)

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 6.2, 6.3
"""
import sys
import os
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# Add libs to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'devops-kb', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'devops-rag', 'src'))

from api.credentials import get_session_id
from solution_manager import SolutionManager
from rag_integration import get_rag_integration
from devops_kb.knowledge_base import KnowledgeBase
from utils.error_handler import handle_generic_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["solutions", "knowledge-base"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SolutionSubmitRequest(BaseModel):
    """Request model for solution submission."""
    title: str = Field(..., description="Solution title (5-200 characters)", min_length=5, max_length=200)
    description: str = Field(..., description="Solution description/resolution steps (20-10000 characters)", min_length=20, max_length=10000)
    tags: List[str] = Field(..., description="Tags for categorization (1-10 tags, max 50 chars each)", min_length=1, max_length=10)
    runbook_url: Optional[str] = Field(None, description="Optional URL to runbook")
    automation_script: Optional[str] = Field(None, description="Optional automation script")
    estimated_fix_time_minutes: Optional[int] = Field(None, description="Optional estimated fix time in minutes", ge=0)
    cluster_context: Optional[Dict[str, Any]] = Field(None, description="Optional cluster context information")


class SolutionSubmitResponse(BaseModel):
    """Response model for solution submission."""
    success: bool
    message: str
    solution_id: Optional[str] = None


class SolutionListItem(BaseModel):
    """Model for solution list item."""
    id: str
    title: str
    description: str
    tags: List[str]
    runbook_url: Optional[str] = None
    estimated_fix_time_minutes: Optional[int] = None
    created_at: str
    usage_count: int = 0


class SolutionListResponse(BaseModel):
    """Response model for solution listing."""
    solutions: List[SolutionListItem]
    count: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: Dict[str, Any]


class SearchResult(BaseModel):
    """Model for semantic search result."""
    id: str
    title: str
    description: str
    tags: List[str]
    similarity_score: float
    runbook_url: Optional[str] = None
    estimated_fix_time_minutes: Optional[int] = None


class SearchResponse(BaseModel):
    """Response model for semantic search."""
    query: str
    results: List[SearchResult]
    count: int
    search_metadata: Dict[str, Any]


# ============================================================================
# Dependency: Get Solution Manager
# ============================================================================

def get_solution_manager() -> SolutionManager:
    """
    Get or create SolutionManager instance.
    
    Returns:
        SolutionManager instance
        
    Raises:
        HTTPException: If initialization fails
    """
    try:
        # Get knowledge base path from environment
        kb_path = os.getenv('KB_PATH', '/data/knowledge_base')
        
        # Initialize knowledge base
        kb = KnowledgeBase(kb_path)
        
        # Get RAG integration (for embedding generation)
        llm_provider = os.getenv('LLM_PROVIDER', 'openai')
        llm_model = os.getenv('LLM_MODEL', 'gpt-3.5-turbo')
        api_key = os.getenv('OPENAI_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        
        rag_integration = get_rag_integration(
            llm_provider=llm_provider,
            llm_model=llm_model,
            api_key=api_key,
            kb_path=kb_path
        )
        
        # Create solution manager
        solution_manager = SolutionManager(
            knowledge_base=kb,
            rag_engine=rag_integration.rag_engine
        )
        
        return solution_manager
        
    except Exception as e:
        logger.error(f"Failed to initialize SolutionManager: {e}")
        raise HTTPException(
            status_code=500,
            detail="Knowledge base service unavailable. Please try again later."
        )


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/solutions", response_model=SolutionSubmitResponse)
async def submit_solution(
    request: SolutionSubmitRequest,
    session_id: str = Depends(get_session_id),
    solution_manager: SolutionManager = Depends(get_solution_manager)
):
    """
    Submit a new solution to the knowledge base.
    
    This endpoint:
    1. Validates solution fields (title, description, tags)
    2. Creates a Solution object
    3. Generates embeddings for the solution
    4. Stores the solution in the knowledge base
    5. Updates the FAISS index immediately
    
    The solution becomes immediately available for semantic search
    by all users in subsequent queries.
    
    Args:
        request: Solution submission request
        session_id: Session ID from header
        solution_manager: SolutionManager dependency
        
    Returns:
        SolutionSubmitResponse with success status and solution ID
        
    Raises:
        HTTPException: If validation fails or submission fails
        
    Requirements: 11.1, 11.2, 11.3
    """
    try:
        logger.info(f"Submitting solution: {request.title[:50]}...")
        
        # Submit solution through solution manager
        success, error_message, solution_id = solution_manager.submit_solution(
            title=request.title,
            description=request.description,
            tags=request.tags,
            runbook_url=request.runbook_url,
            automation_script=request.automation_script,
            estimated_fix_time_minutes=request.estimated_fix_time_minutes,
            cluster_context=request.cluster_context,
            user_id=session_id
        )
        
        if not success:
            logger.warning(f"Solution submission failed: {error_message}")
            raise HTTPException(
                status_code=400,
                detail=error_message
            )
        
        logger.info(f"Solution submitted successfully: {solution_id}")
        
        return SolutionSubmitResponse(
            success=True,
            message="Solution submitted successfully and is now available for search.",
            solution_id=solution_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting solution: {e}")
        raise handle_generic_error(
            e,
            "submitting solution",
            "Unable to submit solution. Please try again later."
        )


@router.get("/solutions", response_model=SolutionListResponse)
async def list_solutions(
    session_id: str = Depends(get_session_id),
    solution_manager: SolutionManager = Depends(get_solution_manager),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags to filter by"),
    page: int = Query(1, description="Page number (1-indexed)", ge=1),
    page_size: int = Query(20, description="Number of solutions per page", ge=1, le=100)
):
    """
    List solutions with pagination and optional tag filtering.
    
    This endpoint retrieves solutions from the knowledge base with support for:
    - Tag-based filtering (comma-separated list)
    - Pagination (page and page_size parameters)
    - Sorting by creation date (newest first)
    
    Args:
        session_id: Session ID from header
        solution_manager: SolutionManager dependency
        tags: Optional comma-separated list of tags to filter by
        page: Page number (1-indexed)
        page_size: Number of solutions per page
        
    Returns:
        SolutionListResponse with paginated solutions
        
    Raises:
        HTTPException: If retrieval fails
        
    Requirements: 11.4, 11.5
    """
    try:
        logger.info(f"Listing solutions (page={page}, page_size={page_size}, tags={tags})")
        
        # Parse tags if provided
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Get all solutions (with optional tag filter)
        all_solutions = solution_manager.get_all_solutions(tags=tag_list)
        
        # Sort by creation date (newest first)
        all_solutions.sort(key=lambda s: s.created_at, reverse=True)
        
        # Calculate pagination
        total_count = len(all_solutions)
        total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
        
        # Validate page number
        if page > total_pages and total_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Page {page} does not exist. Total pages: {total_pages}"
            )
        
        # Get solutions for current page
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_solutions = all_solutions[start_idx:end_idx]
        
        # Convert to response model
        solution_items = [
            SolutionListItem(
                id=s.id,
                title=s.problem_description,
                description=s.resolution_steps,
                tags=s.tags,
                runbook_url=s.runbook_url,
                estimated_fix_time_minutes=s.estimated_fix_time_minutes,
                created_at=s.created_at.isoformat(),
                usage_count=getattr(s, 'usage_count', 0)
            )
            for s in page_solutions
        ]
        
        filters_applied = {
            'tags': tag_list if tag_list else None
        }
        
        logger.info(f"Returning {len(solution_items)} solutions (page {page}/{total_pages})")
        
        return SolutionListResponse(
            solutions=solution_items,
            count=len(solution_items),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            filters_applied=filters_applied
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing solutions: {e}")
        raise handle_generic_error(
            e,
            "listing solutions",
            "Unable to retrieve solutions. Please try again later."
        )


@router.get("/kb/search", response_model=SearchResponse)
async def search_knowledge_base(
    session_id: str = Depends(get_session_id),
    solution_manager: SolutionManager = Depends(get_solution_manager),
    query: str = Query(..., description="Search query", min_length=1, max_length=500),
    top_k: int = Query(5, description="Number of top results to return", ge=1, le=20)
):
    """
    Perform semantic search over the knowledge base using RAG.
    
    This endpoint:
    1. Generates embeddings for the search query
    2. Performs semantic search against the FAISS index
    3. Returns top-k most relevant solutions with similarity scores
    4. Filters results to only include those with similarity score > 0.7
    
    The search uses the same RAG engine as the chat interface,
    providing consistent semantic matching across the application.
    
    Args:
        session_id: Session ID from header
        solution_manager: SolutionManager dependency
        query: Search query string
        top_k: Number of top results to return (max 20)
        
    Returns:
        SearchResponse with relevant solutions and similarity scores
        
    Raises:
        HTTPException: If search fails
        
    Requirements: 6.2, 6.3
    """
    try:
        logger.info(f"Searching knowledge base: '{query[:50]}...' (top_k={top_k})")
        
        # Get RAG integration for semantic search
        rag_integration = get_rag_integration()
        
        # Perform semantic search
        search_results = rag_integration.search_knowledge_base(query, top_k=top_k)
        
        # Filter by similarity threshold (0.7)
        similarity_threshold = 0.7
        filtered_results = [
            r for r in search_results
            if r.get('similarity_score', 0.0) >= similarity_threshold
        ]
        
        logger.info(f"Found {len(search_results)} results, {len(filtered_results)} above threshold {similarity_threshold}")
        
        # Convert to response model
        result_items = []
        for result in filtered_results:
            metadata = result.get('metadata', {})
            
            # Get solution details from knowledge base
            solution_id = result.get('id') or metadata.get('id')
            if solution_id:
                solution = solution_manager.get_solution(solution_id)
                if solution:
                    result_items.append(SearchResult(
                        id=solution.id,
                        title=solution.problem_description,
                        description=solution.resolution_steps,
                        tags=solution.tags,
                        similarity_score=result.get('similarity_score', 0.0),
                        runbook_url=solution.runbook_url,
                        estimated_fix_time_minutes=solution.estimated_fix_time_minutes
                    ))
        
        search_metadata = {
            'total_results': len(search_results),
            'filtered_results': len(filtered_results),
            'similarity_threshold': similarity_threshold,
            'top_k': top_k
        }
        
        logger.info(f"Returning {len(result_items)} search results")
        
        return SearchResponse(
            query=query,
            results=result_items,
            count=len(result_items),
            search_metadata=search_metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        raise handle_generic_error(
            e,
            "searching knowledge base",
            "Unable to search knowledge base. Please try again later."
        )
