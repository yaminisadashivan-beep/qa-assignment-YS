# QA Manager Assignment — Yamini
**Role:** QA Manager, Enterprise Distributed Applications
**Candidate:** Yamini (yaminisadashivan@gmail.com)

---

## How to Run the Tests

**Requirements:** Python 3.11+

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full test suite
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=tests --cov-report=term-missing
```

**Expected output:** 12 tests collected, all passing.

**Run the pricing regression harness:**
```bash
python pricing_harness.py
```
Expected: detects the enterprise-tier outlier, prints structured JSON logs, exits with code 1 (outlier rate exceeds 2% threshold — by design in the mock).

**Run the QA environment health check (requires AWS credentials):**
```bash
python qa-env-healthcheck.py \
  --region ap-south-1 \
  --cluster qa-shipfast \
  --queue-url https://sqs.ap-south-1.amazonaws.com/<account>/qa-order-events \
  --dlq-url https://sqs.ap-south-1.amazonaws.com/<account>/qa-order-dlq \
  --db-host qa-aurora.cluster-xyz.ap-south-1.rds.amazonaws.com \
  --db-secret /qa/aurora/password
```

---

## Repository Structure

```
qa-assignment-YS/
├── README.md                   ← You are here
├── requirements.txt            ← Python dependencies
│
├── tests/                      ← Task A2: pytest suite
│   ├── __init__.py
│   ├── conftest.py             ← Shared fixtures
│   ├── client.py               ← Reusable OrderApiClient
│   └── test_orders.py          ← 12 test cases (POST/GET/PATCH/DELETE + SQS)
│
├── qa-strategy.md              ← Task A1: QA Strategy (3 pages)
├── management-scenario.md      ← Task A3: CTO memo on Friday release
│
├── aws-assessment.md           ← Track B1: AWS testability + QA env design
├── qa-env-healthcheck.py       ← Track B1 artifact: boto3 health check script
│
├── genai-qa.md                 ← Track B2: GenAI test generation + pricing regression
├── pricing_harness.py          ← Track B2 artifact: runnable pricing regression harness
│
└── code-review.md              ← Task C1 (bonus): PR review of junior engineer's test
```

---

## GenAI Tools Used and Where

| Tool | Used For | Where in Submission |
|---|---|---|
| **Claude (Anthropic)** | Drafting initial structure for QA strategy sections, management scenario tone review | A1, A3 — all content reviewed and rewritten with my own judgement and experience |
| **GitHub Copilot Chat** | Generating boilerplate pytest fixture scaffolding, suggesting parametrize patterns | A2 — all suggestions reviewed, modified, and verified against the OpenAPI contract |
| **Claude (Anthropic)** | Generating synthetic edge-case inputs for the pricing golden dataset | B2 — ranges and business logic defined by me, not by AI |

All AI-generated content was reviewed before inclusion. No section was submitted as-is from an AI tool. The opinions in A1 (QA strategy), A3 (management scenario), and B1 (AWS assessment) are my own and I would defend them in a room with the CTO.

---

## Assumptions Made

1. **Service level `OVERNIGHT` is a valid enum value** — the OpenAPI fragment lists `STANDARD | EXPRESS | OVERNIGHT`; the scenario description references only the first two in some places. I treated all three as valid.

2. **Bulk-order import endpoint is `POST /v1/orders/bulk-import`** — not specified in the OpenAPI fragment. I assumed a reasonable REST path for the B2 prompt strategy.

3. **QA environment region is `ap-south-1` (Mumbai)** — ShipFast is a B2B logistics platform; I assumed an India-focused deployment for the AWS artifact. Region is a CLI argument and can be changed without code changes.

4. **Aurora Serverless v2 is available in the target region** — if not, an `r6g.large` single-AZ instance is the alternative at ~$140/month.

5. **The pricing agent outlier rate baseline is unknown on day 1** — my day-90 KPI target of <1% is a proposed target; I committed to establishing the actual baseline in the first two weeks and adjusting the target if needed.

6. **`psycopg2-binary` is acceptable for the health check script** — added to `requirements.txt`. If the environment uses `asyncpg`, the connection check in `qa-env-healthcheck.py` can be swapped out.

---

*Submitted by Yamini | November 2026*
