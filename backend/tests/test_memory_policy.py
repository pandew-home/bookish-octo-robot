from __future__ import annotations

import pytest

from backend.memory.policy import is_durable_turn
from backend.memory.scrub import contains_high_risk_secret, is_safe, scrub


class TestIsDurableTurn:
    @pytest.mark.parametrize(
        "query,response",
        [
            ("How do I fix this pod?", "kubectl apply -f deployment.yaml " * 20),
            (
                "Scale the deployment",
                "You need to run kubectl scale --replicas=3 on the deployment " * 15,
            ),
        ],
    )
    def test_true_for_long_responses_with_keywords(self, query: str, response: str):
        assert is_durable_turn(query, response) is True

    @pytest.mark.parametrize("query", ["hi", "hello"])
    def test_false_for_short_greetings(self, query: str):
        assert is_durable_turn(query, "Hey there!") is False

    def test_false_for_ping_query(self):
        assert is_durable_turn("ping", "pong") is False

    def test_false_for_auth_failure_response(self):
        assert is_durable_turn("list pods", "auth failed") is False

    def test_true_for_short_response_with_remediation(self):
        assert is_durable_turn("deploy this", "run kubectl apply -f app.yaml") is True

    def test_false_for_empty_response(self):
        assert is_durable_turn("anything", "   ") is False


class TestScrubRedactText:
    def test_redacts_aws_akia_keys(self):
        text = "The key is AKIAIOSFODNN7EXAMPLE"
        result = scrub(text)

        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result

    def test_redacts_aws_asia_temp_keys(self):
        text = "Kion key ASIAIOSFODNN7EXAMPLE used here"
        result = scrub(text)
        assert "ASIAIOSFODNN7EXAMPLE" not in result
        assert contains_high_risk_secret(text) is True

    def test_redacts_bearer_tokens(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
        result = scrub(text)

        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "[REDACTED]" in result

    def test_redacts_password_values(self):
        text = "password=mySuperSecret123"
        result = scrub(text)

        assert "mySuperSecret123" not in result
        assert "[REDACTED]" in result

    def test_redacts_token_equals(self):
        text = "token=abc123secretvalue"
        result = scrub(text)

        assert "abc123secretvalue" not in result
        assert "[REDACTED]" in result

    def test_preserves_clean_text(self):
        text = "This is a normal message about kubernetes pods"
        result = scrub(text)

        assert result == text


class TestIsSafe:
    def test_true_for_clean_content(self):
        content = "Your deployment is running with 3 replicas"
        assert is_safe(content) is True

    def test_true_for_content_with_scrubbed_secrets(self):
        content = "The key is [REDACTED]"
        assert is_safe(content) is True

    def test_true_after_scrub_removes_aws_key(self):
        content = "Here is the access key: AKIAIOSFODNN7EXAMPLE"
        assert is_safe(scrub(content)) is True

    def test_true_after_scrub_removes_bearer(self):
        content = "Use Bearer eyJhbGciOiJIUzI1NiJ9 for auth"
        assert is_safe(scrub(content)) is True

    def test_false_for_unscrubbed_aws_key(self):
        content = "Here is the access key: AKIAIOSFODNN7EXAMPLE"
        assert is_safe(content) is False

    def test_false_for_unscrubbed_bearer(self):
        content = "Use Bearer eyJhbGciOiJIUzI1NiJ9 for auth"
        assert is_safe(content) is False
