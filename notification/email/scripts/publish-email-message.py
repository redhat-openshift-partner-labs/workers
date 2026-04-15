#!/usr/bin/env python3
"""
Publish email messages to RabbitMQ for the OPL Email Service.

This script publishes JSON messages to the opl-emails queue, which are then
consumed by the email service to send partner notification emails.

Usage:
    # Basic usage
    python publish-email-message.py \\
      --rabbitmq-url "amqp://user:pass@rabbitmq.namespace.svc.cluster.local:5672/" \\
      --to "partner@example.com" \\
      --cluster-id "test-cluster-123" \\
      --console-url "https://console.example.com" \\
      --credentials-url "https://creds.example.com" \\
      --credentials-password "secret123" \\
      --timezone "America/New_York" \\
      --expiration-date "2026-12-31"

    # With CC and BCC
    python publish-email-message.py \\
      --rabbitmq-url "amqp://localhost:5672/" \\
      --to "partner1@example.com" "partner2@example.com" \\
      --cc "sponsor@redhat.com" \\
      --bcc "admin@openshiftpartnerlabs.com" \\
      --cluster-id "test-cluster" \\
      --console-url "https://console.example.com" \\
      --credentials-url "https://creds.example.com" \\
      --credentials-password "secret" \\
      --timezone "Europe/London" \\
      --expiration-date "2026-12-31"

    # From environment variables
    export RABBITMQ_URL="amqp://localhost:5672/"
    python publish-email-message.py \\
      --to "partner@example.com" \\
      --cluster-id "test" \\
      --console-url "https://console.example.com" \\
      --credentials-url "https://creds.example.com" \\
      --credentials-password "secret" \\
      --timezone "America/New_York" \\
      --expiration-date "2026-12-31"

Requirements:
    pip install pika
"""

import argparse
import json
import os
import sys
from typing import List, Optional

try:
    import pika
except ImportError:
    print("Error: pika library not found. Install with: pip install pika", file=sys.stderr)
    sys.exit(1)


def publish_lab_ready_email(
    rabbitmq_url: str,
    to: List[str],
    cluster_id: str,
    console_url: str,
    credentials_url: str,
    credentials_password: str,
    timezone: str,
    expiration_date: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    queue_name: str = "opl-emails",
    custom_subject: Optional[str] = None,
    verbose: bool = False,
) -> bool:
    """
    Publish a lab_ready email message to RabbitMQ.

    Args:
        rabbitmq_url: RabbitMQ connection URL (e.g., amqp://user:pass@host:5672/)
        to: List of recipient email addresses
        cluster_id: Unique cluster identifier
        console_url: OpenShift console URL
        credentials_url: Password-protected credentials URL
        credentials_password: Password for credentials URL
        timezone: Partner's timezone (IANA format)
        expiration_date: Cluster expiration date (YYYY-MM-DD)
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        queue_name: RabbitMQ queue name (default: opl-emails)
        custom_subject: Optional custom subject line
        verbose: Enable verbose output

    Returns:
        True if message published successfully, False otherwise
    """
    # Build message
    message = {
        "to": to,
        "subject": custom_subject or f"Your OpenShift Lab is Ready - {cluster_id}",
        "template": "lab_ready",
        "data": {
            "cluster_id": cluster_id,
            "console_url": console_url,
            "credentials_url": credentials_url,
            "credentials_password": credentials_password,
            "timezone": timezone,
            "expiration_date": expiration_date,
        },
    }

    # Add optional fields
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    # Validate message structure
    required_fields = ["to", "subject", "template", "data"]
    for field in required_fields:
        if field not in message or not message[field]:
            print(f"Error: Required field '{field}' is missing or empty", file=sys.stderr)
            return False

    required_data_fields = [
        "cluster_id",
        "console_url",
        "credentials_url",
        "credentials_password",
        "timezone",
        "expiration_date",
    ]
    for field in required_data_fields:
        if field not in message["data"] or not message["data"][field]:
            print(f"Error: Required data field '{field}' is missing or empty", file=sys.stderr)
            return False

    if verbose:
        print("Message to publish:")
        print(json.dumps(message, indent=2))
        print()

    try:
        # Connect to RabbitMQ
        if verbose:
            print(f"Connecting to RabbitMQ: {rabbitmq_url}")

        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()

        # Declare queue (idempotent)
        channel.queue_declare(queue=queue_name, durable=True)

        # Publish message
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
                content_type="application/json",
            ),
        )

        if verbose:
            print(f"Message published to queue '{queue_name}'")

        connection.close()
        return True

    except pika.exceptions.AMQPConnectionError as e:
        print(f"Error: Failed to connect to RabbitMQ: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: Failed to publish message: {e}", file=sys.stderr)
        return False


