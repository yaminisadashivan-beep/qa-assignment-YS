#!/usr/bin/env python3
"""
qa-env-healthcheck.py
Verifies the ShipFast QA environment is healthy across ECS, SQS, and RDS Aurora.
Run after every QA environment deploy before starting the automated test suite.

Usage:
    python qa-env-healthcheck.py --region ap-south-1 --cluster qa-shipfast \
        --queue-url https://sqs.ap-south-1.amazonaws.com/123456789/qa-order-events \
        --dlq-url https://sqs.ap-south-1.amazonaws.com/123456789/qa-order-dlq \
        --db-host qa-aurora.cluster-xyz.ap-south-1.rds.amazonaws.com \
        --db-secret /qa/aurora/password
"""
import argparse
import sys
import boto3
import psycopg2

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"


def check_ecs_services(region: str, cluster: str) -> bool:
    """Assert all ECS services in the QA cluster are ACTIVE with >=1 running task."""
    client = boto3.client("ecs", region_name=region)
    services = client.list_services(cluster=cluster)["serviceArns"]
    if not services:
        print(f"{FAIL} ECS: no services found in cluster '{cluster}'")
        return False
    described = client.describe_services(cluster=cluster, services=services)["services"]
    all_ok = True
    for svc in described:
        running = svc["runningCount"]
        status = svc["status"]
        name = svc["serviceName"]
        if status != "ACTIVE" or running < 1:
            print(f"{FAIL} ECS service '{name}': status={status}, running={running}")
            all_ok = False
        else:
            print(f"{PASS} ECS service '{name}': status={status}, running={running}")
    return all_ok


def check_sqs_queue(region: str, queue_url: str, dlq_url: str) -> bool:
    """Assert main queue is reachable and DLQ has zero messages."""
    client = boto3.client("sqs", region_name=region)
    attrs = ["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
    ok = True

    # Main queue reachability
    try:
        resp = client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=attrs)
        visible = int(resp["Attributes"].get("ApproximateNumberOfMessages", 0))
        print(f"{PASS} SQS main queue reachable. Messages visible: {visible}")
    except Exception as e:
        print(f"{FAIL} SQS main queue unreachable: {e}")
        ok = False

    # DLQ must be empty — messages here indicate event-processing failures
    try:
        resp = client.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=attrs)
        dlq_count = int(resp["Attributes"].get("ApproximateNumberOfMessages", 0))
        if dlq_count > 0:
            print(f"{FAIL} SQS DLQ has {dlq_count} unprocessed message(s) — environment may be unhealthy")
            ok = False
        else:
            print(f"{PASS} SQS DLQ is empty")
    except Exception as e:
        print(f"{FAIL} SQS DLQ check failed: {e}")
        ok = False

    return ok


def check_rds_connection(region: str, db_host: str, secret_name: str) -> bool:
    """Fetch DB credentials from Secrets Manager and assert Aurora accepts connections."""
    import json
    sm = boto3.client("secretsmanager", region_name=region)
    try:
        secret = json.loads(sm.get_secret_value(SecretId=secret_name)["SecretString"])
        conn = psycopg2.connect(
            host=db_host,
            port=secret.get("port", 5432),
            dbname=secret.get("dbname", "shipfast"),
            user=secret["username"],
            password=secret["password"],
            connect_timeout=5
        )
        conn.close()
        print(f"{PASS} RDS Aurora: connection successful to {db_host}")
        return True
    except Exception as e:
        print(f"{FAIL} RDS Aurora: connection failed — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="ShipFast QA environment health check")
    parser.add_argument("--region", default="ap-south-1")
    parser.add_argument("--cluster", default="qa-shipfast")
    parser.add_argument("--queue-url", required=True)
    parser.add_argument("--dlq-url", required=True)
    parser.add_argument("--db-host", required=True)
    parser.add_argument("--db-secret", default="/qa/aurora/password")
    args = parser.parse_args()

    print("\n=== ShipFast QA Environment Health Check ===\n")
    results = [
        check_ecs_services(args.region, args.cluster),
        check_sqs_queue(args.region, args.queue_url, args.dlq_url),
        check_rds_connection(args.region, args.db_host, args.db_secret),
    ]
    print()
    if all(results):
        print("All checks passed. QA environment is healthy.")
        sys.exit(0)
    else:
        print("One or more checks FAILED. Do not start the test suite.")
        sys.exit(1)


if __name__ == "__main__":
    main()
