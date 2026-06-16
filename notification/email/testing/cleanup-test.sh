#!/bin/bash
#
# Cleanup script for test deployment
# Removes Email Service, Mailhog, Queue Topology, and RabbitMQ Cluster
#
# Usage: ./cleanup-test.sh [NAMESPACE]
#   NAMESPACE: Namespace for all resources (default: partnerlabs)
#

set -euo pipefail

# Default namespace (override with ./cleanup-test.sh my-namespace)
NAMESPACE="${1:-partnerlabs}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${YELLOW}=== OPL Email Service - Test Cleanup ===${NC}"
echo ""
echo "Configuration:"
echo "  Namespace: ${NAMESPACE}"
echo ""
echo "This will remove:"
echo "  - Email Service"
echo "  - Mailhog"
echo "  - Queue Topology"
echo "  - RabbitMQ Cluster"
echo "  - ${NAMESPACE} namespace"
echo ""

read -p "Are you sure you want to delete all test resources? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled"
    exit 0
fi

# Check if oc is available
if ! command -v oc &> /dev/null; then
    echo -e "${RED}Error: oc CLI not found${NC}" >&2
    exit 1
fi

# Check if logged in
if ! oc whoami &> /dev/null; then
    echo -e "${RED}Error: Not logged in to OpenShift${NC}" >&2
    exit 1
fi

echo ""
echo -e "${YELLOW}Removing Email Service...${NC}"
# Update the overlay namespace before deleting
sed -i.bak "s/^namespace:.*/namespace: ${NAMESPACE}/" deploy/overlays/partner-labs/kustomization.yaml
oc delete -k deploy/overlays/partner-labs/ --ignore-not-found=true
mv deploy/overlays/partner-labs/kustomization.yaml.bak deploy/overlays/partner-labs/kustomization.yaml 2>/dev/null || true
echo -e "${GREEN}✓ Email Service removed${NC}"

echo ""
echo -e "${YELLOW}Removing Mailhog...${NC}"
oc delete -f testing/mailhog-deployment.yaml -n ${NAMESPACE} --ignore-not-found=true
echo -e "${GREEN}✓ Mailhog removed${NC}"

echo ""
echo -e "${YELLOW}Removing Queue Topology...${NC}"
# Update the topology namespace before deleting
sed -i.bak "s/^namespace:.*/namespace: ${NAMESPACE}/" testing/queue-topology/kustomization.yaml
oc delete -k testing/queue-topology/ --ignore-not-found=true
mv testing/queue-topology/kustomization.yaml.bak testing/queue-topology/kustomization.yaml 2>/dev/null || true
echo -e "${GREEN}✓ Queue Topology removed${NC}"

echo ""
echo -e "${YELLOW}Removing RabbitMQ Cluster...${NC}"
oc delete -f testing/rabbitmq-cluster.yaml -n ${NAMESPACE} --ignore-not-found=true

# Remove SCC permission from ServiceAccount
echo "Removing privileged SCC from ServiceAccount..."
oc adm policy remove-scc-from-user privileged -z queue-server -n ${NAMESPACE} 2>/dev/null || true

# ServiceAccount will be deleted automatically when the RabbitmqCluster is deleted

echo "Waiting for RabbitMQ cluster to be deleted..."
sleep 5
echo -e "${GREEN}✓ RabbitMQ Cluster removed${NC}"

echo ""
echo -e "${YELLOW}Removing ${NAMESPACE} namespace...${NC}"
oc delete namespace ${NAMESPACE} --ignore-not-found=true
echo -e "${GREEN}✓ Namespace removed${NC}"

echo ""
echo -e "${GREEN}=== Cleanup Complete! ===${NC}"
echo ""
echo "Verify cleanup:"
echo "  oc get pods -n ${NAMESPACE}"
echo "  oc get pods -n ${NAMESPACE} -l app=opl-email-service"
echo "  oc get pods -n ${NAMESPACE} -l app=mailhog"
echo ""