def publish_lab_expiring_email(
    rabbitmq_url: str,
    to: List[str],
    cluster_id: str,
    expiration_date: str,
    days_remaining: int,
    console_url: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    queue_name: str = "opl-emails",
    verbose: bool = False,
) -> bool:
    """
    Publish a lab_expiring email message to RabbitMQ.

    Args:
        rabbitmq_url: RabbitMQ connection URL
        to: List of recipient email addresses
        cluster_id: Unique cluster identifier
        expiration_date: Cluster expiration date (YYYY-MM-DD)
        days_remaining: Days until expiration
        console_url: Optional OpenShift console URL
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        queue_name: RabbitMQ queue name
        verbose: Enable verbose output

    Returns:
        True if message published successfully, False otherwise
    """
    message = {
        "to": to,
        "subject": "Your OpenShift Lab is Expiring Soon",
        "template": "lab_expiring",
        "data": {
            "cluster_id": cluster_id,
            "expiration_date": expiration_date,
            "days_remaining": days_remaining,
        },
    }

    if console_url:
        message["data"]["console_url"] = console_url
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    if verbose:
        print("Message to publish:")
        print(json.dumps(message, indent=2))
        print()

    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)

        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        if verbose:
            print(f"Message published to queue '{queue_name}'")

        connection.close()
        return True

    except Exception as e:
        print(f"Error: Failed to publish message: {e}", file=sys.stderr)
        return False


