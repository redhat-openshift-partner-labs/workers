#!/bin/bash
#
# Cleanup script for test deployment
# Removes RabbitMQ, Mailhog, and Email Service
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== OPL Email Service - Cleanup ===${NC}"
echo ""

# Confirm deletion
read -p "This will delete all test deployments (RabbitMQ, Mailhog, Email Service). Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

echo ""
echo -e "${YELLOW}Deleting Email Service from partner-labs...${NC}"
oc delete -k deploy/overlays/partner-labs/ --ignore-not-found=true
echo -e "${GREEN}✓ Email Service deleted${NC}"
echo ""

echo -e "${YELLOW}Deleting Mailhog...${NC}"
oc delete -f testing/mailhog-deployment.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Mailhog deleted${NC}"
echo ""

echo -e "${YELLOW}Deleting RabbitMQ...${NC}"
oc delete -f testing/rabbitmq-deployment.yaml --ignore-not-found=true
oc delete namespace rabbitmq --ignore-not-found=true
echo -e "${GREEN}✓ RabbitMQ deleted${NC}"
echo ""

echo -e "${GREEN}=== Cleanup Complete ===${NC}"
echo ""
echo "All test resources have been removed."
echo ""
