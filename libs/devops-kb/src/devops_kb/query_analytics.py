"""Query analytics and suggestion engine."""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter

logger = logging.getLogger(__name__)


class QueryAnalytics:
    """Track and analyze query patterns to identify common issues and suggest improvements.

    Notes:
        - By default this class will use the `DEVOPS_KB_ANALYTICS_PATH` environment
          variable if present. If not set, it falls back to a safe per-user temporary
          directory (typically writable in CI and test environments) so instantiation
          does not raise on systems where `/data` is not writable.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize query analytics.

        Args:
            storage_path: Optional path to store analytics data. If None, will use the
                environment variable DEVOPS_KB_ANALYTICS_PATH or fall back to a safe
                per-user temporary directory.
        """
        # Resolve configured path -> env var -> safe temp fallback
        if storage_path:
            resolved = Path(storage_path)
        else:
            env_path = os.getenv("DEVOPS_KB_ANALYTICS_PATH") or os.getenv("QUERY_ANALYTICS_PATH")
            if env_path:
                resolved = Path(env_path)
            else:
                resolved = Path(tempfile.gettempdir()) / "devops_chatbot" / "analytics"

        # Attempt to create the configured directory; if anything goes wrong (missing parents,
        # permission issues, etc.) fall back to a tempdir and try again. Any failure should
        # not raise — analytics will be disabled instead.
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            self.storage_path: Optional[Path] = resolved
        except Exception as e:
            logger.warning(
                "Failed to create analytics storage path %s: %s. Falling back to temp dir.",
                resolved, e,
            )
            fallback = Path(tempfile.gettempdir()) / "devops_chatbot" / "analytics"
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                self.storage_path = fallback
                logger.info("Using fallback analytics directory %s", fallback)
            except Exception as e2:
                logger.error(
                    "Failed to create fallback analytics storage path %s: %s. Analytics will be disabled.",
                    fallback, e2,
                )
                self.storage_path = None

        self.queries_file: Optional[Path] = self.storage_path / "queries.jsonl" if self.storage_path else None

    def record_query(
        self,
        query: str,
        query_type: str,
        user_id: str,
        response_quality: Optional[str] = None,
        resolution_time_seconds: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> None:
        """Record a query for analytics.

        Args:
            query: The query text
            query_type: Type of query (troubleshooting, deployment, etc.)
            user_id: User who submitted the query
            response_quality: Quality rating (good, fair, poor)
            resolution_time_seconds: Time to resolve the issue
            tags: Tags associated with the query
        """
        try:
            record = {
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "query_type": query_type,
                "user_id": user_id,
                "response_quality": response_quality,
                "resolution_time_seconds": resolution_time_seconds,
                "tags": tags or []
            }

            # If storage is disabled or not available, skip recording to avoid raising
            if not self.queries_file:
                logger.warning("Analytics storage not available; skipping record.")
                return

            # Append to JSONL file
            with open(self.queries_file, "a") as f:
                f.write(json.dumps(record) + "\n")

        except Exception as e:
            logger.error(f"Failed to record query: {e}")

    def get_frequent_queries(
        self,
        hours_back: int = 24,
        min_frequency: int = 2,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get frequently asked queries.

        Args:
            hours_back: How many hours back to analyze
            min_frequency: Minimum frequency to include
            limit: Maximum number of queries to return

        Returns:
            List of frequent queries with metadata
        """
        try:
            if not self.queries_file or not self.queries_file.exists():
                return []

            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            query_counts: Dict[str, Dict[str, Any]] = {}

            with open(self.queries_file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        record_time = datetime.fromisoformat(record["timestamp"])

                        if record_time > cutoff_time:
                            query = record["query"]
                            if query not in query_counts:
                                query_counts[query] = {
                                    "count": 0,
                                    "query_type": record.get("query_type"),
                                    "tags": set(),
                                    "quality_ratings": [],
                                    "resolution_times": []
                                }

                            query_counts[query]["count"] += 1
                            if record.get("tags"):
                                query_counts[query]["tags"].update(record["tags"])
                            if record.get("response_quality"):
                                query_counts[query]["quality_ratings"].append(record["response_quality"])
                            if record.get("resolution_time_seconds"):
                                query_counts[query]["resolution_times"].append(record["resolution_time_seconds"])

                    except json.JSONDecodeError:
                        continue

            # Filter by minimum frequency and sort
            frequent = [
                {
                    "query": query,
                    "frequency": data["count"],
                    "query_type": data["query_type"],
                    "tags": list(data["tags"]),
                    "avg_quality": self._calculate_avg_quality(data["quality_ratings"]),
                    "avg_resolution_time": sum(data["resolution_times"]) / len(data["resolution_times"])
                    if data["resolution_times"] else None
                }
                for query, data in query_counts.items()
                if data["count"] >= min_frequency
            ]

            # Sort by frequency descending
            frequent.sort(key=lambda x: x["frequency"], reverse=True)

            return frequent[:limit]

        except Exception as e:
            logger.error(f"Failed to get frequent queries: {e}")
            return []

    def suggest_kb_improvements(
        self,
        hours_back: int = 24,
        min_frequency: int = 3
    ) -> List[Dict[str, Any]]:
        """Suggest new KB entries based on frequent queries.

        Args:
            hours_back: How many hours back to analyze
            min_frequency: Minimum frequency to suggest

        Returns:
            List of suggested KB improvements
        """
        try:
            frequent_queries = self.get_frequent_queries(
                hours_back=hours_back,
                min_frequency=min_frequency,
                limit=20
            )

            suggestions = []
            for query_data in frequent_queries:
                # Suggest KB entry if query is frequent and has poor quality responses
                avg_quality = query_data.get("avg_quality", 0)
                frequency = query_data.get("frequency", 0)

                if frequency >= min_frequency and avg_quality < 0.6:  # Less than 60% good
                    suggestions.append({
                        "type": "new_kb_entry",
                        "priority": "high" if frequency >= min_frequency * 2 else "medium",
                        "query": query_data["query"],
                        "frequency": frequency,
                        "suggested_tags": query_data.get("tags", []),
                        "reason": f"Frequently asked ({frequency} times) with poor response quality ({avg_quality:.0%})"
                    })

                # Suggest KB update if query is frequent but resolution time is high
                avg_resolution_time = query_data.get("avg_resolution_time")
                if avg_resolution_time and avg_resolution_time > 300:  # More than 5 minutes
                    suggestions.append({
                        "type": "kb_update",
                        "priority": "medium",
                        "query": query_data["query"],
                        "frequency": frequency,
                        "suggested_tags": query_data.get("tags", []),
                        "reason": f"Frequently asked ({frequency} times) with long resolution time ({avg_resolution_time:.0f}s)"
                    })

            return suggestions

        except Exception as e:
            logger.error(f"Failed to suggest KB improvements: {e}")
            return []

    def get_query_trends(
        self,
        hours_back: int = 24,
        interval_minutes: int = 60
    ) -> Dict[str, Any]:
        """Get query trends over time.

        Args:
            hours_back: How many hours back to analyze
            interval_minutes: Time interval for grouping

        Returns:
            Dictionary with query trends
        """
        try:
            if not self.queries_file or not self.queries_file.exists():
                return {"intervals": []}

            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            # Use a relaxed typing here because values include Counters and ints
            intervals: Dict[str, Dict[str, Any]] = {}

            with open(self.queries_file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        record_time = datetime.fromisoformat(record["timestamp"])

                        if record_time > cutoff_time:
                            # Round to interval
                            interval_start = record_time.replace(
                                minute=(record_time.minute // interval_minutes) * interval_minutes,
                                second=0,
                                microsecond=0
                            )
                            interval_key = interval_start.isoformat()

                            if interval_key not in intervals:
                                intervals[interval_key] = {
                                    "total_queries": 0,
                                    "by_type": Counter(),
                                    "by_quality": Counter()
                                }

                            intervals[interval_key]["total_queries"] += 1
                            intervals[interval_key]["by_type"][record.get("query_type", "unknown")] += 1
                            if record.get("response_quality"):
                                intervals[interval_key]["by_quality"][record["response_quality"]] += 1

                    except json.JSONDecodeError:
                        continue

            # Convert to list format
            trend_data = [
                {
                    "timestamp": timestamp,
                    "total_queries": data["total_queries"],
                    "by_type": dict(data["by_type"]),
                    "by_quality": dict(data["by_quality"])
                }
                for timestamp, data in sorted(intervals.items())
            ]

            return {
                "intervals": trend_data,
                "total_queries": sum(d["total_queries"] for d in trend_data),
                "average_queries_per_interval": sum(d["total_queries"] for d in trend_data) / len(trend_data)
                if trend_data else 0
            }

        except Exception as e:
            logger.error(f"Failed to get query trends: {e}")
            return {"intervals": []}

    def get_query_type_distribution(self, hours_back: int = 24) -> Dict[str, int]:
        """Get distribution of query types.

        Args:
            hours_back: How many hours back to analyze

        Returns:
            Dictionary with query type counts
        """
        try:
            if not self.queries_file or not self.queries_file.exists():
                return {}

            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            type_counts: Dict[str, int] = Counter()

            with open(self.queries_file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        record_time = datetime.fromisoformat(record["timestamp"])

                        if record_time > cutoff_time:
                            query_type = record.get("query_type", "unknown")
                            type_counts[query_type] += 1

                    except json.JSONDecodeError:
                        continue

            return dict(type_counts)

        except Exception as e:
            logger.error(f"Failed to get query type distribution: {e}")
            return {}

    def _calculate_avg_quality(self, ratings: List[str]) -> float:
        """Calculate average quality score from ratings.

        Args:
            ratings: List of quality ratings (good, fair, poor)

        Returns:
            Average quality score (0-1)
        """
        if not ratings:
            return 0.5

        score_map = {"good": 1.0, "fair": 0.5, "poor": 0.0}
        scores = [score_map.get(rating, 0.5) for rating in ratings]
        return sum(scores) / len(scores)
