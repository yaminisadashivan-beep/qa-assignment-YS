"""
conftest.py — Shared fixtures for the ShipFast Order API test suite.
"""
import pytest
from unittest.mock import patch
from tests.client import OrderApiClient

BASE_URL = "https://api.shipfast.internal/v1"
VALID_TOKEN = "test-bearer-token-valid"
INVALID_TOKEN = "bad-token"


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
