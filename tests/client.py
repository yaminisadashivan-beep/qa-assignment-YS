"""
client.py — Reusable OrderApiClient encapsulating session, base URL, and auth.

Justification for mocking strategy: We use `responses` (the library) to
intercept requests at the HTTP adapter level. This gives us real
requests.Session behaviour (headers, retries, timeouts) without a live server,
and makes it easy to assert on request bodies and headers inside tests.
"""
import requests


class OrderApiClient:
    """
    Thin wrapper around requests.Session for the ShipFast Order API.
    Encapsulates base URL, auth header injection, and common HTTP verbs.
    """

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def create_order(self, payload: dict) -> requests.Response:
        return self.session.post(f"{self.base_url}/orders", json=payload)

    def get_order(self, order_id: str) -> requests.Response:
        return self.session.get(f"{self.base_url}/orders/{order_id}")

    def update_order_status(self, order_id: str, status: str) -> requests.Response:
        return self.session.patch(
            f"{self.base_url}/orders/{order_id}",
            json={"status": status}
        )

    def delete_order(self, order_id: str) -> requests.Response:
        return self.session.delete(f"{self.base_url}/orders/{order_id}")
