"""
Unit tests for utility functions.

Tests cover:
- SSM parameter operations
- AWS service calls
- Error handling
- Retry logic
- Configuration file loading
"""

import pytest
import json
import yaml
import tempfile
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Import functions to test
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils import (
    get_ssm_parameter,
    put_ssm_parameter,
    delete_ssm_parameter,
    load_api_spec,
    get_aws_region,
    get_aws_account_id,
    get_cognito_client_secret,
    read_config,
)


@pytest.mark.unit
class TestSSMParameters:
    """Test SSM parameter operations."""
    
    def test_get_ssm_parameter_success(self, mock_boto3_client, mock_ssm_parameters):
        """Test successful SSM parameter retrieval."""
        result = get_ssm_parameter("/app/myapp/agentcore/gateway_url")
        assert result == mock_ssm_parameters["/app/myapp/agentcore/gateway_url"]
    
    def test_get_ssm_parameter_empty_name(self):
        """Test that empty parameter name raises ValueError."""
        with pytest.raises(ValueError, match="Parameter name cannot be empty"):
            get_ssm_parameter("")
    
    def test_get_ssm_parameter_not_found(self, mock_boto3_client):
        """Test handling of non-existent parameter."""
        ssm_mock = MagicMock()
        ssm_mock.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "ParameterNotFound"}},
            "GetParameter"
        )
        
        with patch("boto3.client", return_value=ssm_mock):
            with pytest.raises(ValueError, match="not found in SSM Parameter Store"):
                get_ssm_parameter("/app/myapp/nonexistent")
    
    def test_put_ssm_parameter_success(self, mock_boto3_client):
        """Test successful SSM parameter storage."""
        put_ssm_parameter("/app/myapp/test", "test_value")
        # Should not raise exception
    
    def test_put_ssm_parameter_empty_name(self):
        """Test that empty parameter name raises ValueError."""
        with pytest.raises(ValueError, match="Parameter name cannot be empty"):
            put_ssm_parameter("", "value")
    
    def test_put_ssm_parameter_none_value(self):
        """Test that None value raises ValueError."""
        with pytest.raises(ValueError, match="Parameter value cannot be None"):
            put_ssm_parameter("/app/myapp/test", None)
    
    def test_put_ssm_parameter_with_encryption(self, mock_boto3_client):
        """Test storing encrypted parameter."""
        put_ssm_parameter("/app/myapp/secret", "secret_value", with_encryption=True)
        # Should not raise exception
    
    def test_delete_ssm_parameter_success(self, mock_boto3_client):
        """Test successful SSM parameter deletion."""
        delete_ssm_parameter("/app/myapp/test")
        # Should not raise exception
    
    def test_delete_ssm_parameter_not_found(self, mock_boto3_client):
        """Test deleting non-existent parameter (should not raise)."""
        ssm_mock = MagicMock()
        ssm_mock.delete_parameter.side_effect = MagicMock(
            exceptions=MagicMock(ParameterNotFound=Exception)
        )
        ssm_mock.exceptions.ParameterNotFound = Exception
        
        with patch("boto3.client", return_value=ssm_mock):
            # Should handle gracefully
            delete_ssm_parameter("/app/myapp/nonexistent")


@pytest.mark.unit
class TestAWSHelpers:
    """Test AWS helper functions."""
    
    def test_get_aws_region(self, mock_boto3_session):
        """Test AWS region retrieval."""
        region = get_aws_region()
        assert region == "us-east-1"
    
    def test_get_aws_region_not_configured(self):
        """Test error when region not configured."""
        with patch("boto3.session.Session") as mock_session:
            session_instance = MagicMock()
            session_instance.region_name = None
            mock_session.return_value = session_instance
            
            with pytest.raises(RuntimeError, match="AWS region not configured"):
                get_aws_region()
    
    def test_get_aws_account_id(self, mock_boto3_client):
        """Test AWS account ID retrieval."""
        account_id = get_aws_account_id()
        assert account_id == "123456789012"
    
    def test_get_cognito_client_secret(self, mock_boto3_client, mock_ssm_parameters):
        """Test Cognito client secret retrieval."""
        secret = get_cognito_client_secret()
        assert secret == "mock-client-secret"


@pytest.mark.unit
class TestConfigurationLoading:
    """Test configuration file loading."""
    
    def test_load_api_spec_success(self):
        """Test successful API spec loading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_data = [{"key": "value"}, {"key2": "value2"}]
            json.dump(test_data, f)
            temp_path = f.name
        
        try:
            result = load_api_spec(temp_path)
            assert result == test_data
        finally:
            os.unlink(temp_path)
    
    def test_load_api_spec_not_list(self):
        """Test error when API spec is not a list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value"}, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Expected a list"):
                load_api_spec(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_api_spec_file_not_found(self):
        """Test error when API spec file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_api_spec("/nonexistent/path/file.json")
    
    def test_read_config_json(self):
        """Test reading JSON configuration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"setting": "value", "number": 42}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            result = read_config(temp_path)
            assert result == test_config
        finally:
            os.unlink(temp_path)
    
    def test_read_config_yaml(self):
        """Test reading YAML configuration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {"setting": "value", "number": 42}
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            result = read_config(temp_path)
            assert result == test_config
        finally:
            os.unlink(temp_path)
    
    def test_read_config_yml_extension(self):
        """Test reading .yml extension."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            test_config = {"setting": "value"}
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            result = read_config(temp_path)
            assert result == test_config
        finally:
            os.unlink(temp_path)
    
    def test_read_config_file_not_found(self):
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            read_config("/nonexistent/path/config.json")
    
    def test_read_config_invalid_json(self):
        """Test error with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                read_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_read_config_invalid_yaml(self):
        """Test error with invalid YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid:\nyaml:\n  - unclosed")
            f.write("\n    - [\n")  # Intentionally malformed
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid YAML"):
                read_config(temp_path)
        finally:
            os.unlink(temp_path)


@pytest.mark.unit
class TestRetryLogic:
    """Test retry logic for AWS operations."""
    
    def test_retry_on_throttling(self, mock_boto3_client):
        """Test retry on throttling exception."""
        ssm_mock = MagicMock()
        call_count = 0
        
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException"}},
                    "GetParameter"
                )
            return {"Parameter": {"Value": "success"}}
        
        ssm_mock.get_parameter.side_effect = side_effect
        
        with patch("boto3.client", return_value=ssm_mock):
            with patch("time.sleep"):  # Skip actual sleep
                result = get_ssm_parameter("/app/myapp/test")
                assert result == "success"
                assert call_count == 2
    
    def test_max_retries_exceeded(self, mock_boto3_client):
        """Test that max retries is enforced."""
        ssm_mock = MagicMock()
        ssm_mock.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException"}},
            "GetParameter"
        )
        
        with patch("boto3.client", return_value=ssm_mock):
            with patch("time.sleep"):  # Skip actual sleep
                with pytest.raises(ClientError):
                    get_ssm_parameter("/app/myapp/test")
