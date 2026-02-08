"""
Unit tests for input sanitizer.
"""
import pytest
from input_sanitizer import InputSanitizer


class TestQueryValidation:
    """Test cases for query validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_valid_query(self):
        """Test validation of valid queries."""
        valid_queries = [
            "Why is my pod crashing?",
            "Show me the deployments in the default namespace",
            "What's wrong with the ingress controller?",
            "Check the status of my-app deployment",
            "List all pods in the kube-system namespace"
        ]
        
        for query in valid_queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is True
            assert error is None
    
    def test_empty_query(self):
        """Test validation of empty queries."""
        is_valid, error = self.sanitizer.validate_query("")
        
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_whitespace_only_query(self):
        """Test validation of whitespace-only queries."""
        is_valid, error = self.sanitizer.validate_query("   \n\t  ")
        
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_query_too_long(self):
        """Test validation of overly long queries."""
        long_query = "a" * 2001
        is_valid, error = self.sanitizer.validate_query(long_query)
        
        assert is_valid is False
        assert "too long" in error.lower()
        assert "2000" in error
    
    def test_query_at_max_length(self):
        """Test validation of query at maximum length."""
        max_query = "a" * 2000
        is_valid, error = self.sanitizer.validate_query(max_query)
        
        assert is_valid is True
        assert error is None


class TestShellCommandBlocking:
    """Test cases for blocking shell commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_block_shebang(self):
        """Test blocking of shebang patterns."""
        queries = [
            "#!/bin/bash\necho 'hello'",
            "#!/bin/sh\nls -la"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert "shell" in error.lower() or "command" in error.lower()
    
    def test_block_command_substitution(self):
        """Test blocking of command substitution."""
        queries = [
            "Show me $(kubectl get pods)",
            "What is `cat /etc/passwd`",
            "Run $(rm -rf /)"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert error is not None
    
    def test_block_shell_with_c_flag(self):
        """Test blocking of shell -c execution."""
        queries = [
            "bash -c 'kubectl delete pod'",
            "sh -c 'rm -rf /'",
            "zsh -c 'echo hello'"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
    
    def test_block_destructive_commands(self):
        """Test blocking of destructive kubectl/docker/helm commands."""
        queries = [
            "kubectl delete pod my-pod",
            "docker remove container",
            "helm delete my-release",
            "aws destroy infrastructure"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert "destructive" in error.lower() or "cannot execute" in error.lower()
    
    def test_allow_non_destructive_commands_in_text(self):
        """Test that non-destructive command mentions are allowed."""
        queries = [
            "How do I use kubectl to get pods?",
            "What does the helm list command show?",
            "Explain the docker ps command"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is True


class TestCodeInjectionBlocking:
    """Test cases for blocking code injection."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_block_eval_exec(self):
        """Test blocking of eval/exec patterns."""
        queries = [
            "eval('print(hello)')",
            "exec('import os')",
            "system('ls -la')",
            "subprocess.call(['rm', '-rf', '/'])"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert "code" in error.lower() or "execution" in error.lower()
    
    def test_block_os_imports(self):
        """Test blocking of OS module imports."""
        queries = [
            "import os",
            "from os import system",
            "import subprocess",
            "__import__('os')"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
    
    def test_block_dockerfile_commands(self):
        """Test blocking of Dockerfile syntax."""
        queries = [
            "FROM ubuntu:20.04",
            "RUN apt-get update",
            "CMD ['/bin/bash']",
            "ENTRYPOINT ['python', 'app.py']"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert "dockerfile" in error.lower() or "natural language" in error.lower()


class TestSQLInjectionBlocking:
    """Test cases for blocking SQL injection."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_block_sql_injection_patterns(self):
        """Test blocking of SQL injection patterns."""
        queries = [
            "' OR '1'='1",
            "; DROP TABLE users",
            "; DELETE FROM pods",
            "UNION SELECT * FROM secrets"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert "sql" in error.lower()


class TestCredentialAccessBlocking:
    """Test cases for blocking credential access attempts."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_block_password_file_access(self):
        """Test blocking of password file access."""
        queries = [
            "Show me /etc/passwd",
            "What's in /etc/shadow",
            "Read the .aws/credentials file",
            "Display .kube/config"
        ]
        
        for query in queries:
            is_valid, error = self.sanitizer.validate_query(query)
            assert is_valid is False
            assert "credential" in error.lower() or "sensitive" in error.lower()
    
    def test_block_aws_key_patterns(self):
        """Test blocking of AWS access key patterns."""
        query = "My key is AKIAIOSFODNN7EXAMPLE"
        is_valid, error = self.sanitizer.validate_query(query)
        
        assert is_valid is False
    
    def test_block_private_keys(self):
        """Test blocking of private key patterns."""
        query = "-----BEGIN RSA PRIVATE KEY-----"
        is_valid, error = self.sanitizer.validate_query(query)
        
        assert is_valid is False


class TestLogSanitization:
    """Test cases for log sanitization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_sanitize_aws_access_key(self):
        """Test sanitization of AWS access keys."""
        text = "My access key is AKIAIOSFODNN7EXAMPLE"
        sanitized = self.sanitizer.sanitize_for_logging(text)
        
        assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
        assert "[REDACTED]" in sanitized
    
    def test_sanitize_jwt_token(self):
        """Test sanitization of JWT tokens."""
        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        sanitized = self.sanitizer.sanitize_for_logging(text)
        
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "[REDACTED]" in sanitized
    
    def test_sanitize_github_token(self):
        """Test sanitization of GitHub tokens."""
        text = "GitHub token: ghp_1234567890abcdefghijklmnopqrstuv"
        sanitized = self.sanitizer.sanitize_for_logging(text)
        
        assert "ghp_" not in sanitized
        assert "[REDACTED]" in sanitized
    
    def test_sanitize_openai_key(self):
        """Test sanitization of OpenAI API keys."""
        text = "OpenAI key: sk-1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"
        sanitized = self.sanitizer.sanitize_for_logging(text)
        
        assert "sk-" not in sanitized
        assert "[REDACTED]" in sanitized
    
    def test_sanitize_preserves_safe_text(self):
        """Test that sanitization preserves safe text."""
        text = "This is a safe query about pods"
        sanitized = self.sanitizer.sanitize_for_logging(text)
        
        assert sanitized == text


class TestAWSCredentialValidation:
    """Test cases for AWS credential format validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_valid_aws_credentials(self):
        """Test validation of valid AWS credentials."""
        is_valid, error = self.sanitizer.validate_aws_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            session_token="FwoGZXIvYXdzEBQaDH..."
        )
        
        assert is_valid is True
        assert error is None
    
    def test_invalid_access_key_format(self):
        """Test validation of invalid access key format."""
        is_valid, error = self.sanitizer.validate_aws_credentials(
            access_key="INVALID_KEY",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            session_token="FwoGZXIvYXdzEBQaDH..."
        )
        
        assert is_valid is False
        assert "access key" in error.lower()
        assert "AKIA" in error
    
    def test_invalid_secret_key_length(self):
        """Test validation of invalid secret key length."""
        is_valid, error = self.sanitizer.validate_aws_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="too_short",
            session_token="FwoGZXIvYXdzEBQaDH..."
        )
        
        assert is_valid is False
        assert "secret key" in error.lower()
        assert "40" in error
    
    def test_invalid_session_token_length(self):
        """Test validation of invalid session token length."""
        is_valid, error = self.sanitizer.validate_aws_credentials(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            session_token="short"
        )
        
        assert is_valid is False
        assert "session token" in error.lower()


class TestResourceNameExtraction:
    """Test cases for resource name extraction."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sanitizer = InputSanitizer()
    
    def test_extract_pod_names(self):
        """Test extraction of pod names from queries."""
        query = "Why is pod my-app-12345-abcde crashing?"
        resources = self.sanitizer.extract_resource_names(query)
        
        assert len(resources['pods']) > 0
        assert any('my-app' in pod or 'abcde' in pod for pod in resources['pods'])
    
    def test_extract_deployment_names(self):
        """Test extraction of deployment names from queries."""
        query = "Check the deployment my-deployment status"
        resources = self.sanitizer.extract_resource_names(query)
        
        assert 'my-deployment' in resources['deployments']
    
    def test_extract_service_names(self):
        """Test extraction of service names from queries."""
        query = "What's wrong with service my-service?"
        resources = self.sanitizer.extract_resource_names(query)
        
        assert 'my-service' in resources['services']
    
    def test_extract_namespace_names(self):
        """Test extraction of namespace names from queries."""
        queries = [
            "Show pods in namespace production",
            "List deployments in the staging namespace",
            "kubectl get pods -n kube-system"
        ]
        
        for query in queries:
            resources = self.sanitizer.extract_resource_names(query)
            assert len(resources['namespaces']) > 0
    
    def test_extract_multiple_resources(self):
        """Test extraction of multiple resource types."""
        query = "Why is pod my-pod in namespace production not connecting to service my-service?"
        resources = self.sanitizer.extract_resource_names(query)
        
        assert len(resources['pods']) > 0
        assert len(resources['services']) > 0
        assert len(resources['namespaces']) > 0
    
    def test_no_duplicates_in_extraction(self):
        """Test that extraction removes duplicates."""
        query = "pod my-pod and pod my-pod are both failing"
        resources = self.sanitizer.extract_resource_names(query)
        
        # Should only have unique pod names
        assert len(resources['pods']) == len(set(resources['pods']))
