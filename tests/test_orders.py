"""
test_orders.py — pytest suite for ShipFast Order Management API.

Covers: POST /v1/orders, GET /v1/orders/{id}, PATCH /v1/orders/{id},
        DELETE /v1/orders/{id}

HTTP layer is mocked using the `responses` library so no live server is needed.
"""
import pytest
import responses as rsps_lib
import responses
from tests.client import OrderApiClient

BASE_URL = "https://api.shipfast.internal/v1"
VALID_TOKEN = "test-bearer-token-valid"
ORDER_ID = "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# POST /v1/orders — Happy path & validation errors
# ---------------------------------------------------------------------------

class TestCreateOrder:

    @responses.activate
    def test_create_order_happy_path(self, api_client, valid_order_payload, created_order_response):
        """201 returned with order_id, status=CREATED, price_usd, eta on valid input."""
        responses.add(
            responses.POST,
            f"{BASE_URL}/orders",
            json=created_order_response,
            status=201
        )
        resp = api_client.create_order(valid_order_payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "order_id" in body
        assert body["status"] == "CREATED"
        assert isinstance(body["price_usd"], float)
        assert "eta" in body

    @responses.activate
    @pytest.mark.parametrize("weight_kg,expected_status", [
        (0, 400),       # zero weight
        (-5, 400),      # negative weight
        (5001, 400),    # over 5000 kg limit
        (5000.1, 400),  # just over limit
    ])
    def test_create_order_invalid_weight(self, api_client, valid_order_payload, weight_kg, expected_status):
        """400 returned when weight_kg is <= 0 or > 5000."""
        responses.add(
            responses.POST,
            f"{BASE_URL}/orders",
            json={"error": "invalid weight_kg"},
            status=400
        )
        valid_order_payload["weight_kg"] = weight_kg
        resp = api_client.create_order(valid_order_payload)
        assert resp.status_code == expected_status

    @responses.activate
    def test_create_order_missing_address_fields(self, api_client, valid_order_payload):
        """422 returned when address fields are incomplete."""
        responses.add(
            responses.POST,
            f"{BASE_URL}/orders",
            json={"error": "incomplete address"},
            status=422
        )
        valid_order_payload["pickup"] = {"street": "1 Main St"}  # missing city, postcode, country
        resp = api_client.create_order(valid_order_payload)
        assert resp.status_code == 422

    @responses.activate
    def test_create_order_unauthorized(self, unauth_client, valid_order_payload):
        """401 returned when Bearer token is missing or invalid."""
        responses.add(
            responses.POST,
            f"{BASE_URL}/orders",
            json={"error": "unauthorized"},
            status=401
        )
        resp = unauth_client.create_order(valid_order_payload)
        assert resp.status_code == 401

    @responses.activate
    @pytest.mark.parametrize("service_level", ["STANDARD", "EXPRESS", "OVERNIGHT"])
    def test_create_order_all_service_levels(self, api_client, valid_order_payload, created_order_response, service_level):
        """201 returned for each valid service level."""
        responses.add(
            responses.POST,
            f"{BASE_URL}/orders",
            json=created_order_response,
            status=201
        )
        valid_order_payload["service_level"] = service_level
        resp = api_client.create_order(valid_order_payload)
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# GET /v1/orders/{order_id}
# ---------------------------------------------------------------------------

class TestGetOrder:

    @responses.activate
    def test_get_order_happy_path(self, api_client):
        """200 returned with order details and history list."""
        responses.add(
            responses.GET,
            f"{BASE_URL}/orders/{ORDER_ID}",
            json={
                "order_id": ORDER_ID,
                "status": "IN_TRANSIT",
                "price_usd": 42.50,
                "eta": "2026-11-13T10:00:00Z",
                "history": [
                    {"status": "CREATED", "timestamp": "2026-11-11T08:00:00Z"},
                    {"status": "PICKED_UP", "timestamp": "2026-11-11T10:00:00Z"},
                    {"status": "IN_TRANSIT", "timestamp": "2026-11-11T12:00:00Z"},
                ]
            },
            status=200
        )
        resp = api_client.get_order(ORDER_ID)
        assert resp.status_code == 200
        body = resp.json()
        assert body["order_id"] == ORDER_ID
        assert isinstance(body["history"], list)

    @responses.activate
    def test_get_order_not_found(self, api_client):
        """404 returned for a non-existent order_id."""
        responses.add(
            responses.GET,
            f"{BASE_URL}/orders/nonexistent-id",
            json={"error": "order not found"},
            status=404
        )
        resp = api_client.get_order("nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /v1/orders/{order_id} — State transition rules
# ---------------------------------------------------------------------------

class TestUpdateOrderStatus:

    @responses.activate
    @pytest.mark.parametrize("from_status,to_status", [
        ("CREATED", "PICKED_UP"),
        ("PICKED_UP", "IN_TRANSIT"),
        ("IN_TRANSIT", "DELIVERED"),
        ("IN_TRANSIT", "CANCELLED"),
    ])
    def test_valid_state_transitions(self, api_client, from_status, to_status):
        """200 returned on all legal state transitions."""
        responses.add(
            responses.PATCH,
            f"{BASE_URL}/orders/{ORDER_ID}",
            json={"order_id": ORDER_ID, "status": to_status},
            status=200
        )
        resp = api_client.update_order_status(ORDER_ID, to_status)
        assert resp.status_code == 200
        assert resp.json()["status"] == to_status

    @responses.activate
    @pytest.mark.parametrize("illegal_transition", [
        "IN_TRANSIT",   # DELIVERED → IN_TRANSIT is illegal
        "PICKED_UP",    # DELIVERED → PICKED_UP is illegal
        "CREATED",      # DELIVERED → CREATED is illegal
    ])
    def test_illegal_state_transition_returns_409(self, api_client, illegal_transition):
        """409 returned when attempting an illegal state transition."""
        responses.add(
            responses.PATCH,
            f"{BASE_URL}/orders/{ORDER_ID}",
            json={"error": "illegal state transition"},
            status=409
        )
        resp = api_client.update_order_status(ORDER_ID, illegal_transition)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /v1/orders/{order_id}
# ---------------------------------------------------------------------------

class TestDeleteOrder:

    @responses.activate
    @pytest.mark.parametrize("deletable_status", ["CREATED", "PICKED_UP"])
    def test_delete_order_allowed_statuses(self, api_client, deletable_status):
        """204 returned when order status allows deletion."""
        responses.add(
            responses.DELETE,
            f"{BASE_URL}/orders/{ORDER_ID}",
            status=204
        )
        resp = api_client.delete_order(ORDER_ID)
        assert resp.status_code == 204

    @responses.activate
    @pytest.mark.parametrize("non_deletable_status", ["IN_TRANSIT", "DELIVERED"])
    def test_delete_order_blocked_statuses(self, api_client, non_deletable_status):
        """409 returned when trying to delete an in-transit or delivered order."""
        responses.add(
            responses.DELETE,
            f"{BASE_URL}/orders/{ORDER_ID}",
            json={"error": "cannot delete order in current status"},
            status=409
        )
        resp = api_client.delete_order(ORDER_ID)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Bonus: SQS event-flow validation (mocked) for order state change
# ---------------------------------------------------------------------------

class TestSQSEventFlow:

    def test_order_state_change_emits_sqs_event(self, valid_order_payload):
        """
        Validates that an order state change publishes the expected message
        to the SQS queue. The SQS client is mocked via unittest.mock.
        """
        from unittest.mock import MagicMock, patch

        mock_sqs = MagicMock()
        mock_sqs.send_message.return_value = {
            "MessageId": "mock-message-id-123",
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

        with patch("boto3.client", return_value=mock_sqs):
            import boto3
            sqs = boto3.client("sqs", region_name="ap-south-1")
            response = sqs.send_message(
                QueueUrl="https://sqs.ap-south-1.amazonaws.com/123456789/order-events",
                MessageBody='{"order_id": "550e8400-e29b-41d4-a716-446655440000", "event": "ORDER_STATUS_CHANGED", "new_status": "PICKED_UP"}'
            )

        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
        assert "MessageId" in response
        mock_sqs.send_message.assert_called_once()
        call_kwargs = mock_sqs.send_message.call_args.kwargs
        assert "order-events" in call_kwargs["QueueUrl"]
        assert "ORDER_STATUS_CHANGED" in call_kwargs["MessageBody"]
