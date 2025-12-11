# Troubleshooting Guide

This guide helps diagnose and resolve common issues when working with the AgentCore template for healthcare and life sciences agents.

## Table of Contents

- [Common Issues](#common-issues)
- [Error Messages](#error-messages)
- [Debugging Tools](#debugging-tools)
- [Health Checks](#health-checks)
- [AWS Service Issues](#aws-service-issues)
- [Performance Issues](#performance-issues)
- [Getting Help](#getting-help)

## Common Issues

### 1. Agent Initialization Fails

**Symptoms**:
- Error during agent startup
- "Gateway client initialization failed" message
- "Bedrock model initialization failed" message

**Possible Causes**:
1. Missing or invalid SSM parameters
2. Insufficient IAM permissions
3. Invalid bearer token
4. Network connectivity issues

**Solutions**:

1. **Verify SSM Parameters**:
```bash
# List all SSM parameters for your app
./scripts/list_ssm_parameters.sh

# Manually verify a specific parameter
aws ssm get-parameter --name /app/myapp/agentcore/gateway_url
```

2. **Check IAM Permissions**:
```bash
# Verify your AWS credentials
aws sts get-caller-identity

# Test SSM access
aws ssm describe-parameters --max-results 1
```

3. **Validate Configuration**:
```python
from agent.agent_config.config import get_config

config = get_config()
print(config.to_dict())
```

4. **Run Health Checks**:
```python
from agent.agent_config.health import perform_health_checks

health = perform_health_checks()
print(health)
```

### 2. Gateway Connection Issues

**Symptoms**:
- "Gateway connectivity failed" in health checks
- Timeout errors when calling gateway
- 401/403 errors from gateway

**Solutions**:

1. **Verify Bearer Token**:
```python
from tests.test_gateway import get_gateway_access_token
import asyncio

# Test token retrieval
token = asyncio.run(get_gateway_access_token())
print(f"Token length: {len(token)}")
```

2. **Check Gateway URL**:
```bash
# Verify gateway URL is correct
aws ssm get-parameter --name /app/myapp/agentcore/gateway_url

# Test connectivity
curl -I https://your-gateway-url
```

3. **Validate Cognito Configuration**:
```bash
# Check Cognito user pool
aws cognito-idp describe-user-pool \
  --user-pool-id $(aws ssm get-parameter --name /app/myapp/agentcore/userpool_id --query 'Parameter.Value' --output text)
```

### 3. Memory Service Issues

**Symptoms**:
- Memory not persisting between sessions
- "Memory service unavailable" errors
- Context not being maintained

**Solutions**:

1. **Test Memory Service**:
```bash
python tests/test_memory.py list-memory
```

2. **Verify Memory ID**:
```bash
aws ssm get-parameter --name /app/myapp/agentcore/memory_id
```

3. **Check OpenSearch/Memory Backend**:
```python
from scripts.utils import get_ssm_parameter

memory_id = get_ssm_parameter("/app/myapp/agentcore/memory_id")
print(f"Memory ID: {memory_id}")
```

### 4. Model Invocation Errors

**Symptoms**:
- "Model not found" errors
- "Access denied" to Bedrock model
- Timeout errors during inference

**Solutions**:

1. **Verify Model Access**:
```bash
# List available models
aws bedrock list-foundation-models --region us-east-1

# Check specific model access
aws bedrock get-foundation-model \
  --model-identifier us.anthropic.claude-3-7-sonnet-20250219-v1:0 \
  --region us-east-1
```

2. **Request Model Access**:
- Navigate to Amazon Bedrock console
- Go to "Model access"
- Request access to required models

3. **Check Region Configuration**:
```bash
# Verify your region
aws configure get region

# Or check environment
echo $AWS_DEFAULT_REGION
```

### 5. Streamlit UI Issues

**Symptoms**:
- UI not loading
- Authentication failures
- Connection errors

**Solutions**:

1. **Check Port Availability**:
```bash
# Verify port 8501 is available
lsof -i :8501

# Or use netstat
netstat -an | grep 8501
```

2. **Verify Agent Runtime**:
```bash
# List deployed runtimes
agentcore list

# Check specific runtime status
agentcore describe --name myapp<AgentName>
```

3. **Test with IAM Authentication**:
```bash
# Use IAM-based app first
streamlit run app.py --server.port 8501
```

4. **Debug OAuth Issues**:
```bash
# Use OAuth-based app
streamlit run app_oauth.py --server.port 8501 -- --agent=myapp<AgentName>
```

## Error Messages

### `ValidationError: Parameter name cannot be empty`

**Cause**: Attempting to access SSM parameter with empty name.

**Solution**: Check that all required configuration values are set.

```python
from agent.agent_config.config import get_config

config = get_config()
# Ensure config.gateway_url_param is set
```

### `RuntimeError: Gateway client initialization failed`

**Cause**: Cannot connect to or initialize the MCP gateway client.

**Solutions**:
1. Verify gateway URL is accessible
2. Check bearer token is valid
3. Ensure network connectivity
4. Review gateway logs

### `ClientError: ParameterNotFound`

**Cause**: Required SSM parameter does not exist.

**Solution**: Create the missing parameter:

```bash
aws ssm put-parameter \
  --name /app/myapp/agentcore/gateway_url \
  --value "https://your-gateway-url" \
  --type String
```

### `ThrottlingException`

**Cause**: AWS API rate limits exceeded.

**Solution**: The retry logic will automatically handle this, but you can:
1. Reduce request frequency
2. Request a service quota increase
3. Implement caching

### `TimeoutError`

**Cause**: Operation exceeded timeout threshold.

**Solutions**:
1. Increase timeout value:
```python
from agent.agent_config.config import AgentConfig

config = AgentConfig(timeout_seconds=600)
```

2. Check network latency
3. Verify service availability

## Debugging Tools

### 1. Enable Debug Logging

```bash
# Set environment variable
export LOG_LEVEL=DEBUG

# Or in code
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 2. Use Health Check System

```python
from agent.agent_config.health import HealthChecker

checker = HealthChecker()
checker.check_ssm_connectivity()
checker.check_bedrock_availability()
checker.check_memory_availability()

health = checker.get_overall_health()
print(health)
```

### 3. Test Individual Components

```bash
# Test gateway
python tests/test_gateway.py --prompt "Hello"

# Test memory
python tests/test_memory.py list-memory

# Test agent
python tests/test_agent.py myapp<AgentName> -p "Hi"
```

### 4. Check CloudWatch Logs

```bash
# List log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda

# Tail logs
aws logs tail /aws/lambda/your-function-name --follow
```

### 5. Use Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use ipdb for better interface
import ipdb; ipdb.set_trace()
```

## Health Checks

### Comprehensive Health Check

```python
from agent.agent_config.health import perform_health_checks

# Basic health checks
health = perform_health_checks()

# With gateway check
health = perform_health_checks(
    include_gateway=True,
    gateway_url="https://your-gateway-url",
    bearer_token="your-token"
)

# Interpret results
if health["status"] == "unhealthy":
    for check in health["checks"]:
        if check["status"] == "unhealthy":
            print(f"Component {check['component']} is unhealthy: {check['message']}")
```

### Component-Specific Checks

```python
from agent.agent_config.health import HealthChecker

checker = HealthChecker()

# Check SSM
ssm_health = checker.check_ssm_connectivity()
print(ssm_health.to_dict())

# Check Bedrock
bedrock_health = checker.check_bedrock_availability()
print(bedrock_health.to_dict())
```

## AWS Service Issues

### SSM Parameter Store

**Issue**: Parameters not accessible

**Debug Steps**:
```bash
# 1. Verify IAM permissions
aws iam get-user

# 2. List parameters
aws ssm describe-parameters

# 3. Check specific parameter
aws ssm get-parameter --name /app/myapp/agentcore/gateway_url

# 4. Test parameter creation
aws ssm put-parameter \
  --name /app/test/param \
  --value "test" \
  --type String
```

### Amazon Bedrock

**Issue**: Model access denied

**Debug Steps**:
```bash
# 1. Check model access status
aws bedrock list-foundation-models

# 2. Verify region
aws bedrock get-foundation-model \
  --model-identifier us.anthropic.claude-3-7-sonnet-20250219-v1:0 \
  --region us-east-1

# 3. Check IAM permissions
aws iam get-role --role-name YourBedrockRole
```

### Amazon Cognito

**Issue**: Authentication failures

**Debug Steps**:
```bash
# 1. Describe user pool
aws cognito-idp describe-user-pool \
  --user-pool-id your-pool-id

# 2. List user pool clients
aws cognito-idp list-user-pool-clients \
  --user-pool-id your-pool-id

# 3. Check resource servers
aws cognito-idp list-resource-servers \
  --user-pool-id your-pool-id
```

## Performance Issues

### Slow Response Times

**Debug Steps**:

1. **Check Latency Metrics**:
```python
from agent.agent_config.health import HealthChecker
import time

checker = HealthChecker()
start = time.time()
result = checker.check_component("test", lambda: True)
print(f"Latency: {result.latency_ms}ms")
```

2. **Enable Performance Profiling**:
```python
import cProfile
import pstats

# Profile agent invocation
profiler = cProfile.Profile()
profiler.enable()

# Your code here
response = agent.invoke("test query")

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

3. **Check Network Latency**:
```bash
# Ping gateway
ping your-gateway-domain

# Test HTTP latency
curl -w "@curl-format.txt" -o /dev/null -s https://your-gateway-url
```

### Memory Leaks

**Debug Steps**:

1. **Monitor Memory Usage**:
```python
import tracemalloc

tracemalloc.start()

# Your code here

current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 10**6}MB, Peak: {peak / 10**6}MB")
tracemalloc.stop()
```

2. **Use Memory Profiler**:
```bash
pip install memory_profiler

# Add @profile decorator to functions
python -m memory_profiler your_script.py
```

## Getting Help

### 1. Check Logs

```bash
# Application logs
tail -f logs/application.log

# CloudWatch Logs
aws logs tail /aws/lambda/function-name --follow
```

### 2. Enable Verbose Output

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 3. Run Diagnostics

```bash
# Run health checks
python -c "from agent.agent_config.health import perform_health_checks; import json; print(json.dumps(perform_health_checks(), indent=2))"

# Test configuration
python -c "from agent.agent_config.config import get_config; print(get_config().to_dict())"
```

### 4. Collect System Information

```bash
# Python environment
python --version
pip list

# AWS CLI
aws --version
aws configure list

# System info
uname -a
```

### 5. Contact Support

When reporting issues, include:
- Error messages (full stack trace)
- Health check results
- Configuration (sanitized, no secrets)
- Steps to reproduce
- Expected vs actual behavior
- Environment information

### Useful Commands Summary

```bash
# Quick diagnostic script
cat << 'EOF' > diagnose.sh
#!/bin/bash
echo "=== System Info ==="
python --version
aws --version

echo -e "\n=== AWS Identity ==="
aws sts get-caller-identity

echo -e "\n=== SSM Parameters ==="
./scripts/list_ssm_parameters.sh

echo -e "\n=== Health Check ==="
python -c "from agent.agent_config.health import perform_health_checks; import json; print(json.dumps(perform_health_checks(), indent=2))"

echo -e "\n=== Configuration ==="
python -c "from agent.agent_config.config import get_config; print(get_config().to_dict())"
EOF

chmod +x diagnose.sh
./diagnose.sh
```

## Additional Resources

- [AWS Documentation](https://docs.aws.amazon.com/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Strands Documentation](https://strandsagents.com/)
- [Project README](README.md)
- [Best Practices Guide](BEST_PRACTICES.md)
