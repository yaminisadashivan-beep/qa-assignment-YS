# Code Review — PR Feedback
**Reviewer:** Yamini | Task C1 (Bonus)
**File:** `test_order_creation.py`

---

## Overview

The intent here is clear and the flow makes sense — create an order, update its status, clean up. That's a reasonable starting point. But there are several issues that need to be addressed before this merges, and I want to walk through them clearly rather than just leaving inline comments. A few of these are habits that will cause problems across every test you write going forward, so I'd rather explain the reasoning than just flag the line.

---

### Issue 1 — Hardcoded Bearer Token (Critical)

```python
token = 'eyJhbGc...REDACTED'
```

This is the most urgent issue. A real JWT is committed to source code, which means it's in git history permanently — even after you remove it in a future commit. If that token were valid, it would be a credential leak. It also means the test breaks the moment the token expires, which could be in an hour or a day depending on how it was issued.

Tokens must never appear in source code. The right pattern is to load them from environment variables or fetch them from Secrets Manager at runtime. At minimum:

```python
import os
token = os.environ["SHIPFAST_API_TOKEN"]
```

In CI, the secret is injected by the pipeline. Locally, engineers set it in a `.env` file that's in `.gitignore`. See `conftest.py` in this repo for the pattern we use.

---

### Issue 2 — No HTTP Mocking — This Hits the Live API (Critical)

```python
r = requests.post('https://api.shipfast.internal/v1/orders', ...)
```

This test makes real HTTP calls. That means it will fail in any CI environment that doesn't have network access to the internal API. It also means every test run creates real orders in the database, which makes the data impossible to reason about over time. And it means you can't test error scenarios — 401, 422, 409 — without special server-side setup.

The `responses` library intercepts outbound HTTP calls at the adapter level, so you get real `requests.Session` behaviour without a live server. The `@responses.activate` decorator is the established pattern in this codebase. Take a look at `test_orders.py` for working examples.

---

### Issue 3 — One Test is Doing Three Things

```python
def test_order_creation():
    # creates an order
    # patches its status
    # deletes it
```

When this test fails, you don't know which operation caused it without reading the full traceback. If the `POST` returns an unexpected `order_id`, the subsequent `PATCH` and `DELETE` calls use that wrong ID silently — the test might pass for the wrong reason or fail for a confusing one.

Each test should assert one thing. Split this into `test_create_order_returns_201`, `test_update_order_status_to_delivered`, and `test_delete_order_returns_204`. If you need to share state between them, use a `pytest.fixture` to create the order once and pass the `order_id` through.

---

### Issue 4 — Cleanup Runs Only If Everything Passes

```python
r3 = requests.delete(...)
# cleanup
```

If the `assert r2.status_code == 200` on the PATCH call fails, Python raises an `AssertionError` and execution stops. The delete never runs. You've now got an orphaned order in the database every time this test fails — which is exactly when you'd want the cleanup to happen.

The correct pattern is a `pytest.fixture` with `yield`:

```python
@pytest.fixture
def created_order(api_client, valid_order_payload):
    resp = api_client.create_order(valid_order_payload)
    order_id = resp.json()["order_id"]
    yield order_id
    api_client.delete_order(order_id)  # runs even if the test fails
```

---

### Issue 5 — No Negative or Error Cases

The test only covers the happy path. The API contract specifies 400 for invalid weight, 401 for missing token, 409 for illegal state transitions, and 422 for incomplete addresses. None of these are tested here.

In my experience the error handling paths are where most bugs actually live — not the happy path. `@pytest.mark.parametrize` makes it easy to cover multiple error cases without duplicating test logic. See `test_orders.py` for examples of how we're doing this for weight validation and state transitions.

---

### Issue 6 — `print()` Doesn't Belong in Tests

```python
print('Created order:', order_id)
```

`print()` statements produce output nobody reads and don't cause the test to fail when something is wrong. They're fine in a debug session but shouldn't be committed.

Replace this with an assertion:

```python
assert order_id is not None
assert len(order_id) == 36  # UUID: 8-4-4-4-12
```

Pytest's assertion introspection already gives you readable output on failure — you don't need print for that.

---

### Issue 7 — No Fixtures or Shared Setup

The token, base URL, and order payload are all defined inline in the test function. When you write a second test tomorrow, you'll copy all of this. When the base URL changes, you'll update it in multiple places. When the token pattern changes, you'll miss one.

The `api_client` and `valid_order_payload` fixtures are already in `conftest.py` — use them. The test body should describe *what* is being tested, not repeat the setup boilerplate every time.

---

## Final Note

None of these issues suggest a misunderstanding of what the endpoint does — the flow is correct and the thinking is right. These are craft issues, not logic issues. The two to fix first are the hardcoded token (security) and the missing HTTP mock (reliability) — those affect every test you write, not just this one. Happy to pair on the refactor if that would help.
