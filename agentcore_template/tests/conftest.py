"""
Pytest configuration and fixtures for AgentCore template tests.

This module provides common test fixtures following AWS testing best practices:
- Mock AWS services
- Test data fixtures
- Configuration overrides
- Cleanup utilities
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(scope="session")
def aws_credentials():
    """
    Mock AWS credentials for testing.
    
    Prevents actual AWS API calls during tests.
    """
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_ssm_parameters() -> Dict[str, str]:
    """
    Mock SSM parameters for testing.
    
    Returns:
        Dict[str, str]: Dictionary of parameter names to values
    """
    return {
        "/app/myapp/agentcore/gateway_url": "https://mock-gateway.example.com",
        "/app/myapp/agentcore/memory_id": "mock-memory-id-123",
        "/app/myapp/agentcore/cognito_provider": "mock-cognito-provider",
        "/app/myapp/agentcore/userpool_id": "us-east-1_mockpool",
        "/app/myapp/agentcore/machine_client_id": "mock-client-id",
        "/app/myapp/agentcore/cognito_secret": "mock-secret",
        "/app/myapp/agentcore/cognito_domain": "mock-domain.auth.us-east-1.amazoncognito.com",
        "/app/myapp/knowledge_base/knowledge_base_id": "mock-kb-id",
    }


@pytest.fixture
def mock_boto3_client(mock_ssm_parameters):
    """
    Mock boto3 client for testing.
    
    Args:
        mock_ssm_parameters: SSM parameter fixtures
        
    Yields:
        Mock: Mocked boto3 client
    """
    with patch("boto3.client") as mock_client:
        # Mock SSM client
        ssm_mock = MagicMock()
        ssm_mock.get_parameter.side_effect = lambda Name, WithDecryption=True: {
            "Parameter": {"Value": mock_ssm_parameters.get(Name, "")}
        }
        
        # Mock STS client
        sts_mock = MagicMock()
        sts_mock.get_caller_identity.return_value = {"Account": "123456789012"}
        
        # Mock Cognito client
        cognito_mock = MagicMock()
        cognito_mock.describe_user_pool_client.return_value = {
            "UserPoolClient": {"ClientSecret": "mock-client-secret"}
        }
        cognito_mock.list_resource_servers.return_value = {
            "ResourceServers": [{"Identifier": "mock-resource-server"}]
        }
        
        def client_factory(service_name, *args, **kwargs):
            if service_name == "ssm":
                return ssm_mock
            elif service_name == "sts":
                return sts_mock
            elif service_name == "cognito-idp":
                return cognito_mock
            return MagicMock()
        
        mock_client.side_effect = client_factory
        yield mock_client


@pytest.fixture
def mock_boto3_session():
    """
    Mock boto3 session for testing.
    
    Yields:
        Mock: Mocked boto3 session
    """
    with patch("boto3.session.Session") as mock_session:
        session_instance = MagicMock()
        session_instance.region_name = "us-east-1"
        mock_session.return_value = session_instance
        yield mock_session


@pytest.fixture
def sample_agent_config() -> Dict[str, Any]:
    """
    Sample agent configuration for testing.
    
    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    return {
        "app_prefix": "testapp",
        "bedrock_model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "max_retries": 2,
        "timeout_seconds": 60,
        "enable_observability": True,
        "log_level": "DEBUG",
    }


@pytest.fixture
def sample_user_query() -> str:
    """
    Sample user query for testing.
    
    Returns:
        str: Sample query string
    """
    return "What is the weather today?"


@pytest.fixture
def mock_bearer_token() -> str:
    """
    Mock OAuth bearer token for testing.
    
    Returns:
        str: Mock token string
    """
    return "mock-bearer-token-123456"


@pytest.fixture
def mock_memory_hook():
    """
    Mock memory hook for testing.
    
    Returns:
        Mock: Mocked memory hook instance
    """
    mock_hook = MagicMock()
    mock_hook.on_start = MagicMock()
    mock_hook.on_end = MagicMock()
    return mock_hook


@pytest.fixture
def mock_mcp_client():
    """
    Mock MCP client for testing.
    
    Returns:
        Mock: Mocked MCP client
    """
    with patch("strands.tools.mcp.MCPClient") as mock_client:
        client_instance = MagicMock()
        client_instance.start = MagicMock()
        client_instance.list_tools_sync.return_value = []
        mock_client.return_value = client_instance
        yield mock_client


@pytest.fixture
def mock_bedrock_model():
    """
    Mock Bedrock model for testing.
    
    Returns:
        Mock: Mocked Bedrock model
    """
    with patch("strands.models.BedrockModel") as mock_model:
        model_instance = MagicMock()
        mock_model.return_value = model_instance
        yield mock_model


@pytest.fixture
def mock_agent():
    """
    Mock Strands agent for testing.
    
    Returns:
        Mock: Mocked agent
    """
    with patch("strands.Agent") as mock_agent_class:
        agent_instance = MagicMock()
        agent_instance.__call__.return_value = "Mock agent response"
        
        async def mock_stream():
            yield {"data": "Mock streaming response"}
        
        agent_instance.stream_async.return_value = mock_stream()
        mock_agent_class.return_value = agent_instance
        yield mock_agent_class


@pytest.fixture(autouse=True)
def reset_environment():
    """
    Reset environment variables after each test.
    
    This fixture runs automatically for every test.
    """
    # Store original environment
    original_env = os.environ.copy()
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def capture_logs(caplog):
    """
    Capture log output for assertions.
    
    Args:
        caplog: Pytest's built-in log capture fixture
        
    Returns:
        caplog: Log capture fixture
    """
    import logging
    caplog.set_level(logging.DEBUG)
    return caplog


# Test markers
def pytest_configure(config):
    """Register custom test markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require AWS services"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that may require AWS services"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests that take significant time to run"
    )
    config.addinivalue_line(
        "markers", "aws: Tests that interact with AWS services"
    )
