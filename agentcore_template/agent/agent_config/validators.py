"""
Input validation module for AgentCore template.

This module provides validation utilities following AWS security best practices:
- Input sanitization
- Parameter validation
- Security checks
- Type validation
"""

import re
import logging
from typing import Any, Optional, List, Dict
from functools import wraps

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_string_length(
    value: str,
    min_length: int = 1,
    max_length: int = 10000,
    field_name: str = "input"
) -> str:
    """
    Validate string length.
    
    Args:
        value: String to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        field_name: Field name for error messages
        
    Returns:
        str: Validated string
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    if len(value) < min_length:
        raise ValidationError(
            f"{field_name} must be at least {min_length} characters long"
        )
    
    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} must not exceed {max_length} characters"
        )
    
    return value


def validate_not_empty(value: str, field_name: str = "input") -> str:
    """
    Validate that string is not empty or whitespace-only.
    
    Args:
        value: String to validate
        field_name: Field name for error messages
        
    Returns:
        str: Validated string
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    if not value.strip():
        raise ValidationError(f"{field_name} cannot be empty")
    
    return value


def validate_alphanumeric(
    value: str,
    allow_spaces: bool = False,
    allow_hyphens: bool = False,
    allow_underscores: bool = False,
    field_name: str = "input"
) -> str:
    """
    Validate that string contains only alphanumeric characters.
    
    Args:
        value: String to validate
        allow_spaces: Allow space characters
        allow_hyphens: Allow hyphen characters
        allow_underscores: Allow underscore characters
        field_name: Field name for error messages
        
    Returns:
        str: Validated string
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    # Build regex pattern
    pattern = r'^[a-zA-Z0-9'
    if allow_spaces:
        pattern += r'\s'
    if allow_hyphens:
        pattern += r'\-'
    if allow_underscores:
        pattern += r'_'
    pattern += r']+$'
    
    if not re.match(pattern, value):
        raise ValidationError(
            f"{field_name} contains invalid characters. "
            f"Only alphanumeric characters"
            f"{' and spaces' if allow_spaces else ''}"
            f"{' and hyphens' if allow_hyphens else ''}"
            f"{' and underscores' if allow_underscores else ''} are allowed."
        )
    
    return value


def validate_ssm_parameter_name(value: str) -> str:
    """
    Validate SSM parameter name format.
    
    SSM parameter names must:
    - Start with a forward slash
    - Contain only alphanumeric, hyphens, underscores, periods, and forward slashes
    - Not exceed 2048 characters
    
    Args:
        value: Parameter name to validate
        
    Returns:
        str: Validated parameter name
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError("SSM parameter name must be a string")
    
    if not value.startswith("/"):
        raise ValidationError("SSM parameter name must start with '/'")
    
    if len(value) > 2048:
        raise ValidationError("SSM parameter name must not exceed 2048 characters")
    
    # Check for valid characters
    if not re.match(r'^[a-zA-Z0-9/_.-]+$', value):
        raise ValidationError(
            "SSM parameter name contains invalid characters. "
            "Only alphanumeric, hyphens, underscores, periods, and forward slashes are allowed."
        )
    
    return value


def validate_model_id(value: str) -> str:
    """
    Validate Bedrock model ID format.
    
    Args:
        value: Model ID to validate
        
    Returns:
        str: Validated model ID
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError("Model ID must be a string")
    
    if not value.strip():
        raise ValidationError("Model ID cannot be empty")
    
    # Basic validation for common model ID patterns
    # e.g., "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    if not re.match(r'^[a-zA-Z0-9._:-]+$', value):
        raise ValidationError(
            "Model ID contains invalid characters. "
            "Only alphanumeric, periods, underscores, colons, and hyphens are allowed."
        )
    
    return value


def validate_url(value: str, require_https: bool = True) -> str:
    """
    Validate URL format.
    
    Args:
        value: URL to validate
        require_https: Require HTTPS protocol
        
    Returns:
        str: Validated URL
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError("URL must be a string")
    
    if not value.strip():
        raise ValidationError("URL cannot be empty")
    
    # Basic URL validation
    url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    if not re.match(url_pattern, value, re.IGNORECASE):
        raise ValidationError("Invalid URL format")
    
    if require_https and not value.lower().startswith('https://'):
        raise ValidationError("URL must use HTTPS protocol")
    
    return value


def validate_bearer_token(value: str) -> str:
    """
    Validate OAuth bearer token format.
    
    Args:
        value: Bearer token to validate
        
    Returns:
        str: Validated token
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError("Bearer token must be a string")
    
    if not value.strip():
        raise ValidationError("Bearer token cannot be empty")
    
    # Tokens should be reasonably long
    if len(value) < 20:
        raise ValidationError("Bearer token appears to be too short")
    
    # Check for basic base64-like characters (common in JWT)
    if not re.match(r'^[A-Za-z0-9_\-\.=]+$', value):
        logger.warning("Bearer token contains unexpected characters")
    
    return value


def sanitize_user_input(value: str, max_length: int = 10000) -> str:
    """
    Sanitize user input by removing potential injection attempts.
    
    Args:
        value: User input to sanitize
        max_length: Maximum allowed length
        
    Returns:
        str: Sanitized input
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError("User input must be a string")
    
    # Remove null bytes
    value = value.replace('\x00', '')
    
    # Trim to max length
    if len(value) > max_length:
        logger.warning(f"User input truncated from {len(value)} to {max_length} characters")
        value = value[:max_length]
    
    # Log suspicious patterns
    suspicious_patterns = [
        r'<script',
        r'javascript:',
        r'onerror=',
        r'onclick=',
        r'eval\(',
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            logger.warning(f"Suspicious pattern detected in user input: {pattern}")
    
    return value


def validate_json_structure(data: Any, required_keys: Optional[List[str]] = None) -> Dict:
    """
    Validate JSON structure.
    
    Args:
        data: Data to validate
        required_keys: List of required keys (for dict validation)
        
    Returns:
        Dict: Validated dictionary
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError("Data must be a dictionary")
    
    if required_keys:
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            raise ValidationError(f"Missing required keys: {', '.join(missing_keys)}")
    
    return data


def validate_positive_integer(value: Any, field_name: str = "value") -> int:
    """
    Validate that value is a positive integer.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        
    Returns:
        int: Validated integer
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be an integer")
    
    if int_value <= 0:
        raise ValidationError(f"{field_name} must be positive")
    
    return int_value


def validate_non_negative_integer(value: Any, field_name: str = "value") -> int:
    """
    Validate that value is a non-negative integer.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        
    Returns:
        int: Validated integer
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be an integer")
    
    if int_value < 0:
        raise ValidationError(f"{field_name} must be non-negative")
    
    return int_value


def requires_validation(*validators):
    """
    Decorator to apply validation to function arguments.
    
    Args:
        *validators: Tuple of (param_name, validator_func) pairs
        
    Example:
        @requires_validation(
            ('name', lambda x: validate_not_empty(x, 'name')),
            ('age', lambda x: validate_positive_integer(x, 'age'))
        )
        def create_user(name: str, age: int):
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get function signature
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Apply validators
            for param_name, validator_func in validators:
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    try:
                        validated_value = validator_func(value)
                        bound_args.arguments[param_name] = validated_value
                    except ValidationError as e:
                        logger.error(f"Validation failed for {param_name}: {e}")
                        raise
            
            return func(*bound_args.args, **bound_args.kwargs)
        
        return wrapper
    return decorator
