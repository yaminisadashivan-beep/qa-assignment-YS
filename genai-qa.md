# GenAI in the QA Workflow
**Author:** Yamini | Track B2

---

## Question 1 — Test Generation for Bulk-Order Import

**Tool I'd use:** GitHub Copilot Chat (GPT-4o) inside VS Code.

The reason I'd pick this over a standalone ChatGPT session is context. Copilot Chat has access to the files I have open — the existing `conftest.py`, the `OrderApiClient`, the `responses` mock setup. That means I'm not re-explaining the project structure in every prompt. The generated tests reference the actual fixtures and patterns already in use, rather than inventing new ones that I then have to reconcile with the codebase.

**The actual prompt I'd use:**

```
You are a senior QA engineer working on a pytest suite for a CSV bulk-order import endpoint.

Context:
- Endpoint: POST /v1/orders/bulk-import
- Accepts: multipart/form-data with a CSV file
- CSV columns: customer_id, pickup_street, pickup_city, pickup_postcode,
  pickup_country, dropoff_street, dropoff_city, dropoff_postcode,
  dropoff_country, weight_kg, service_level
- Flow: CSV validation → DB insert (Aurora PostgreSQL) → SNS event per row
- Auth: Bearer token (same pattern as existing order endpoints)

The existing test suite uses:
- conftest.py fixtures: api_client, unauth_client, valid_order_payload
- HTTP mocking via the `responses` library (@responses.activate decorator)
- OrderApiClient class in tests/client.py

Write pytest test cases covering:
1. Happy path: valid 5-row CSV returns 202 with job_id and row_count=5
2. Empty CSV: 400 with descriptive error message
3. CSV with one invalid row (weight_kg=-1): partial failure listing the bad row number
4. CSV exceeding row limit (1000 rows max): 413
5. Missing required column (no service_level column): 422
6. Auth failure: 401

Requirements:
- Use @pytest.fixture for CSV content, not hardcoded strings
- Mock HTTP via @responses.activate — no real HTTP calls
- Each test must assert on at least one field in the response body, not just status code
- Do NOT hardcode tokens — use the api_client and unauth_client fixtures from conftest.py
```

**What I would NOT trust the AI to do:**

Defining what "correct" partial failure behaviour looks like for a mixed-valid CSV — that's a product decision, not a pattern-matching problem. Writing the assertions for SNS event emission — the boto3 mock setup for async event verification is subtle, and in my experience AI tools get it wrong in ways that make tests pass vacuously (the mock is called but the assertion doesn't actually validate the message body). I also wouldn't trust it to review its own output for logical correctness.

**Human review process:**

Every AI-generated test goes through three gates before it merges. I read it myself first — specifically looking at whether the assertion actually tests the contract or just verifies that a mock was invoked. Then it goes on a PR where a peer reviews it. Then it has to pass in CI on a clean virtual environment. If a test passes only because the mock is configured to return success regardless of input, it gets deleted.

---

## Question 2 — AI Pricing Agent Regression

**How I'd define "expected range" for a non-deterministic model:**

I want to be clear about one thing upfront: I would not ask the model to tell me what the correct price is. That's circular. The acceptable ranges need to come from the product and pricing team, derived from historical pricing data and business rules — not from running the model a few times and averaging the output.

In practice, that means sitting down with whoever owns the pricing logic and agreeing on bounds per input segment: weight band × distance band × service level × customer tier. These bounds should be wider than typical output variance but tight enough to actually catch the kind of outlier we saw — $4,210 for a standard enterprise shipment where the expected range is $30–$48. That's not a subtle drift. That's a failure.

**Drift detection strategy:**

A golden dataset of 200+ input/output pairs sampled from production, covering normal cases, edge cases, and known historical outliers. Every release re-runs the full dataset against the new agent version. I track two things over time: outlier rate (percentage of inputs outside the agreed range) and mean price delta (average price change from the previous release for identical inputs). A spike in either metric above a rolling 4-week baseline is a release hold.

I'd also run the golden dataset weekly against the live agent as a scheduled job — not just on release days. Drift doesn't always coincide with a deployment.

**What I log for forensics:**

Full input payload, raw model output, parsed price, expected range, pass/fail verdict, model version identifier, timestamp, and request latency. Structured JSON to CloudWatch Logs so I can query `outlier_rate by model_version` within seconds of an incident. Without this logging, post-incident analysis is reconstruction from memory, which is unreliable.

**Where GenAI helps:**

Generating diverse synthetic test inputs at scale. Covering all combinations of weight, distance, service level, and customer tier manually would take days. I'd use a prompt to generate 50 synthetic edge cases per segment and then trim to the 200 that best cover the input space. That's the right use of AI here — accelerating data generation, not making quality judgements.

**Where GenAI doesn't help:**

Defining the acceptable ranges — that's a business decision. Detecting drift — the model can't tell you if a price change is a bug or an intentional model update; only the ML team can make that call. Writing the forensics logging schema — AI tends to log what's easy to access, not what's forensically useful. That schema needs to be designed by someone who's been in a 2am incident call wondering why the pricing agent returned a wrong value.

---

## Artifact

See `pricing_harness.py` in this repository for the runnable regression harness.
