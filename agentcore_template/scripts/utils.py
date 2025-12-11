import boto3
import json
import yaml
import os
import logging
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError, BotoCoreError
from functools import wraps
import time

# Configure logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def retry_with_backoff(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """
    Decorator to retry AWS operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay between retries
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (ClientError, BotoCoreError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', 'Unknown')
                        # Only retry on throttling or service errors
                        if error_code in ['ThrottlingException', 'ServiceUnavailable', 'InternalError']:
                            logger.warning(
                                f"AWS operation failed (attempt {attempt + 1}/{max_retries}), "
                                f"retrying in {delay}s: {e}"
                            )
                            time.sleep(delay)
                            delay *= backoff_factor
                        else:
                            # Don't retry on other errors
                            raise
                    else:
                        logger.error(f"AWS operation failed after {max_retries} attempts: {e}")
                        raise last_exception
            
            raise last_exception
        
        return wrapper
    return decorator


@retry_with_backoff(max_retries=3)
def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    """
    Retrieve a parameter from AWS Systems Manager Parameter Store.
    
    Args:
        name: Parameter name/path
        with_decryption: Whether to decrypt SecureString parameters
        
    Returns:
        str: Parameter value
        
    Raises:
        ValueError: If parameter name is empty
        ClientError: If parameter not found or AWS error occurs
    """
    if not name or not name.strip():
        raise ValueError("Parameter name cannot be empty")
    
    logger.debug(f"Retrieving SSM parameter: {name}")
    
    try:
        ssm = boto3.client("ssm")
        response = ssm.get_parameter(Name=name, WithDecryption=with_decryption)
        logger.debug(f"Successfully retrieved SSM parameter: {name}")
        return response["Parameter"]["Value"]
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'ParameterNotFound':
            logger.error(f"SSM parameter not found: {name}")
            raise ValueError(f"Parameter '{name}' not found in SSM Parameter Store") from e
        else:
            logger.error(f"AWS error retrieving SSM parameter '{name}': {e}")
            raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving SSM parameter '{name}': {e}")
        raise


@retry_with_backoff(max_retries=3)
def put_ssm_parameter(
    name: str, 
    value: str, 
    parameter_type: str = "String", 
    with_encryption: bool = False,
    description: Optional[str] = None
) -> None:
    """
    Store a parameter in AWS Systems Manager Parameter Store.
    
    Args:
        name: Parameter name/path
        value: Parameter value
        parameter_type: Type of parameter (String, StringList, SecureString)
        with_encryption: Whether to encrypt the parameter (sets type to SecureString)
        description: Optional description for the parameter
        
    Raises:
        ValueError: If parameter name or value is empty
        ClientError: If AWS error occurs
    """
    if not name or not name.strip():
        raise ValueError("Parameter name cannot be empty")
    if value is None:
        raise ValueError("Parameter value cannot be None")
    
    logger.debug(f"Storing SSM parameter: {name}")
    
    ssm = boto3.client("ssm")

    put_params = {
        "Name": name,
        "Value": value,
        "Type": parameter_type,
        "Overwrite": True,
    }

    if with_encryption:
        put_params["Type"] = "SecureString"
        
    if description:
        put_params["Description"] = description

    try:
        ssm.put_parameter(**put_params)
        logger.info(f"Successfully stored SSM parameter: {name}")
    except ClientError as e:
        logger.error(f"AWS error storing SSM parameter '{name}': {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error storing SSM parameter '{name}': {e}")
        raise


def delete_ssm_parameter(name: str) -> None:
    """
    Delete a parameter from AWS Systems Manager Parameter Store.
    
    Args:
        name: Parameter name/path
        
    Raises:
        ValueError: If parameter name is empty
    """
    if not name or not name.strip():
        raise ValueError("Parameter name cannot be empty")
        
    logger.debug(f"Deleting SSM parameter: {name}")
    
    ssm = boto3.client("ssm")
    try:
        ssm.delete_parameter(Name=name)
        logger.info(f"Successfully deleted SSM parameter: {name}")
    except ssm.exceptions.ParameterNotFound:
        logger.warning(f"SSM parameter not found (already deleted?): {name}")
    except ClientError as e:
        logger.error(f"AWS error deleting SSM parameter '{name}': {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting SSM parameter '{name}': {e}")
        raise


def load_api_spec(file_path: str) -> list:
    """
    Load API specification from a JSON file.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        list: API specification data
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file content is invalid
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"API spec file not found: {file_path}")
        
    logger.debug(f"Loading API spec from: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            raise ValueError("Expected a list in the JSON file")
            
        logger.info(f"Successfully loaded API spec with {len(data)} items")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in API spec file '{file_path}': {e}")
        raise ValueError(f"Invalid JSON in file '{file_path}': {e}") from e
    except Exception as e:
        logger.error(f"Error loading API spec from '{file_path}': {e}")
        raise


@retry_with_backoff(max_retries=3)
def get_aws_region() -> str:
    """
    Get the current AWS region.
    
    Returns:
        str: AWS region name
        
    Raises:
        RuntimeError: If region cannot be determined
    """
    try:
        session = boto3.session.Session()
        region = session.region_name
        
        if not region:
            raise RuntimeError("AWS region not configured. Please set AWS_DEFAULT_REGION or configure AWS CLI.")
            
        logger.debug(f"AWS region: {region}")
        return region
    except Exception as e:
        logger.error(f"Error getting AWS region: {e}")
        raise RuntimeError("Failed to determine AWS region") from e


@retry_with_backoff(max_retries=3)
def get_aws_account_id() -> str:
    """
    Get the current AWS account ID.
    
    Returns:
        str: AWS account ID
        
    Raises:
        ClientError: If AWS error occurs
    """
    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        logger.debug(f"AWS account ID: {account_id}")
        return account_id
    except ClientError as e:
        logger.error(f"AWS error getting account ID: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting account ID: {e}")
        raise


@retry_with_backoff(max_retries=3)
def get_cognito_client_secret() -> str:
    """
    Get Cognito user pool client secret.
    
    Returns:
        str: Client secret
        
    Raises:
        ClientError: If AWS error occurs
        ValueError: If SSM parameters not found
    """
    try:
        client = boto3.client("cognito-idp")
        
        # Retrieve required SSM parameters
        user_pool_id = get_ssm_parameter("/app/myapp/agentcore/userpool_id")
        client_id = get_ssm_parameter("/app/myapp/agentcore/machine_client_id")
        
        response = client.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id,
        )
        
        client_secret = response["UserPoolClient"]["ClientSecret"]
        logger.debug("Successfully retrieved Cognito client secret")
        return client_secret
    except ClientError as e:
        logger.error(f"AWS error getting Cognito client secret: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting Cognito client secret: {e}")
        raise


def read_config(file_path: str) -> Dict[str, Any]:
    """
    Read configuration from a file path. Supports JSON, YAML, and YML formats.

    Args:
        file_path (str): Path to the configuration file

    Returns:
        Dict[str, Any]: Configuration data as a dictionary

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file format is not supported or invalid
        yaml.YAMLError: If YAML parsing fails
        json.JSONDecodeError: If JSON parsing fails
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    # Get file extension to determine format
    _, ext = os.path.splitext(file_path.lower())

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            if ext == ".json":
                return json.load(file)
            elif ext in [".yaml", ".yml"]:
                return yaml.safe_load(file)
            else:
                # Try to auto-detect format by attempting JSON first, then YAML
                content = file.read()
                file.seek(0)

                # Try JSON first
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Try YAML
                    try:
                        return yaml.safe_load(content)
                    except yaml.YAMLError:
                        raise ValueError(
                            f"Unsupported configuration file format: {ext}. "
                            f"Supported formats: .json, .yaml, .yml"
                        )

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file {file_path}: {e}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file {file_path}: {e}")
    except Exception as e:
        raise ValueError(f"Error reading configuration file {file_path}: {e}")