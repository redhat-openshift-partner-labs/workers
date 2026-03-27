#!/bin/bash
#
# Quick test script for local RabbitMQ testing
#
# This script:
# 1. Checks if RabbitMQ is running locally
# 2. Publishes a test message
# 3. Shows instructions for checking results
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== OPL Email Service - Local Test ===${NC}"
echo ""

# Check if RabbitMQ is running
echo -e "${YELLOW}Checking RabbitMQ...${NC}"
if ! docker ps | grep -q rabbitmq; then
    echo -e "${RED}RabbitMQ container not found!${NC}"
    echo ""
    echo "Start RabbitMQ with:"
    echo -e "${GREEN}docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management${NC}"
    echo ""
    exit 1
fi
echo -e "${GREEN}✓ RabbitMQ is running${NC}"
echo ""

# Default test values
RABBITMQ_URL="${RABBITMQ_URL:-amqp://guest:guest@localhost:5672/}"
TO="${1:-test@example.com}"

echo -e "${YELLOW}Test Configuration:${NC}"
echo "  RabbitMQ URL: $RABBITMQ_URL"
echo "  Recipient: $TO"
echo ""

# Check if Python script exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/publish-email-message.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}Error: publish-email-message.py not found${NC}" >&2
    exit 1
fi

# Check if pika is installed
echo -e "${YELLOW}Checking Python dependencies...${NC}"
if ! python3 -c "import pika" 2>/dev/null; then
    echo -e "${YELLOW}Warning: pika not installed${NC}"
    echo "Install with: pip install pika"
    echo ""
    echo "Trying anyway..."
    echo ""
fi

# Publish test message
echo -e "${YELLOW}Publishing test message...${NC}"
echo ""

python3 "$PYTHON_SCRIPT" \
  --rabbitmq-url "$RABBITMQ_URL" \
  --to "$TO" \
  --cluster-id "test-cluster-$(date +%s)" \
  --console-url "https://console-openshift-console.apps.test.openshiftpartnerlabs.com" \
  --credentials-url "https://bin.apps.admin.openshiftpartnerlabs.com/?test123#abc" \
  --credentials-password "test-password-123" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31" \
  --verbose

echo ""
echo -e "${GREEN}=== Next Steps ===${NC}"
echo ""
echo "1. Check RabbitMQ Management UI:"
echo -e "   ${BLUE}http://localhost:15672${NC} (guest/guest)"
echo "   → Go to Queues → opl-emails to see the message"
echo ""
echo "2. Check email service logs (if running):"
echo -e "   ${BLUE}oc logs -n opl-email-service -l app=opl-email-service -f${NC}"
echo ""
echo "3. If using Mailhog, check the web UI for captured emails"
echo ""
