"""Agentic loop for the chat agent.

This module owns three things:

1. Loading the system prompt from ``backend/prompts/system.md`` (override path
   via the ``SYSTEM_PROMPT_PATH`` env var) and rendering it with live context.
2. Running a bounded tool-calling loop against the LLM client until either the
   model produces a final text response or a stop condition fires.
3. Compacting older tool results when the conversation is about to overflow
   the model's context window.

Tool *definitions* and *implementations* live in ``agent_tools.py``. Skill
discovery lives in ``skills.py``. Keep the loop small and let those modules
own their concerns.

# MAINTENANCE — read before changing this file
# AI assistants: the loop's stop conditions (no_progress / dedupe_loop /
# blocked_loop / context_budget_exhausted / forced_final_synthesis) are load-
# bearing safety mechanisms. They prevent runaway tool-calling and infinite
# loops. Do NOT remove, reorder, or relax any of them, and do NOT add new
# stop conditions, without explicit human review. Same for the message-budget
# compaction in ``_enforce_message_budget`` — getting it wrong makes the agent
# either hallucinate (too aggressive) or run out of context (too lenient).
#
# If a request goes beyond fixing a localized bug — e.g. "also stream tool
# results", "switch to a different LLM SDK", "add memory", "support multiple
# parallel agents" — stop and ask the human. Those are feature decisions, not
# refactors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_tools import AgentContext, build_tool_specs, execute_tool
from kube_policy import KubeApiPolicy
from skills import format_skills_summary, load_skills

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"

MAX_PARALLEL_TOOL_CALLS = 3
MAX_NO_PROGRESS_ROUNDS = 2
MAX_DEDUP_ONLY_ROUNDS = 2
MAX_BLOCKED_ONLY_ROUNDS = 2
MAX_CONTEXT_TOKENS = 12000
RECENT_MESSAGES_TO_KEEP = 12
MAX_COMPACTED_TOOL_RESULTS = 25


def _load_system_prompt(path: Optional[Path] = None) -> str:
    """Read the system prompt template. ``SYSTEM_PROMPT_PATH`` env var wins."""
    candidate = (
        Path(os.environ["SYSTEM_PROMPT_PATH"])
        if os.getenv("SYSTEM_PROMPT_PATH")
        else (path or DEFAULT_PROMPT_PATH)
    )
    return candidate.read_text(encoding="utf-8")


def _safe_prompt_format(template: str, **kwargs: Any) -> str:
    """Format system prompt without breaking on braces in memory/K8sGPT text.

    Escapes ``{``/``}`` inside substituted values so ``str.format`` cannot
    interpret them as field names (JSON, Helm, Go templates, etc.).
    """
    escaped = {
        key: str(value).replace("{", "{{").replace("}", "}}")
        for key, value in kwargs.items()
    }
    try:
        return template.format(**escaped)
    except (KeyError, ValueError, IndexError) as exc:
        logger.warning("[AGENT] prompt format failed (%s); using unformatted template", exc)
        # Last resort: append context blocks without format
        parts = [template]
        for key, value in kwargs.items():
            parts.append(f"\n## {key}\n{value}")
        return "\n".join(parts)


class AgentEngine:
    """Tool-enabled LLM engine for Kubernetes troubleshooting."""

    def __init__(
        self,
        llm_client: Any,
        k8sgpt_results: Optional[List] = None,
        k8s_clients: Optional[Dict[str, Any]] = None,
        cluster_version: Optional[str] = None,
        skills_dir: Optional[Path] = None,
        system_prompt_path: Optional[Path] = None,
        memory_summary: str = "",
        kube_policy: Optional[KubeApiPolicy] = None,
    ):
        self.llm_client = llm_client
        self.k8sgpt_results = k8sgpt_results or []
        self.k8s_clients = k8s_clients or {}
        self.cluster_version = (cluster_version or "").strip() or "unknown"
        self.kube_policy = kube_policy

        self.skills = load_skills(skills_dir)
        self.system_prompt_template = _load_system_prompt(system_prompt_path)
        self.memory_summary = memory_summary

    async def run(self, query: str) -> Dict[str, Any]:
        """Run the tool-calling loop and return ``{response, errors, metadata}``.

        Unexpected failures are soft-failed into a recoverable response so the
        chat turn does not derail the conversation thread.
        """
        try:
            return await self._run_loop(query)
        except Exception as exc:
            logger.exception("[AGENT] unexpected failure (soft-fail for chat continuity): %s", exc)
            return {
                "response": (
                    "I hit an internal error while investigating and could not finish this turn. "
                    "Your earlier messages are still here—try rephrasing or narrowing the question."
                ),
                "errors": [
                    {
                        "code": "agent_error",
                        "message": "Agent loop failed unexpectedly; you can continue the chat.",
                        "severity": "error",
                    }
                ],
                "metadata": {
                    "tool_calls_used": 0,
                    "rounds": 0,
                    "stop_reason": "internal_error",
                    "soft_failed": True,
                },
            }

    async def _run_loop(self, query: str) -> Dict[str, Any]:
        """Inner agent loop (may raise; wrapped by ``run``)."""
        ctx = AgentContext(
            k8s_clients=self.k8s_clients,
            k8sgpt_results=self.k8sgpt_results,
            skills=self.skills,
            cluster_version=self.cluster_version,
            kube_policy=self.kube_policy,
        )

        system_content = _safe_prompt_format(
            self.system_prompt_template,
            k8sgpt_summary=self._format_k8sgpt_summary() or "None available.",
            memory_summary=self.memory_summary or "No memory context available.",
            cluster_version=_major_minor_version(self.cluster_version),
            api_reference_url=_api_reference_url(self.cluster_version),
            skills_summary=format_skills_summary(self.skills),
        )

        messages: List[Any] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]
        tools = build_tool_specs(ctx)

        tool_calls_used = 0
        rounds = 0
        errors: List[Any] = []
        stop_reason = ""
        dedup_hits = 0
        no_progress_rounds = 0
        dedup_only_rounds = 0
        blocked_only_rounds = 0
        tool_cache: Dict[str, Dict[str, Any]] = {}

        logger.info("[AGENT] Calling LLM with tool access...")
        result: Dict[str, Any] = {}
        while True:
            rounds += 1

            messages = self._enforce_message_budget(messages)
            if self._estimate_messages_tokens(messages) > MAX_CONTEXT_TOKENS:
                stop_reason = "context_budget_exhausted"
                errors.append(
                    "Stop condition reached: message context exceeded token budget after compaction."
                )
                break

            result = await asyncio.to_thread(
                self.llm_client.generate_with_tools, messages, tools
            )

            if result.get("type") == "text":
                break

            if result.get("type") != "tool_calls":
                errors.append("Unexpected LLM response type while processing tool calls.")
                break

            tool_calls = result.get("tool_calls", [])
            if not tool_calls:
                break

            tool_calls_used += len(tool_calls)
            outcomes = await self._execute_tool_calls_parallel(tool_calls, tool_cache, ctx)

            round_made_progress = False
            round_all_deduped = bool(outcomes)
            round_all_blocked = bool(outcomes)

            for outcome in outcomes:
                if outcome["deduped"]:
                    dedup_hits += 1
                else:
                    round_all_deduped = False

                if outcome["made_progress"]:
                    round_made_progress = True
                    round_all_blocked = False
                elif not outcome["blocked"]:
                    round_all_blocked = False

                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "TOOL_RESULT "
                            f"{outcome['tool_name']} "
                            f"args={json.dumps(outcome['args'], default=str)} "
                            f"result={json.dumps(outcome['tool_output'], default=str)}"
                        ),
                    }
                )

            if round_made_progress:
                no_progress_rounds = 0
            else:
                no_progress_rounds += 1
                if no_progress_rounds >= MAX_NO_PROGRESS_ROUNDS:
                    stop_reason = "no_progress"
                    errors.append("Stop condition reached: repeated tool calls produced no new evidence.")
                    break

            if round_all_deduped:
                dedup_only_rounds += 1
                if dedup_only_rounds >= MAX_DEDUP_ONLY_ROUNDS:
                    stop_reason = "dedupe_loop"
                    errors.append("Stop condition reached: repeated duplicate tool calls without new evidence.")
                    break
            else:
                dedup_only_rounds = 0

            if round_all_blocked:
                blocked_only_rounds += 1
                if blocked_only_rounds >= MAX_BLOCKED_ONLY_ROUNDS:
                    stop_reason = "blocked_loop"
                    errors.append("Stop condition reached: only blocked/approval-required actions requested repeatedly.")
                    break
            else:
                blocked_only_rounds = 0

        if result.get("type") != "text":
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "STOP_CONDITION Reached. Provide the best final diagnosis now using gathered evidence. "
                        "If evidence is insufficient, state what should be investigated next."
                    ),
                }
            )
            forced = await asyncio.to_thread(self.llm_client.generate_with_tools, messages, [])
            if forced.get("type") == "text":
                result = forced
                if not stop_reason:
                    stop_reason = "forced_final_synthesis"

        response_text = result.get("text", "Unable to generate a response.")
        logger.info("[AGENT] Response: %d chars", len(response_text))

        return {
            "response": response_text,
            "errors": errors,
            "metadata": {
                "tool_calls_used": tool_calls_used,
                "rounds": rounds,
                "tools_available": len(tools),
                "dedup_hits": dedup_hits,
                "stop_reason": stop_reason,
                "skills_loaded": [s.name for s in self.skills.values()],
            },
        }

    # ------------------------------------------------------------------
    # Tool execution.
    # ------------------------------------------------------------------

    async def _execute_tool_calls_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_cache: Dict[str, Dict[str, Any]],
        ctx: AgentContext,
    ) -> List[Dict[str, Any]]:
        """Execute tool calls in parallel with bounded concurrency and dedupe cache."""
        semaphore = asyncio.Semaphore(MAX_PARALLEL_TOOL_CALLS)

        async def _run(index: int, tool_call: Dict[str, Any]) -> Dict[str, Any]:
            tool_name = tool_call.get("name", "unknown_tool")
            args = tool_call.get("args", {})
            call_key = _tool_call_key(tool_name, args)

            if call_key in tool_cache:
                cached = tool_cache[call_key]
                return {
                    "index": index,
                    "tool_name": tool_name,
                    "args": args,
                    "tool_output": {
                        "deduped": True,
                        "cached": True,
                        "tool": tool_name,
                        "result": cached,
                    },
                    "deduped": True,
                    "blocked": False,
                    "approval_required": False,
                    "made_progress": False,
                    "reason": "deduped",
                }

            async with semaphore:
                tool_output = await asyncio.to_thread(execute_tool, tool_name, args, ctx)

            tool_cache[call_key] = tool_output
            blocked = False
            approval_required = False
            made_progress = False
            reason = ""

            if isinstance(tool_output, dict):
                approval_required = bool(tool_output.get("approval_required"))
                blocked = bool(tool_output.get("blocked")) or approval_required
                reason = str(tool_output.get("reason", ""))
                made_progress = not tool_output.get("error") and not blocked

            return {
                "index": index,
                "tool_name": tool_name,
                "args": args,
                "tool_output": tool_output,
                "deduped": False,
                "blocked": blocked,
                "approval_required": approval_required,
                "made_progress": made_progress,
                "reason": reason,
            }

        tasks = [_run(idx, call) for idx, call in enumerate(tool_calls)]
        outcomes = await asyncio.gather(*tasks)
        outcomes.sort(key=lambda item: item["index"])
        return outcomes

    # ------------------------------------------------------------------
    # Message budget compaction.
    # ------------------------------------------------------------------

    def _estimate_messages_tokens(self, messages: List[Any]) -> int:
        joined = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", ""))
            content = msg.get("content", "")
            if isinstance(content, str):
                joined.append(f"{role}:{content}")
            else:
                joined.append(f"{role}:{json.dumps(content, default=str)}")
        text = "\n".join(joined)

        count_fn = getattr(self.llm_client, "count_tokens", None)
        if callable(count_fn):
            try:
                return int(count_fn(text))
            except Exception:
                pass
        return max(len(text) // 4, 1) if text else 0

    def _enforce_message_budget(self, messages: List[Any]) -> List[Any]:
        if self._estimate_messages_tokens(messages) <= MAX_CONTEXT_TOKENS:
            return messages
        if len(messages) <= 3:
            return messages

        head = messages[:2]
        tail_count = min(RECENT_MESSAGES_TO_KEEP, max(len(messages) - 2, 1))
        tail = messages[-tail_count:]
        middle = messages[2:-tail_count] if len(messages) > 2 + tail_count else []

        summary_lines: List[str] = []
        compacted_tool_results = 0
        dropped_messages = 0

        for msg in middle:
            if not isinstance(msg, dict):
                dropped_messages += 1
                continue
            parsed = _parse_tool_result_for_summary(msg.get("content", ""))
            if parsed is None:
                dropped_messages += 1
                continue
            compacted_tool_results += 1
            if len(summary_lines) < MAX_COMPACTED_TOOL_RESULTS:
                tool_name, args, result = parsed
                summary_lines.append(
                    f"- {tool_name} args={json.dumps(args, default=str)} result={json.dumps(result, default=str)}"
                )

        if compacted_tool_results == 0 and dropped_messages == 0:
            return messages

        summary_parts = [
            "EVIDENCE_SUMMARY",
            (
                f"Compacted {compacted_tool_results} tool results and dropped {dropped_messages} older messages "
                "to stay within token budget."
            ),
        ]
        if summary_lines:
            summary_parts.append("\n".join(summary_lines))

        summary_message = {"role": "system", "content": "\n".join(summary_parts)}
        return head + [summary_message] + tail

    # ------------------------------------------------------------------
    # Context formatting helpers.
    # ------------------------------------------------------------------

    def _format_k8sgpt_summary(self) -> str:
        if not self.k8sgpt_results:
            return ""
        lines = []
        for r in self.k8sgpt_results[:10]:
            if hasattr(r, "name"):
                details = r.details if isinstance(r.details, dict) else {}
                resource_name = details.get("resource_name", "")
                raw_errors = details.get("error", [])
                error_detail = ""
                if isinstance(raw_errors, list) and raw_errors:
                    combined = " | ".join(str(e) for e in raw_errors[:3])
                    error_detail = f"\n    raw errors: {combined}"
                ts = r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp)
                lines.append(
                    f"- [{r.severity}] {r.kind}/{resource_name} (ns: {r.namespace}) detected {ts}\n"
                    f"    problem: {r.problem}{error_detail}\n"
                    f"    fix: {r.solution}"
                )
            else:
                details = r.get("details", {}) if isinstance(r.get("details"), dict) else {}
                resource_name = details.get("resource_name", r.get("name", "?"))
                raw_errors = details.get("error", [])
                error_detail = ""
                if isinstance(raw_errors, list) and raw_errors:
                    combined = " | ".join(str(e) for e in raw_errors[:3])
                    error_detail = f"\n    raw errors: {combined}"
                lines.append(
                    f"- [{r.get('severity','?')}] {r.get('kind','?')}/{resource_name} (ns: {r.get('namespace','?')}) detected {r.get('timestamp','?')}\n"
                    f"    problem: {r.get('details','')}{error_detail}\n"
                    f"    fix: {r.get('solution','N/A')}"
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level helpers.
# ---------------------------------------------------------------------------

def _tool_call_key(tool_name: str, args: Dict[str, Any]) -> str:
    """Stable dedupe key for tool calls."""
    try:
        normalized = json.dumps(args or {}, sort_keys=True, default=str)
    except Exception:
        normalized = str(args)
    return f"{tool_name}:{normalized}"


def _parse_tool_result_for_summary(content: Any):
    """Parse ``TOOL_RESULT <name> args=<json> result=<json>`` strings."""
    if not isinstance(content, str):
        return None
    if not content.startswith("TOOL_RESULT "):
        return None

    rest = content[len("TOOL_RESULT "):]
    first_space = rest.find(" ")
    if first_space <= 0:
        return None

    tool_name = rest[:first_space]
    tail = rest[first_space + 1:]
    if not tail.startswith("args="):
        return None

    split_idx = tail.find(" result=")
    if split_idx <= len("args="):
        return None

    args_json = tail[len("args="):split_idx]
    result_json = tail[split_idx + len(" result="):]

    try:
        args = json.loads(args_json)
    except Exception:
        args = {}
    try:
        result = json.loads(result_json)
    except Exception:
        result = {"raw": result_json}

    return tool_name, args, result


def _major_minor_version(version: str) -> str:
    """Normalize a Kubernetes version to ``vMAJOR.MINOR`` form."""
    match = re.search(r"v?(\d+)\.(\d+)", version or "")
    if not match:
        return "unknown"
    return f"v{match.group(1)}.{match.group(2)}"


def _api_reference_url(version: str) -> str:
    major_minor = _major_minor_version(version)
    if major_minor == "unknown":
        return "https://kubernetes.io/docs/reference/generated/kubernetes-api/"
    return f"https://kubernetes.io/docs/reference/generated/kubernetes-api/{major_minor}/"
