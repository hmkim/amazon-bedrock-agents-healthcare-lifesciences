"""
Configuration management module for AgentCore template.

This module provides centralized configuration management following AWS best practices:
- Environment-based configuration
- Configuration validation
- Default values with overrides
- Type safety
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """
    Agent configuration with validation and defaults.
    
    Attributes:
        app_prefix: Application prefix for SSM parameters (default: "myapp")
        bedrock_model_id: Bedrock model identifier
        gateway_url_param: SSM parameter path for gateway URL
        memory_id_param: SSM parameter path for memory ID
        cognito_provider_param: SSM parameter path for Cognito provider
        max_retries: Maximum retry attempts for AWS operations
        timeout_seconds: Timeout for agent operations
        enable_observability: Enable OpenTelemetry observability
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    
    # Application configuration
    app_prefix: str = field(default_factory=lambda: os.getenv("APP_PREFIX", "myapp"))
    
    # Model configuration
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv(
            "BEDROCK_MODEL_ID",
            "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        )
    )
    
    # SSM Parameter paths
    gateway_url_param: Optional[str] = None
    memory_id_param: Optional[str] = None
    cognito_provider_param: Optional[str] = None
    userpool_id_param: Optional[str] = None
    machine_client_id_param: Optional[str] = None
    cognito_secret_param: Optional[str] = None
    cognito_domain_param: Optional[str] = None
    
    # Operation configuration
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv("TIMEOUT_SECONDS", "300")))
    
    # Observability configuration
    enable_observability: bool = field(
        default_factory=lambda: os.getenv("ENABLE_OBSERVABILITY", "true").lower() == "true"
    )
    enable_console_export: bool = field(
        default_factory=lambda: os.getenv("STRANDS_OTEL_ENABLE_CONSOLE_EXPORT", "true").lower() == "true"
    )
    tool_console_mode: str = field(
        default_factory=lambda: os.getenv("STRANDS_TOOL_CONSOLE_MODE", "enabled")
    )
    
    # Logging configuration
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    def __post_init__(self):
        """Validate configuration and set derived values."""
        # Set default SSM parameter paths based on app_prefix
        if not self.gateway_url_param:
            self.gateway_url_param = f"/app/{self.app_prefix}/agentcore/gateway_url"
        if not self.memory_id_param:
            self.memory_id_param = f"/app/{self.app_prefix}/agentcore/memory_id"
        if not self.cognito_provider_param:
            self.cognito_provider_param = f"/app/{self.app_prefix}/agentcore/cognito_provider"
        if not self.userpool_id_param:
            self.userpool_id_param = f"/app/{self.app_prefix}/agentcore/userpool_id"
        if not self.machine_client_id_param:
            self.machine_client_id_param = f"/app/{self.app_prefix}/agentcore/machine_client_id"
        if not self.cognito_secret_param:
            self.cognito_secret_param = f"/app/{self.app_prefix}/agentcore/cognito_secret"
        if not self.cognito_domain_param:
            self.cognito_domain_param = f"/app/{self.app_prefix}/agentcore/cognito_domain"
            
        # Validate configuration
        self._validate()
        
        logger.info(f"Configuration initialized with app_prefix: {self.app_prefix}")
    
    def _validate(self):
        """Validate configuration values."""
        if not self.app_prefix or not self.app_prefix.strip():
            raise ValueError("app_prefix cannot be empty")
        
        if not self.bedrock_model_id or not self.bedrock_model_id.strip():
            raise ValueError("bedrock_model_id cannot be empty")
        
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"log_level must be one of {valid_log_levels}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "app_prefix": self.app_prefix,
            "bedrock_model_id": self.bedrock_model_id,
            "gateway_url_param": self.gateway_url_param,
            "memory_id_param": self.memory_id_param,
            "cognito_provider_param": self.cognito_provider_param,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "enable_observability": self.enable_observability,
            "enable_console_export": self.enable_console_export,
            "tool_console_mode": self.tool_console_mode,
            "log_level": self.log_level,
        }
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """
        Create configuration from environment variables.
        
        Returns:
            AgentConfig: Configuration instance
        """
        return cls()
    
    def get_ssm_param_path(self, param_name: str) -> str:
        """
        Get full SSM parameter path for a given parameter name.
        
        Args:
            param_name: Short parameter name (e.g., 'gateway_url')
            
        Returns:
            str: Full SSM parameter path
        """
        return f"/app/{self.app_prefix}/agentcore/{param_name}"


# Global configuration instance
_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """
    Get the global configuration instance.
    
    Returns:
        AgentConfig: Global configuration
    """
    global _config
    if _config is None:
        _config = AgentConfig.from_env()
    return _config


def set_config(config: AgentConfig) -> None:
    """
    Set the global configuration instance.
    
    Args:
        config: Configuration to set as global
    """
    global _config
    _config = config


def reset_config() -> None:
    """Reset the global configuration instance."""
    global _config
    _config = None
