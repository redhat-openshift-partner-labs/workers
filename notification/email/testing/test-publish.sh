#!/bin/bash
#
# Test script to publish message to notification queue
# Uses RabbitMQ with opl vhost and proper queue names
#
# Usage: ./test-publish-new.sh [email@address.com]
#

set -euo pipefail

# Default email if not provided
EMAIL="${1:-test@example.com}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Publishing Test Email Notification ===${NC}"
echo ""

# Check for amqp-tools
if ! command -v amqp-publish &> /dev/null; then
    echo -e "${RED}Error: amqp-tools not installed${NC}" >&2
    echo "" >&2
    echo "Install with:" >&2
    echo "  macOS: brew install amqp-tools" >&2
    echo "  Debian/Ubuntu: apt-get install amqp-tools" >&2
    echo "  RHEL/Fedora: dnf install qpid-proton-c-devel" >&2
    echo "" >&2
    exit 1
fi

# Default namespace
NAMESPACE="${NAMESPACE:-partnerlabs}"

# Get RabbitMQ credentials from cluster
echo -e "${YELLOW}Fetching RabbitMQ credentials...${NC}"
if command -v oc &> /dev/null && oc whoami &> /dev/null; then
    RABBITMQ_USER=$(oc get secret user-worker-notification-user-credentials -n ${NAMESPACE} -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "")
    RABBITMQ_PASS=$(oc get secret user-worker-notification-user-credentials -n ${NAMESPACE} -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

    if [ -z "$RABBITMQ_USER" ] || [ -z "$RABBITMQ_PASS" ]; then
        echo -e "${YELLOW}Warning: Could not fetch credentials from cluster${NC}"
        echo "Using manual credentials..."
        RABBITMQ_USER="user-worker-notification"
        RABBITMQ_PASS="changeme"
    else
        echo -e "${GREEN}✓ Credentials fetched from cluster${NC}"
    fi
else
    echo -e "${YELLOW}Not connected to OpenShift, using manual credentials${NC}"
    RABBITMQ_USER="user-worker-notification"
    RABBITMQ_PASS="changeme"
fi

# RabbitMQ connection
RABBITMQ_URL="${RABBITMQ_URL:-amqp://${RABBITMQ_USER}:${RABBITMQ_PASS}@localhost:5672/opl}"

# Exchange and routing key (messages route through exchanges, not directly to queues)
# For testing: publish directly to opl.notify exchange (worker has write permission)
# In production: upstream systems publish to opl.provision which routes to notify queues
EXCHANGE="opl.notify"
ROUTING_KEY="notify.user.lab-ready"

# Create test message payload
MESSAGE=$(cat <<EOF
{
  "to": ["${EMAIL}"],
  "cc": null,
  "bcc": null,
  "subject": "Your OpenShift Lab is Ready!",
  "template": "lab_ready",
  "data": {
    "cluster_id": "test-cluster-001",
    "partner_name": "Test Partner",
    "console_url": "https://console-openshift-console.apps.test-cluster-001.example.com",
    "api_url": "https://api.test-cluster-001.example.com:6443",
    "credentials_url": "https://creds.openshiftpartnerlabs.com/test-cluster-001",
    "credentials_password": "test-password-123",
    "timezone": "America/New_York",
    "business_hours": "9am-5pm EST",
    "expiration_date": "2026-12-31",
    "expiration_days": 30
  }
}
EOF
)

echo ""
echo -e "${BLUE}Publishing message:${NC}"
echo "  RabbitMQ URL: ${RABBITMQ_URL//:*@/:***@}"
echo "  Exchange: ${EXCHANGE}"
echo "  Routing Key: ${ROUTING_KEY}"
echo "  Recipient: ${EMAIL}"
echo ""

# Publish message to exchange (not directly to queue)
if amqp-publish -u "${RABBITMQ_URL}" -e "${EXCHANGE}" -r "${ROUTING_KEY}" -b "${MESSAGE}"; then
    echo ""
    echo -e "${GREEN}✓ Message published successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Check worker logs:"
    echo "     oc logs -n ${NAMESPACE} -l app=opl-email-service -f"
    echo ""
    echo "  2. Check Mailhog UI to see the email:"
    echo "     oc get route mailhog-web -n ${NAMESPACE}"
    echo ""
    echo "  3. Verify message was consumed:"
    echo "     oc exec -n ${NAMESPACE} queue-server-0 -- rabbitmqctl list_queues -p opl name messages"
    echo ""
else
    echo ""
    echo -e "${RED}✗ Failed to publish message${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Ensure RabbitMQ port is forwarded:"
    echo "     oc port-forward -n ${NAMESPACE} svc/queue 5672:5672"
    echo ""
    echo "  2. Verify credentials:"
    echo "     oc get secret user-worker-notification-user-credentials -n ${NAMESPACE}"
    echo ""
    echo "  3. Check queue exists:"
    echo "     oc exec -n ${NAMESPACE} queue-server-0 -- rabbitmqctl list_queues -p opl"
    echo ""
    exit 1
fi
