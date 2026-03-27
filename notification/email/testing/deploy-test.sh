#!/bin/bash
#
# Quick deployment script for PoC testing
# Deploys RabbitMQ, Mailhog, and Email Service
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== OPL Email Service - Test Deployment ===${NC}"
echo ""

# Check if oc is available
if ! command -v oc &> /dev/null; then
    echo -e "${RED}Error: oc CLI not found${NC}" >&2
    echo "Please install the OpenShift CLI and login to your cluster" >&2
    exit 1
fi

# Check if logged in
if ! oc whoami &> /dev/null; then
    echo -e "${RED}Error: Not logged in to OpenShift${NC}" >&2
    echo "Please login with: oc login <cluster-url>" >&2
    exit 1
fi

echo -e "${GREEN}✓ Logged in to OpenShift as $(oc whoami)${NC}"
echo ""

# Step 1: Deploy RabbitMQ
echo -e "${YELLOW}Step 1: Deploying RabbitMQ...${NC}"
oc create namespace rabbitmq --dry-run=client -o yaml | oc apply -f -
oc apply -f testing/rabbitmq-deployment.yaml

echo "Waiting for RabbitMQ to be ready..."
oc wait --for=condition=ready pod -l app=rabbitmq -n rabbitmq --timeout=120s
echo -e "${GREEN}✓ RabbitMQ deployed${NC}"
echo ""

# Step 2: Deploy Mailhog
echo -e "${YELLOW}Step 2: Deploying Mailhog (test SMTP)...${NC}"
oc apply -f testing/mailhog-deployment.yaml

echo "Waiting for Mailhog to be ready..."
oc wait --for=condition=ready pod -l app=mailhog -n partner-labs --timeout=60s
echo -e "${GREEN}✓ Mailhog deployed${NC}"
echo ""

# Step 3: Deploy Email Service
echo -e "${YELLOW}Step 3: Deploying Email Service to partner-labs namespace...${NC}"
# Use the partner-labs overlay
oc apply -k deploy/overlays/partner-labs/

echo "Waiting for Email Service to be ready..."
oc wait --for=condition=ready pod -l app=opl-email-service -n partner-labs --timeout=60s
echo -e "${GREEN}✓ Email Service deployed${NC}"
echo ""

# Get URLs
MAILHOG_URL=$(oc get route mailhog-web -n partner-labs -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-available")
RABBITMQ_URL=$(oc get route rabbitmq-management -n rabbitmq -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-available")

# Summary
echo -e "${GREEN}=== Deployment Complete! ===${NC}"
echo ""
echo "Resources deployed:"
echo "  ✓ RabbitMQ (namespace: rabbitmq)"
echo "  ✓ Mailhog (namespace: partner-labs)"
echo "  ✓ Email Service (namespace: partner-labs)"
echo ""
echo -e "${BLUE}Access URLs:${NC}"
if [ "$MAILHOG_URL" != "not-available" ]; then
    echo "  Mailhog UI: https://${MAILHOG_URL}"
else
    echo "  Mailhog UI: Not exposed (use port-forward: oc port-forward -n partner-labs svc/mailhog-web 8025:8025)"
fi
if [ "$RABBITMQ_URL" != "not-available" ]; then
    echo "  RabbitMQ Management: https://${RABBITMQ_URL} (admin/admin123)"
else
    echo "  RabbitMQ Management: Not exposed (use port-forward: oc port-forward -n rabbitmq svc/rabbitmq-management 15672:15672)"
fi
echo ""
echo -e "${BLUE}Verify deployment:${NC}"
echo "  oc get pods -n rabbitmq"
echo "  oc get pods -n partner-labs"
echo "  oc logs -n partner-labs -l app=opl-email-service -f"
echo ""
echo -e "${BLUE}Test it:${NC}"
echo "  # Port forward to RabbitMQ"
echo "  oc port-forward -n rabbitmq svc/rabbitmq 5672:5672"
echo ""
echo "  # In another terminal, publish test message"
echo "  cd scripts"
echo "  ./publish-email-message.py \\"
echo "    --rabbitmq-url \"amqp://admin:admin123@localhost:5672/\" \\"
echo "    --to \"test@example.com\" \\"
echo "    --cluster-id \"test-cluster-001\" \\"
echo "    --console-url \"https://console.example.com\" \\"
echo "    --credentials-url \"https://creds.example.com\" \\"
echo "    --credentials-password \"secret\" \\"
echo "    --timezone \"America/New_York\" \\"
echo "    --expiration-date \"2026-12-31\" \\"
echo "    --verbose"
echo ""
echo "  # Check Mailhog UI to see the email!"
if [ "$MAILHOG_URL" != "not-available" ]; then
    echo "  Open: https://${MAILHOG_URL}"
fi
echo ""
echo -e "${GREEN}For detailed instructions, see DEPLOYMENT.md${NC}"
echo ""
