# AWS Best Practices for Life Science Research Agents

This document outlines the best practices implemented in this AgentCore template, following AWS recommendations for building production-ready AI agents for healthcare and life sciences applications.

## Table of Contents

- [Security Best Practices](#security-best-practices)
- [Error Handling and Resilience](#error-handling-and-resilience)
- [Configuration Management](#configuration-management)
- [Observability and Monitoring](#observability-and-monitoring)
- [Testing Strategy](#testing-strategy)
- [Performance Optimization](#performance-optimization)
- [Code Quality](#code-quality)
- [Documentation Standards](#documentation-standards)

## Security Best Practices

### 1. Input Validation and Sanitization

**Implementation**: `agent/agent_config/validators.py`

- All user inputs are validated before processing
- String length limits enforced to prevent buffer overflow
- Special characters sanitized to prevent injection attacks
- SSM parameter names validated against AWS naming conventions
- Bearer tokens validated for proper format

**Example Usage**:
```python
from agent.agent_config.validators import validate_not_empty, sanitize_user_input

# Validate and sanitize user query
user_query = sanitize_user_input(raw_input, max_length=10000)
user_query = validate_not_empty(user_query, "user_query")
```

### 2. Secure Parameter Storage

- All sensitive configuration stored in AWS Systems Manager Parameter Store
- Secrets use SecureString type with KMS encryption
- No hardcoded credentials or API keys in code
- SSM parameters retrieved with retry logic and error handling

**Example**:
```python
from scripts.utils import put_ssm_parameter

# Store sensitive data securely
put_ssm_parameter(
    "/app/myapp/api_key",
    api_key_value,
    with_encryption=True
)
```

### 3. Least Privilege Access

- IAM roles configured with minimum required permissions
- Service-specific access policies
- No wildcard permissions in production
- Regular audit of IAM policies

### 4. Network Security

- All external connections use HTTPS
- Bearer token authentication for gateway access
- Support for VPC endpoints for AWS services
- Network isolation for sensitive workloads

## Error Handling and Resilience

### 1. Comprehensive Error Handling

**Implementation**: Enhanced error handling in `agent/agent_config/agent.py` and `scripts/utils.py`

- Try-catch blocks around all AWS service calls
- Specific exception types handled appropriately
- Proper error propagation with context
- User-friendly error messages without exposing internals

**Example**:
```python
try:
    response = agent.invoke(user_query)
except ValidationError as e:
    logger.error(f"Validation error: {e}")
    return "Invalid input provided"
except RuntimeError as e:
    logger.error(f"System error: {e}")
    return "System temporarily unavailable"
```

### 2. Retry Logic with Exponential Backoff

**Implementation**: `scripts/utils.py` - `@retry_with_backoff` decorator

- Automatic retry for transient failures
- Exponential backoff to prevent API throttling
- Maximum retry limit to prevent infinite loops
- Only retry on retryable errors (throttling, service unavailable)

**Configuration**:
```python
@retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
def aws_operation():
    # AWS service call
    pass
```

### 3. Graceful Degradation

- System continues operating with reduced functionality when non-critical components fail
- Clear indication of degraded state to users
- Fallback mechanisms for optional features
- Health checks to monitor component status

## Configuration Management

### 1. Centralized Configuration

**Implementation**: `agent/agent_config/config.py`

- Single source of truth for configuration
- Environment-based configuration support
- Configuration validation on initialization
- Type-safe configuration with dataclasses

**Usage**:
```python
from agent.agent_config.config import get_config

config = get_config()
model_id = config.bedrock_model_id
timeout = config.timeout_seconds
```

### 2. Environment Variable Support

All configuration can be overridden via environment variables:

```bash
export APP_PREFIX=myapp
export BEDROCK_MODEL_ID=us.anthropic.claude-3-7-sonnet-20250219-v1:0
export MAX_RETRIES=5
export TIMEOUT_SECONDS=300
export LOG_LEVEL=DEBUG
```

### 3. Configuration Validation

- All configuration values validated on initialization
- Type checking for all parameters
- Range validation for numeric values
- Format validation for strings (URLs, model IDs, etc.)

## Observability and Monitoring

### 1. Structured Logging

**Implementation**: Logging throughout all modules

- Consistent log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Contextual information in log messages
- No sensitive data in logs
- Correlation IDs for request tracking

**Best Practices**:
```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Processing request for user: {user_id}")
logger.debug(f"Query parameters: {sanitized_params}")
logger.error(f"Operation failed: {error}", exc_info=True)
```

### 2. Health Checks

**Implementation**: `agent/agent_config/health.py`

- Comprehensive health check system
- Component-level health monitoring
- Overall system health aggregation
- Performance metrics (latency, uptime)

**Usage**:
```python
from agent.agent_config.health import perform_health_checks

health_status = perform_health_checks(
    include_gateway=True,
    gateway_url=gateway_url,
    bearer_token=token
)

if health_status["status"] == "unhealthy":
    # Take corrective action
    pass
```

### 3. OpenTelemetry Integration

- OTEL console export enabled by default
- Distributed tracing support
- Custom spans for important operations
- Performance metrics collection

### 4. CloudWatch Integration

- Structured logs sent to CloudWatch Logs
- Custom metrics for business KPIs
- Alarms for critical conditions
- Dashboard for monitoring

## Testing Strategy

### 1. Comprehensive Test Coverage

**Implementation**: `tests/` directory with pytest framework

- Unit tests for individual functions
- Integration tests for component interactions
- Mock AWS services for testing
- Test fixtures for common scenarios

### 2. Test Organization

```
tests/
├── conftest.py          # Shared fixtures
├── test_utils.py        # Utils module tests
├── test_config.py       # Configuration tests
├── test_agent.py        # Agent tests
├── test_gateway.py      # Gateway integration tests
└── test_memory.py       # Memory tests
```

### 3. Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=agent --cov=scripts --cov-report=html

# Run only unit tests
pytest tests/ -m unit

# Run integration tests
pytest tests/ -m integration
```

### 4. Test Markers

- `@pytest.mark.unit`: Fast unit tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.slow`: Long-running tests
- `@pytest.mark.aws`: Tests requiring AWS services

## Performance Optimization

### 1. Timeout Configuration

- Configurable timeouts for all operations
- Prevents hanging requests
- Default timeout: 300 seconds (adjustable)

### 2. Connection Reuse

- Boto3 client reuse across requests
- Connection pooling for HTTP requests
- Session management for authentication

### 3. Async Operations

- Async streaming for real-time responses
- Non-blocking I/O operations
- Concurrent request handling

### 4. Caching Strategy

- SSM parameter caching (with TTL)
- Model response caching (where appropriate)
- Token caching with automatic refresh

## Code Quality

### 1. Type Hints

All functions include type hints for parameters and return values:

```python
def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    """Retrieve SSM parameter."""
    pass
```

### 2. Docstrings

All public functions and classes include comprehensive docstrings:

```python
def function_name(param1: str, param2: int) -> dict:
    """
    Brief description of function.
    
    Detailed description if needed.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ExceptionType: Description of when raised
    """
    pass
```

### 3. Code Formatting

- Follow PEP 8 style guidelines
- Use Black for automatic formatting
- Maximum line length: 100 characters
- Consistent naming conventions

### 4. Linting

Pre-commit checks configured:
```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Documentation Standards

### 1. README Files

Each major component includes a README with:
- Overview and purpose
- Prerequisites
- Installation instructions
- Usage examples
- Configuration options
- Troubleshooting guide

### 2. Code Comments

- Complex logic includes explanatory comments
- No redundant comments for obvious code
- TODO comments for future improvements
- FIXME comments for known issues

### 3. API Documentation

All public APIs documented with:
- Function/method signature
- Parameter descriptions
- Return value descriptions
- Usage examples
- Error conditions

## Deployment Best Practices

### 1. Infrastructure as Code

- CloudFormation templates for all resources
- Parameterized templates for different environments
- Stack outputs for resource references
- Change sets for safe updates

### 2. Environment Separation

- Separate AWS accounts for dev/staging/prod
- Environment-specific configuration
- Isolated resources per environment
- No cross-environment dependencies

### 3. Blue/Green Deployment

- Zero-downtime deployments
- Gradual traffic shifting
- Automatic rollback on errors
- Health checks before traffic switch

### 4. Backup and Recovery

- Regular backups of critical data
- Point-in-time recovery capability
- Disaster recovery plan documented
- Regular recovery testing

## Compliance and Governance

### 1. HIPAA Compliance (for healthcare data)

- Encryption at rest and in transit
- Access logging and auditing
- Data retention policies
- Business Associate Agreements

### 2. Data Privacy

- Minimal data collection
- Data anonymization where possible
- Clear data retention policies
- User consent management

### 3. Audit Logging

- All data access logged
- User actions tracked
- Configuration changes recorded
- Log retention per compliance requirements

## Additional Resources

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS Security Best Practices](https://docs.aws.amazon.com/security/)
- [Amazon Bedrock Best Practices](https://docs.aws.amazon.com/bedrock/latest/userguide/best-practices.html)
- [Healthcare and Life Sciences on AWS](https://aws.amazon.com/health/)

## Version History

- v1.0.0 - Initial best practices implementation
  - Error handling improvements
  - Configuration management
  - Input validation
  - Health checks
  - Comprehensive testing
  - Documentation standards
