"""
Health check and monitoring module for AgentCore template.

This module provides health check and system monitoring capabilities following AWS best practices:
- Health check endpoints
- System status monitoring
- Dependency checks
- Performance metrics
"""

import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """
    Result of a health check.
    
    Attributes:
        component: Name of the component checked
        status: Health status of the component
        message: Optional message describing the status
        latency_ms: Latency of the check in milliseconds
        timestamp: ISO timestamp of the check
        details: Additional details about the check
    """
    component: str
    status: HealthStatus
    message: Optional[str] = None
    latency_ms: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class HealthChecker:
    """
    Health checker for AgentCore components.
    
    This class manages health checks for various components and provides
    an aggregated health status.
    """
    
    def __init__(self):
        """Initialize health checker."""
        self.checks: List[HealthCheckResult] = []
        self.start_time = time.time()
        logger.info("HealthChecker initialized")
    
    def check_component(
        self,
        component_name: str,
        check_func: callable,
        timeout_seconds: int = 5
    ) -> HealthCheckResult:
        """
        Check health of a component.
        
        Args:
            component_name: Name of the component
            check_func: Function to execute for the check
            timeout_seconds: Timeout for the check
            
        Returns:
            HealthCheckResult: Result of the health check
        """
        logger.debug(f"Checking health of component: {component_name}")
        start_time = time.time()
        
        try:
            # Execute check function
            result = check_func()
            latency_ms = (time.time() - start_time) * 1000
            
            # Determine status based on result
            if result is True or (isinstance(result, dict) and result.get('healthy', False)):
                status = HealthStatus.HEALTHY
                message = "Component is healthy"
            elif isinstance(result, dict):
                status = HealthStatus(result.get('status', HealthStatus.UNKNOWN.value))
                message = result.get('message', 'No message provided')
            else:
                status = HealthStatus.UNKNOWN
                message = "Unknown health status"
            
            check_result = HealthCheckResult(
                component=component_name,
                status=status,
                message=message,
                latency_ms=latency_ms,
                details=result if isinstance(result, dict) else {}
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Health check failed for {component_name}: {e}")
            
            check_result = HealthCheckResult(
                component=component_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                latency_ms=latency_ms,
                details={"error": str(e)}
            )
        
        self.checks.append(check_result)
        return check_result
    
    def check_ssm_connectivity(self) -> HealthCheckResult:
        """
        Check connectivity to AWS Systems Manager.
        
        Returns:
            HealthCheckResult: Result of the SSM connectivity check
        """
        def check():
            import boto3
            from botocore.exceptions import ClientError
            
            try:
                ssm = boto3.client('ssm')
                # Try to describe parameters (doesn't require specific parameters to exist)
                ssm.describe_parameters(MaxResults=1)
                return {"healthy": True, "message": "SSM connectivity confirmed"}
            except ClientError as e:
                return {
                    "healthy": False,
                    "status": HealthStatus.UNHEALTHY.value,
                    "message": f"SSM connectivity failed: {e}"
                }
        
        return self.check_component("ssm_connectivity", check)
    
    def check_bedrock_availability(self) -> HealthCheckResult:
        """
        Check availability of Amazon Bedrock service.
        
        Returns:
            HealthCheckResult: Result of the Bedrock availability check
        """
        def check():
            import boto3
            from botocore.exceptions import ClientError
            
            try:
                bedrock = boto3.client('bedrock')
                # Try to list foundation models
                bedrock.list_foundation_models(byProvider='anthropic')
                return {"healthy": True, "message": "Bedrock service available"}
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code in ['AccessDeniedException', 'UnauthorizedException']:
                    # Service is available but we lack permissions (which is okay for health check)
                    return {"healthy": True, "message": "Bedrock service available (limited permissions)"}
                return {
                    "healthy": False,
                    "status": HealthStatus.UNHEALTHY.value,
                    "message": f"Bedrock availability check failed: {e}"
                }
        
        return self.check_component("bedrock_availability", check)
    
    def check_gateway_connectivity(self, gateway_url: str, bearer_token: str) -> HealthCheckResult:
        """
        Check connectivity to AgentCore Gateway.
        
        Args:
            gateway_url: Gateway URL to check
            bearer_token: Bearer token for authentication
            
        Returns:
            HealthCheckResult: Result of the gateway connectivity check
        """
        def check():
            import requests
            
            try:
                # Simple health check - adjust endpoint as needed
                response = requests.get(
                    gateway_url,
                    headers={"Authorization": f"Bearer {bearer_token}"},
                    timeout=5
                )
                
                if response.status_code < 500:
                    return {"healthy": True, "message": "Gateway is reachable"}
                else:
                    return {
                        "healthy": False,
                        "status": HealthStatus.DEGRADED.value,
                        "message": f"Gateway returned status {response.status_code}"
                    }
            except Exception as e:
                return {
                    "healthy": False,
                    "status": HealthStatus.UNHEALTHY.value,
                    "message": f"Gateway connectivity failed: {e}"
                }
        
        return self.check_component("gateway_connectivity", check)
    
    def check_memory_availability(self) -> HealthCheckResult:
        """
        Check availability of memory system.
        
        Returns:
            HealthCheckResult: Result of the memory availability check
        """
        def check():
            # Basic check - can be enhanced with actual memory system checks
            return {"healthy": True, "message": "Memory system initialized"}
        
        return self.check_component("memory_availability", check)
    
    def get_system_info(self) -> Dict[str, Any]:
        """
        Get system information.
        
        Returns:
            Dict containing system information
        """
        import platform
        import sys
        
        uptime_seconds = time.time() - self.start_time
        
        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": self._format_uptime(uptime_seconds),
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        
        return " ".join(parts)
    
    def get_overall_health(self) -> Dict[str, Any]:
        """
        Get overall health status.
        
        Returns:
            Dict containing overall health information
        """
        if not self.checks:
            return {
                "status": HealthStatus.UNKNOWN.value,
                "message": "No health checks performed",
                "checks": [],
                "system_info": self.get_system_info(),
            }
        
        # Determine overall status
        statuses = [check.status for check in self.checks]
        
        if all(status == HealthStatus.HEALTHY for status in statuses):
            overall_status = HealthStatus.HEALTHY
            message = "All components are healthy"
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            overall_status = HealthStatus.UNHEALTHY
            unhealthy_components = [
                check.component for check in self.checks 
                if check.status == HealthStatus.UNHEALTHY
            ]
            message = f"Unhealthy components: {', '.join(unhealthy_components)}"
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            overall_status = HealthStatus.DEGRADED
            message = "Some components are degraded"
        else:
            overall_status = HealthStatus.UNKNOWN
            message = "Unknown overall health status"
        
        return {
            "status": overall_status.value,
            "message": message,
            "checks": [check.to_dict() for check in self.checks],
            "system_info": self.get_system_info(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def clear_checks(self):
        """Clear all health check results."""
        self.checks.clear()
        logger.debug("Health check results cleared")


def perform_health_checks(
    include_gateway: bool = False,
    gateway_url: Optional[str] = None,
    bearer_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Perform all health checks and return results.
    
    Args:
        include_gateway: Whether to check gateway connectivity
        gateway_url: Gateway URL (required if include_gateway is True)
        bearer_token: Bearer token (required if include_gateway is True)
        
    Returns:
        Dict containing health check results
    """
    checker = HealthChecker()
    
    # Perform basic checks
    checker.check_ssm_connectivity()
    checker.check_bedrock_availability()
    checker.check_memory_availability()
    
    # Optionally check gateway
    if include_gateway and gateway_url and bearer_token:
        checker.check_gateway_connectivity(gateway_url, bearer_token)
    
    return checker.get_overall_health()
