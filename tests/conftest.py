"""
conftest.py — Shared fixtures and hooks for the ShipFast Order API test suite.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from tests.client import OrderApiClient

BASE_URL = "https://api.shipfast.internal/v1"
VALID_TOKEN = "test-bearer-token-valid"
INVALID_TOKEN = "bad-token"


# ---------------------------------------------------------------------------
# Bonus: boto3 snippet — fetch API token from AWS Secrets Manager
# In production CI, replace VALID_TOKEN with get_api_token() result
# ---------------------------------------------------------------------------

def get_api_token(secret_name: str = "/qa/shipfast/api-token",
                  region: str = "ap-south-1") -> str:
    """
    Fetches the ShipFast API Bearer token from AWS Secrets Manager.
    Falls back to the SHIPFAST_API_TOKEN environment variable if set,
    so local development doesn't require AWS credentials.
    """
    env_token = os.environ.get("SHIPFAST_API_TOKEN")
    if env_token:
        return env_token

    import boto3
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return response["SecretString"]


# ---------------------------------------------------------------------------
# Bonus: CloudWatch pytest hook — emits a custom metric on suite completion
# ---------------------------------------------------------------------------

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Pytest hook that emits a CloudWatch custom metric after the suite runs.
    Metric name: ShipFastQA/TestSuiteResult
    Dimensions: Environment=QA
    Only runs when AWS credentials are available (skips silently in local dev).
    """
    try:
        import boto3
        passed = len(terminalreporter.stats.get("passed", []))
        failed = len(terminalreporter.stats.get("failed", []))
        total = passed + failed

        cw = boto3.client("cloudwatch", region_name="ap-south-1")
        cw.put_metric_data(
            Namespace="ShipFastQA",
            MetricData=[
                {
                    "MetricName": "TestsPassed",
                    "Dimensions": [{"Name": "Environment", "Value": "QA"}],
                    "Value": passed,
                    "Unit": "Count"
                },
                {
                    "MetricName": "TestsFailed",
                    "Dimensions": [{"Name": "Environment", "Value": "QA"}],
                    "Value": failed,
                    "Unit": "Count"
                },
                {
                    "MetricName": "PassRate",
                    "Dimensions": [{"Name": "Environment", "Value": "QA"}],
                    "Value": (passed / total * 100) if total > 0 else 0,
                    "Unit": "Percent"
                },
            ]
        )
    except Exception:
        # Silently skip if AWS credentials are not available (local dev / CI without AWS)
        pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    """Reusable authenticated OrderApiClient for happy-path tests."""
    return OrderApiClient(base_url=BASE_URL, token=VALID_TOKEN)


@pytest.fixture
def unauth_client():
    """OrderApiClient with an invalid token for auth-failure tests."""
    return OrderApiClient(base_url=BASE_URL, token=INVALID_TOKEN)


@pytest.fixture
def valid_order_payload():
    """A complete, valid order creation payload."""
    return {
        "customer_id": "cust_abc123",
        "pickup": {
            "street": "1 Main St",
            "city": "Mumbai",
            "postcode": "400001",
            "country": "IN"
        },
        "dropoff": {
            "street": "5 Oak Ave",
            "city": "Delhi",
            "postcode": "110001",
            "country": "IN"
        },
        "weight_kg": 12.0,
        "service_level": "STANDARD"
    }


@pytest.fixture
def created_order_response():
    """Mock response body for a successfully created order."""
    return {
        "order_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "CREATED",
        "price_usd": 42.50,
        "eta": "2026-11-13T10:00:00Z"
    }
