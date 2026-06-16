#!/bin/bash
#
# Check if required RabbitMQ operators are installed and working
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Checking RabbitMQ Operators ===${NC}"
echo ""

# Check if oc is available
if ! command -v oc &> /dev/null; then
    echo -e "${RED}Error: oc CLI not found${NC}" >&2
    exit 1
fi

# Check RabbitMQ Cluster Operator CRDs
echo -e "${YELLOW}1. Checking RabbitMQ Cluster Operator...${NC}"
if oc get crd rabbitmqclusters.rabbitmq.com &> /dev/null; then
    echo -e "${GREEN}✓ RabbitmqCluster CRD found${NC}"

    # Check if operator is running
    if oc get deployment rabbitmq-cluster-operator -n rabbitmq-system &> /dev/null 2>&1; then
        REPLICAS=$(oc get deployment rabbitmq-cluster-operator -n rabbitmq-system -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
        if [ "$REPLICAS" -gt 0 ]; then
            echo -e "${GREEN}✓ RabbitMQ Cluster Operator is running (${REPLICAS} replicas)${NC}"
        else
            echo -e "${RED}✗ RabbitMQ Cluster Operator deployment exists but no replicas available${NC}"
        fi
    else
        echo -e "${YELLOW}Warning: Could not find operator deployment in rabbitmq-system namespace${NC}"
        echo "  Operator might be in a different namespace"
    fi
else
    echo -e "${RED}✗ RabbitMQ Cluster Operator NOT installed${NC}"
    echo ""
    echo "Install with:"
    echo "  kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"
    echo ""
    exit 1
fi
echo ""

# Check RabbitMQ Messaging Topology Operator CRDs
echo -e "${YELLOW}2. Checking RabbitMQ Messaging Topology Operator...${NC}"
TOPOLOGY_CRDS=(
    "queues.rabbitmq.com"
    "exchanges.rabbitmq.com"
    "bindings.rabbitmq.com"
    "vhosts.rabbitmq.com"
    "users.rabbitmq.com"
    "permissions.rabbitmq.com"
)

ALL_CRDS_FOUND=true
for crd in "${TOPOLOGY_CRDS[@]}"; do
    if oc get crd "$crd" &> /dev/null; then
        echo -e "${GREEN}✓ $crd${NC}"
    else
        echo -e "${RED}✗ $crd NOT FOUND${NC}"
        ALL_CRDS_FOUND=false
    fi
done

if [ "$ALL_CRDS_FOUND" = true ]; then
    echo -e "${GREEN}✓ All Messaging Topology CRDs found${NC}"

    # Check if operator is running
    if oc get deployment messaging-topology-operator -n rabbitmq-system &> /dev/null 2>&1; then
        REPLICAS=$(oc get deployment messaging-topology-operator -n rabbitmq-system -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
        if [ "$REPLICAS" -gt 0 ]; then
            echo -e "${GREEN}✓ Messaging Topology Operator is running (${REPLICAS} replicas)${NC}"
        else
            echo -e "${RED}✗ Messaging Topology Operator deployment exists but no replicas available${NC}"
        fi
    else
        echo -e "${YELLOW}Warning: Could not find operator deployment in rabbitmq-system namespace${NC}"
    fi
else
    echo -e "${RED}✗ RabbitMQ Messaging Topology Operator NOT fully installed${NC}"
    echo ""
    echo "Install with:"
    echo "  kubectl apply -f https://github.com/rabbitmq/messaging-topology-operator/releases/latest/download/messaging-topology-operator-with-certmanager.yaml"
    echo ""
    echo "Or check if cert-manager is installed (required dependency):"
    echo "  oc get pods -n cert-manager"
    echo ""
    exit 1
fi
echo ""

# Summary
echo -e "${GREEN}=== All Required Operators Installed ===${NC}"
echo ""
echo "You can now deploy the test environment:"
echo "  ./testing/deploy-test-new.sh"
echo ""
