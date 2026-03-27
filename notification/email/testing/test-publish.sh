#!/bin/bash
# Test script to publish a message to RabbitMQ
# Requires amqp-tools: brew install amqp-tools

set -e

RABBITMQ_URL="${RABBITMQ_URL:-amqp://localhost}"
QUEUE_NAME="${QUEUE_NAME:-opl-emails}"
TO_EMAIL="${1:-your-email@example.com}"

echo "Publishing test email message to RabbitMQ..."
echo "  RabbitMQ: $RABBITMQ_URL"
echo "  Queue: $QUEUE_NAME"
echo "  To: $TO_EMAIL"

cat <<EOF | amqp-publish -u "$RABBITMQ_URL" -r "$QUEUE_NAME"
{
  "to": ["$TO_EMAIL"],
  "subject": "OpenShift Partner Labs - test-cluster-123",
  "template": "cluster-provisioned",
  "data": {
    "cluster_id": "test-cluster-123",
    "console_url": "https://console-openshift-console.apps.test-cluster.openshiftpartnerlabs.com",
    "credentials_url": "https://bin.apps.admin.openshiftpartnerlabs.com/?test123",
    "credentials_password": "test-password-example",
    "timezone": "America/New_York",
    "expiration_date": "2026-03-10"
  }
}
EOF

echo ""
echo "Message published! Check the email service logs."
