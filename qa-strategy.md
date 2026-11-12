# QA Strategy — ShipFast
**Author:** Yamini | **Role:** QA Manager | **Mandate:** 90-day quality improvement

---

## 1. Coverage Model

The honest starting point is that not every component needs the same type of testing, and spreading effort evenly is a mistake I've seen teams make more than once.

The REST API is where I'd concentrate the most automation effort — it's the backbone of everything else, and with ~40 endpoints it has the highest blast radius when something breaks. Unit tests for business logic, contract tests at the service boundary, integration tests for the database layer, and a focused set of E2E tests for the most critical order lifecycle flows.

For the PostgreSQL layer, I wouldn't write tests that poke directly at the database schema. The API owns that boundary. What I do care about is data integrity under concurrent writes and migration correctness — both of which have burned me in past projects and are easy to miss until they're a production incident.

The Web Portal gets component tests and a small set of Playwright E2E tests covering the three flows that generate the most customer support tickets — placing an order, tracking it, and downloading a report. Full UI regression automation has a poor ROI in my experience; it's expensive to maintain and breaks for the wrong reasons.

For the Mobile App, I'd focus automation at the API contract layer rather than the UI. Device matrix testing is better done through exploratory sessions — the edge cases that matter there are the ones that don't show up in a script.

The AI Pricing Agent needs its own approach entirely, which I've covered in section 4.

The Event Bus is probably the most under-tested surface in most systems I've worked with, and I'd treat it as a first-class testing concern — not an afterthought. Schema validation, idempotency, and dead-letter queue monitoring need to be in the automation suite from the start.

---

## 2. First 30 Days

I've learned not to start writing tests before I understand what's actually breaking. So the first thing I'd do — probably in the first week — is sit with the team and go through the 120 manual regression cases. I want to understand which ones have failed in the last three months, which ones are flaky, and which ones nobody actually trusts. That audit will tell me more about the real risk areas than any architecture diagram.

The second priority is observability. We can't have a meaningful conversation about quality without knowing what's failing and why. I'd add structured logging and basic CloudWatch alarms to the API and event bus before writing a single automated test. Instrumentation first.

The third thing — and this is where I'd spend most of my energy in weeks two and three — is standing up a dedicated QA environment and getting the team a working CI scaffold they can actually build on. A blank test file is daunting. A conftest.py with shared fixtures, a working client class, and two example tests is something people actually use. I want to give the team a foundation, not a mandate.

---

## 3. Automation Roadmap

My rule of thumb is: automate the things that, when they break, page someone at 2am. Everything else can wait.

That means the first wave of automation is the order lifecycle happy paths and the critical state transitions in the REST API. These are deterministic, fast to write, and directly tied to revenue. Target: 40 tests covering the full order lifecycle by week six.

Second wave is the event bus integration tests. The SNS → SQS → consumer chain failing silently is in my experience the highest category of hard-to-detect P1 risk in event-driven systems. Mocked queue tests in CI, real queue smoke tests in the QA environment. This should be done by week eight.

Third wave is the Web Portal E2E suite — but only the three user journeys I mentioned above. I'd resist the temptation to automate everything visible in the UI. The maintenance cost isn't worth it.

I measure automation progress three ways: coverage rate against the original 120 regression cases (target 60% by day 90), CI pass rate on the main branch (target ≥95%), and mean time to detect a regression after a merge (target under 30 minutes). These are directional targets — I'd establish the actual baselines in week one and adjust if the numbers don't make sense in context.

---

## 4. AI Pricing Agent

This one requires a different mental model and I want to be clear about that upfront. You cannot test a non-deterministic LLM-powered service the same way you test an API endpoint. Exact-value assertions will fail randomly and tell you nothing useful.

What I would do instead is work with the product and pricing team to define acceptable price ranges per input segment — weight band, distance band, service level, customer tier. These ranges should be wider than typical output variance but tight enough to catch genuine outliers. The $4,210 output for a standard enterprise shipment that the team observed is exactly the kind of thing a range-based assertion would catch.

For regression, I'd maintain a golden dataset of 200+ input/output pairs sampled from production, covering normal cases, known edge cases, and historical outliers. Every release re-runs the full dataset. Any new outlier is a blocking issue before deploy.

Drift is the harder problem. I'd run the golden dataset weekly against the live agent as a scheduled job — not just on release days — and track the outlier rate over time. A spike above baseline triggers a review with the ML team before the next release. I'd also log every agent invocation with the full input, raw output, expected range, verdict, and model version. Without that forensics trail, post-incident analysis is guesswork.

One thing I'd be honest about: the range definitions themselves need to come from the business, not from me. I can build the harness, but someone who understands the pricing model needs to sign off on what "correct" looks like.

---

## 5. Non-Functional Priorities

Performance first, and specifically for the two highest-latency surfaces: the pricing agent and the bulk-order import flow. I'd establish baseline p50/p95/p99 latency for both using k6 load tests in the QA environment before any release that touches them. Without a baseline you're flying blind — you can't call something a regression if you don't know what normal looks like.

Security second. The API handles financial data and customer PII, which puts it in a different risk category than most of the systems I've worked on. I'd run OWASP ZAP against the top-risk endpoint categories and add auth boundary tests to the automated suite — missing token, expired token, wrong scope. These are fast to write and catch a whole class of bugs that unit tests miss entirely. I'd aim to have this done within 60 days.

Accessibility third, but I'd frame this differently to the team: once Playwright E2E is in place, adding axe-core takes maybe half a day and catches accessibility regressions automatically without a manual audit. The incremental effort is small. The legal exposure for an enterprise B2B platform that ignores WCAG 2.1 AA is not.

---

## 6. Day 90 KPIs

I want to be upfront: some of these numbers will need to be adjusted once I see the actual baselines in week one. These are informed targets, not commitments made without data.

| KPI | Target | Reasoning |
|---|---|---|
| Automated regression coverage | ≥60% of 120 cases | Currently 0%; getting to 60% means the top-risk cases are covered and the team has built the habit |
| CI pass rate on main | ≥95% | Below this, developers stop trusting the suite and start ignoring it — which is worse than no automation |
| Mean time to detect regression | <30 minutes from merge | Same-day detection changes how the team thinks about quality |
| P1 incidents from releases | ≤1 per month | Need the current baseline first; this is the number the CTO actually cares about |
| Pricing agent outlier rate | <1% of golden dataset | Baseline this in week one; adjust target if the starting point is worse than expected |
| QA cycle time per release | <4 hours | Down from the current ~2 days of manual regression; this is the ROI story for automation investment |

The most important thing I'd do at day 30 is present the baselines — not the targets — to the CTO. That conversation sets realistic expectations and gives us a shared definition of what improvement actually looks like.
