"""SC-010 / T032: system prompt must not reintroduce dual-approval or anti-recommend rules."""
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"

# Phrases that must not return after constitution v3 / US3 cutover.
FORBIDDEN_SNIPPETS = [
    "do not recommend",
    "never recommend",
    "must not recommend",
    "refuse to recommend",
    "dual approval",
    "dual-approval",
    "require human approval",
    "require approval before",
    "type APPROVE",
    "say approve",
    "verbal approval",
    "multi-step approval",
    "cannot recommend",
    "ban recommendations",
    "save to knowledge base",
    "save to kb",
]


def test_system_prompt_exists():
    assert PROMPT_PATH.is_file(), f"missing system prompt at {PROMPT_PATH}"


def test_system_prompt_has_no_dual_approval_or_anti_recommend_language():
    text = PROMPT_PATH.read_text(encoding="utf-8").lower()
    for snippet in FORBIDDEN_SNIPPETS:
        assert snippet not in text, f"forbidden prompt language found: {snippet!r}"


def test_system_prompt_keeps_wrappers_only_and_live_first():
    text = PROMPT_PATH.read_text(encoding="utf-8").lower()
    assert "python kubernetes api" in text or "kubernetes api wrappers" in text
    assert "live" in text
    assert "memory_summary" in PROMPT_PATH.read_text(encoding="utf-8")
    assert "kb_summary" not in PROMPT_PATH.read_text(encoding="utf-8")


def test_system_prompt_allows_free_text_recommendations():
    text = PROMPT_PATH.read_text(encoding="utf-8").lower()
    assert "recommendation" in text