def publish_lab_deprovisioned_email(
    rabbitmq_url: str,
    to: List[str],
    cluster_id: str,
    deprovision_date: str,
    deprovision_reason: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    queue_name: str = "opl-emails",
    verbose: bool = False,
) -> bool:
    """
    Publish a lab_deprovisioned email message to RabbitMQ.

    Args:
        rabbitmq_url: RabbitMQ connection URL
        to: List of recipient email addresses
        cluster_id: Unique cluster identifier
        deprovision_date: Date the cluster was deprovisioned
        deprovision_reason: Reason for deprovisioning
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        queue_name: RabbitMQ queue name
        verbose: Enable verbose output

    Returns:
        True if message published successfully, False otherwise
    """
    message = {
        "to": to,
        "subject": f"Your OpenShift Lab Has Been Deprovisioned - {cluster_id}",
        "template": "lab_deprovisioned",
        "data": {
            "cluster_id": cluster_id,
            "deprovision_date": deprovision_date,
            "deprovision_reason": deprovision_reason,
        },
    }

    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    if verbose:
        print("Message to publish:")
        print(json.dumps(message, indent=2))
        print()

    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)

        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        if verbose:
            print(f"Message published to queue '{queue_name}'")

        connection.close()
        return True

    except Exception as e:
        print(f"Error: Failed to publish message: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Publish email messages to RabbitMQ for OPL Email Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic lab_ready email
  %(prog)s \\
    --rabbitmq-url "amqp://localhost:5672/" \\
    --to "partner@example.com" \\
    --cluster-id "test-123" \\
    --console-url "https://console.example.com" \\
    --credentials-url "https://creds.example.com" \\
    --credentials-password "secret" \\
    --timezone "America/New_York" \\
    --expiration-date "2026-12-31"

  # With CC and multiple recipients
  %(prog)s \\
    --rabbitmq-url "amqp://localhost:5672/" \\
    --to "partner1@example.com" "partner2@example.com" \\
    --cc "sponsor@redhat.com" \\
    --cluster-id "test-123" \\
    --console-url "https://console.example.com" \\
    --credentials-url "https://creds.example.com" \\
    --credentials-password "secret" \\
    --timezone "Europe/London" \\
    --expiration-date "2026-12-31"

  # Cluster expiring warning
  %(prog)s \\
    --rabbitmq-url "amqp://localhost:5672/" \\
    --to "partner@example.com" \\
    --template lab_expiring \\
    --cluster-id "test-123" \\
    --expiration-date "2026-03-31" \\
    --days-remaining 7

Environment Variables:
  RABBITMQ_URL    RabbitMQ connection URL (can use instead of --rabbitmq-url)
        """,
    )

    # Connection settings
    parser.add_argument(
        "--rabbitmq-url",
        default=os.environ.get("RABBITMQ_URL"),
        help="RabbitMQ URL (e.g., amqp://user:pass@host:5672/) [env: RABBITMQ_URL]",
    )
    parser.add_argument(
        "--queue-name",
        default="opl-emails",
        help="RabbitMQ queue name (default: opl-emails)",
    )

    # Email recipients
    parser.add_argument(
        "--to",
        nargs="+",
        required=True,
        help="Recipient email address(es)",
    )
    parser.add_argument(
        "--cc",
        nargs="+",
        help="CC email address(es)",
    )
    parser.add_argument(
        "--bcc",
        nargs="+",
        help="BCC email address(es)",
    )

    # Template selection
    parser.add_argument(
        "--template",
        choices=["lab_ready", "lab_expiring", "lab_deprovisioned"],
        default="lab_ready",
        help="Email template to use (default: lab_ready)",
    )

    # Common fields
    parser.add_argument(
        "--cluster-id",
        required=True,
        help="Cluster identifier",
    )
    parser.add_argument(
        "--expiration-date",
        required=True,
        help="Cluster expiration date (YYYY-MM-DD)",
    )

    # lab_ready specific
    parser.add_argument(
        "--console-url",
        help="OpenShift console URL (required for lab_ready)",
    )
    parser.add_argument(
        "--credentials-url",
        help="Password-protected credentials URL (required for lab_ready)",
    )
    parser.add_argument(
        "--credentials-password",
        help="Password for credentials URL (required for lab_ready)",
    )
    parser.add_argument(
        "--timezone",
        help="Partner timezone (required for lab_ready)",
    )
    parser.add_argument(
        "--subject",
        help="Custom email subject (optional, defaults to 'OpenShift Partner Labs - <cluster-id>')",
    )

    # lab_expiring specific
    parser.add_argument(
        "--days-remaining",
        type=int,
        help="Days until expiration (required for lab_expiring)",
    )

    # lab_deprovisioned specific
    parser.add_argument(
        "--deprovision-date",
        help="Date cluster was deprovisioned (required for lab_deprovisioned)",
    )
    parser.add_argument(
        "--deprovision-reason",
        help="Reason for deprovisioning (required for lab_deprovisioned)",
    )

    # Other options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Validate RabbitMQ URL
    if not args.rabbitmq_url:
        print("Error: RabbitMQ URL required (use --rabbitmq-url or RABBITMQ_URL env var)", file=sys.stderr)
        sys.exit(1)

    # Route to appropriate function based on template
    if args.template == "lab_ready":
        # Validate required fields
        required = {
            "console-url": args.console_url,
            "credentials-url": args.credentials_url,
            "credentials-password": args.credentials_password,
            "timezone": args.timezone,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            print(f"Error: Missing required fields for lab_ready: {', '.join(missing)}", file=sys.stderr)
            print("Run with --help for usage examples", file=sys.stderr)
            sys.exit(1)

        success = publish_lab_ready_email(
            rabbitmq_url=args.rabbitmq_url,
            to=args.to,
            cluster_id=args.cluster_id,
            console_url=args.console_url,
            credentials_url=args.credentials_url,
            credentials_password=args.credentials_password,
            timezone=args.timezone,
            expiration_date=args.expiration_date,
            cc=args.cc,
            bcc=args.bcc,
            queue_name=args.queue_name,
            custom_subject=args.subject,
            verbose=args.verbose,
        )

    elif args.template == "lab_expiring":
        if not args.days_remaining:
            print("Error: --days-remaining required for lab_expiring template", file=sys.stderr)
            sys.exit(1)

        success = publish_lab_expiring_email(
            rabbitmq_url=args.rabbitmq_url,
            to=args.to,
            cluster_id=args.cluster_id,
            expiration_date=args.expiration_date,
            days_remaining=args.days_remaining,
            console_url=args.console_url,
            cc=args.cc,
            bcc=args.bcc,
            queue_name=args.queue_name,
            verbose=args.verbose,
        )

    elif args.template == "lab_deprovisioned":
        # Validate required fields
        required = {
            "deprovision-date": args.deprovision_date,
            "deprovision-reason": args.deprovision_reason,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            print(f"Error: Missing required fields for lab_deprovisioned: {', '.join(missing)}", file=sys.stderr)
            print("Run with --help for usage examples", file=sys.stderr)
            sys.exit(1)

        success = publish_lab_deprovisioned_email(
            rabbitmq_url=args.rabbitmq_url,
            to=args.to,
            cluster_id=args.cluster_id,
            deprovision_date=args.deprovision_date,
            deprovision_reason=args.deprovision_reason,
            cc=args.cc,
            bcc=args.bcc,
            queue_name=args.queue_name,
            verbose=args.verbose,
        )

    if success:
        print("✓ Message published successfully")
        sys.exit(0)
    else:
        print("✗ Failed to publish message", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
