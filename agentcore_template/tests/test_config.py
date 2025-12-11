"""
Unit tests for configuration module.

Tests cover:
- Configuration initialization
- Environment variable handling
- Configuration validation
- Default values
"""

import pytest
import os
from unittest.mock import patch

# Import configuration classes
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agent.agent_config.config import AgentConfig, get_config, set_config, reset_config


@pytest.mark.unit
class TestAgentConfig:
    """Test AgentConfig class."""
    
    def test_default_initialization(self):
        """Test configuration with default values."""
        config = AgentConfig()
        
        assert config.app_prefix == "myapp"
        assert config.bedrock_model_id == "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        assert config.max_retries == 3
        assert config.timeout_seconds == 300
        assert config.enable_observability is True
        assert config.log_level == "INFO"
    
    def test_custom_initialization(self):
        """Test configuration with custom values."""
        config = AgentConfig(
            app_prefix="customapp",
            bedrock_model_id="custom-model-id",
            max_retries=5,
            timeout_seconds=600,
        )
        
        assert config.app_prefix == "customapp"
        assert config.bedrock_model_id == "custom-model-id"
        assert config.max_retries == 5
        assert config.timeout_seconds == 600
    
    def test_ssm_parameter_paths(self):
        """Test SSM parameter path generation."""
        config = AgentConfig(app_prefix="testapp")
        
        assert config.gateway_url_param == "/app/testapp/agentcore/gateway_url"
        assert config.memory_id_param == "/app/testapp/agentcore/memory_id"
        assert config.cognito_provider_param == "/app/testapp/agentcore/cognito_provider"
    
    def test_custom_ssm_parameter_paths(self):
        """Test custom SSM parameter paths."""
        config = AgentConfig(
            app_prefix="testapp",
            gateway_url_param="/custom/gateway/url"
        )
        
        assert config.gateway_url_param == "/custom/gateway/url"
    
    def test_validation_empty_app_prefix(self):
        """Test validation fails with empty app_prefix."""
        with pytest.raises(ValueError, match="app_prefix cannot be empty"):
            AgentConfig(app_prefix="")
    
    def test_validation_empty_model_id(self):
        """Test validation fails with empty model_id."""
        with pytest.raises(ValueError, match="bedrock_model_id cannot be empty"):
            AgentConfig(bedrock_model_id="")
    
    def test_validation_negative_retries(self):
        """Test validation fails with negative retries."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            AgentConfig(max_retries=-1)
    
    def test_validation_zero_timeout(self):
        """Test validation fails with zero timeout."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            AgentConfig(timeout_seconds=0)
    
    def test_validation_invalid_log_level(self):
        """Test validation fails with invalid log level."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            AgentConfig(log_level="INVALID")
    
    def test_to_dict(self):
        """Test configuration conversion to dictionary."""
        config = AgentConfig(app_prefix="testapp")
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert config_dict["app_prefix"] == "testapp"
        assert "bedrock_model_id" in config_dict
        assert "max_retries" in config_dict
    
    def test_from_env(self):
        """Test configuration from environment variables."""
        with patch.dict(os.environ, {
            "APP_PREFIX": "envapp",
            "BEDROCK_MODEL_ID": "env-model",
            "MAX_RETRIES": "5",
            "LOG_LEVEL": "DEBUG"
        }):
            config = AgentConfig.from_env()
            
            assert config.app_prefix == "envapp"
            assert config.bedrock_model_id == "env-model"
            assert config.max_retries == 5
            assert config.log_level == "DEBUG"
    
    def test_get_ssm_param_path(self):
        """Test SSM parameter path helper method."""
        config = AgentConfig(app_prefix="testapp")
        path = config.get_ssm_param_path("custom_param")
        
        assert path == "/app/testapp/agentcore/custom_param"
    
    def test_observability_flags(self):
        """Test observability configuration flags."""
        config = AgentConfig()
        
        assert config.enable_observability is True
        assert config.enable_console_export is True
        assert config.tool_console_mode == "enabled"
    
    def test_observability_from_env(self):
        """Test observability flags from environment."""
        with patch.dict(os.environ, {
            "ENABLE_OBSERVABILITY": "false",
            "STRANDS_OTEL_ENABLE_CONSOLE_EXPORT": "false",
            "STRANDS_TOOL_CONSOLE_MODE": "disabled"
        }):
            config = AgentConfig.from_env()
            
            assert config.enable_observability is False
            assert config.enable_console_export is False
            assert config.tool_console_mode == "disabled"


@pytest.mark.unit
class TestGlobalConfig:
    """Test global configuration management."""
    
    def setup_method(self):
        """Reset global config before each test."""
        reset_config()
    
    def test_get_config_creates_instance(self):
        """Test that get_config creates a config instance."""
        config = get_config()
        assert isinstance(config, AgentConfig)
    
    def test_get_config_returns_same_instance(self):
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2
    
    def test_set_config(self):
        """Test setting a custom global config."""
        custom_config = AgentConfig(app_prefix="custom")
        set_config(custom_config)
        
        retrieved_config = get_config()
        assert retrieved_config is custom_config
        assert retrieved_config.app_prefix == "custom"
    
    def test_reset_config(self):
        """Test resetting global config."""
        config1 = get_config()
        reset_config()
        config2 = get_config()
        
        assert config1 is not config2


@pytest.mark.unit
class TestConfigurationEdgeCases:
    """Test edge cases in configuration."""
    
    def test_whitespace_app_prefix(self):
        """Test that whitespace-only app_prefix is rejected."""
        with pytest.raises(ValueError, match="app_prefix cannot be empty"):
            AgentConfig(app_prefix="   ")
    
    def test_whitespace_model_id(self):
        """Test that whitespace-only model_id is rejected."""
        with pytest.raises(ValueError, match="bedrock_model_id cannot be empty"):
            AgentConfig(bedrock_model_id="   ")
    
    def test_case_insensitive_log_level(self):
        """Test that log level validation is case-insensitive."""
        # Should not raise
        config = AgentConfig(log_level="debug")
        assert config.log_level == "debug"
    
    def test_large_timeout_value(self):
        """Test that large timeout values are accepted."""
        config = AgentConfig(timeout_seconds=86400)  # 1 day
        assert config.timeout_seconds == 86400
    
    def test_zero_retries(self):
        """Test that zero retries is valid."""
        config = AgentConfig(max_retries=0)
        assert config.max_retries == 0
