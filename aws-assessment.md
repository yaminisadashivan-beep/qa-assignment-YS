# AWS Architecture & Testability Assessment — ShipFast
**Author:** Yamini | Track B1

---

## Testability Risks and Gaps

Before I get into the specific gaps, I want to name the overarching problem: this is an architecture that was designed for production reliability, not for testability. That's not unusual — most systems I've worked with start this way. The goal is to identify where that creates the most risk and address it deliberately.

**Gap 1: Shared staging and UAT environment.**
This is the one that would concern me most on day one. When QA-initiated load tests, destructive test data, and schema migrations share the same environment as UAT sessions, you're never working with a known-clean state. I've seen this cause test failures that took hours to diagnose — not because the code was wrong, but because someone had left dirty data from a manual UAT session two days earlier. Any serious automation investment on a shared environment is undermined from the start.

**Gap 2: No distributed tracing.**
X-Ray is not enabled. That means when an automated test fails with a 500, there's no way to trace that request across ECS Fargate, Aurora, and the SNS/SQS chain without manually correlatidng CloudWatch log timestamps across four or five log groups. I've done that kind of debugging. It's slow, it's error-prone, and it's completely avoidable. Without tracing, the team is spending engineering time on triage that should be spent on features.

**Gap 3: No mechanism to inject test messages into the event bus.**
The SNS → SQS → consumer chain is essentially untestable in isolation right now. There's no documented way to push a test message directly into a queue or assert on the dead-letter queue state from a test. This means event-driven flows are either tested end-to-end (slow and fragile) or not tested at all. Based on what I can see, it's mostly the latter.

**Gap 4: No dedicated QA environment — test data contaminates shared Aurora.**
Without isolation, we can't baseline performance, run destructive edge-case data tests, or reproduce customer-specific bugs reliably. Aurora Multi-AZ in a shared staging environment is also significantly over-provisioned for QA workloads, which means we're paying for resilience features that add no QA value.

**Gap 5: No automated test stage in CodePipeline.**
The pipeline is: build → unit test → deploy staging → manual approval → prod. Manual approval is not a quality gate — it's a human remembering to check. As release frequency increases, that model breaks down. There needs to be an automated smoke test stage after the staging deploy that either passes or fails the pipeline without human intervention.

**Gap 6: IAM over-permissioning for QA tooling.**
Without a dedicated QA environment and purpose-built IAM roles, QA automation tools are almost certainly running under developer-scoped admin roles or the same ECS task roles as production services. I've seen this cause two categories of problem: test scripts accidentally touching production resources, and over-broad CI runner access becoming a security exposure. This one is easy to fix and worth doing early.

---

## Dedicated QA Environment Design

The goal here is isolation without over-spending. We don't need a full production replica — we need an environment that's stable, clean, and representative enough to catch real bugs.

**Compute:** Same ECS task definitions as staging, but with reduced CPU/memory allocations — say 0.25 vCPU / 512MB per service vs. production's 1 vCPU / 2GB. Fargate scales to zero when tests aren't running, so the idle cost is essentially zero. Separate ECS cluster tagged `env=qa`.

**Database:** This is where the biggest cost saving is. Replace the Multi-AZ Aurora cluster with a single Aurora Serverless v2 instance. It scales to zero ACUs when idle — roughly $0.06/ACU-hour only during active test runs. Same schema, same migration scripts, no read replicas needed.

**Event Bus:** Separate SNS topics and SQS queues for the QA environment with a consistent naming convention (`qa-order-events`, `qa-order-dlq`). This is what allows test-injected messages to flow through the full chain without touching staging consumers. Enable DLQ redrive with a short visibility timeout so tests can assert on failure routing quickly.

**Secrets Manager:** QA-specific secrets under a `/qa/` prefix. The QA IAM role only has access to that path.

**Estimated cost:** In my experience a setup like this runs $80–120/month for a team running automated suites 8 hours/day on weekdays. Near-zero on weekends.

---

## CloudWatch and X-Ray for Test Triage

Enabling X-Ray on ECS Fargate services is straightforward — add the X-Ray daemon as a sidecar container. The benefit is immediate: every automated test run gets a trace ID that links the test log to the full request path across services. When a test fails, the QA engineer looks up the trace in X-Ray Service Map and sees exactly which service returned an error and at what latency. This cuts triage time significantly.

For CloudWatch, the two things I'd set up first are saved Logs Insights queries for the most common failure patterns (5xx from the API, DLQ count > 0, Aurora connection errors), and alarms on `HTTPCode_Target_5XX_Count` and `ApproximateNumberOfMessagesNotVisible` on the order DLQ. If either alarm fires within 5 minutes of a test deploy, the pipeline stage fails automatically.

One thing that makes all of this much more useful is enforcing structured logging across services — with consistent `request_id`, `order_id`, `service_name`, and `env` fields. Without that, correlating logs across the import → pricing → event chain is still painful even with Logs Insights.

---

## SQS/SNS Event Flow Testing

My approach has two layers and I think both are necessary.

For fast CI feedback, mock the SQS client in unit and integration tests using `unittest.mock`. The pytest suite in this repo (see A2) demonstrates the pattern. This is fast and reliable but doesn't test the actual AWS infrastructure.

For environment-level confidence, use a test producer/consumer pattern in the QA environment: a small script publishes a test event directly to the `qa-order-events` SNS topic, then polls the downstream SQS queue with a reasonable timeout, asserting that a message with the expected `order_id` and `event_type` arrives. If the message lands in the DLQ instead, the test fails with the DLQ message body as the error detail — which immediately tells you what went wrong.

The reason I prefer this over asserting on database state after an async event is timing. Database assertions after async events are inherently flaky. Queue state assertions with a sensible timeout are deterministic.

---

## IAM Concern and Remediation

The concern is that QA automation tooling — pytest runners, boto3 scripts, load test agents — is running under overly broad IAM roles. Either developer admin access or the same task roles as production services. I've seen both in practice and both are problems.

The remediation is a dedicated `qa-automation-role` scoped specifically to the QA environment:
- ECS describe/list permissions on the `qa` cluster only
- SQS send/receive/delete on queue ARNs matching `arn:aws:sqs:*:*:qa-*`
- SNS publish on topic ARNs matching `arn:aws:sns:*:*:qa-*`
- Secrets Manager read on paths matching `/qa/*`
- CloudWatch PutMetricData restricted to the `QA` namespace
- Explicit Deny on any resource tagged `env=production`

The CI runner assumes this role via `sts:AssumeRole` with a 1-hour session. No human user ever needs this role. This isn't a complicated change — it's a few hours of IAM work — but it removes a category of risk that's easy to ignore until it becomes an incident.

---

## Artifact

See `qa-env-healthcheck.py` in this repository. The script verifies the QA environment is healthy across ECS (services running), SQS (queue reachable, DLQ empty), and RDS Aurora (connection successful) before the automated test suite starts. Run it after every QA environment deploy.
