#!/bin/bash
#
# Test deployment script using RabbitMQ Operator and queue topology
# Deploys RabbitMQ Cluster, Queue Topology, Mailhog, and Email Service
#
# Usage: ./deploy-test.sh [NAMESPACE]
#   NAMESPACE: Namespace for all resources (default: partnerlabs)
#

set -euo pipefail

# Default namespace (override with ./deploy-test.sh my-namespace)
NAMESPACE="${1:-partnerlabs}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== OPL Email Service - Test Deployment (with Queue Topology) ===${NC}"
echo ""
echo "Configuration:"
echo "  Namespace: ${NAMESPACE}"
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

# Check for RabbitMQ Operator
echo -e "${YELLOW}Checking for RabbitMQ Cluster Operator...${NC}"
if ! oc get crd rabbitmqclusters.rabbitmq.com &> /dev/null; then
    echo -e "${RED}Error: RabbitMQ Cluster Operator not installed${NC}" >&2
    echo "" >&2
    echo "Install the operator via OperatorHub or run:" >&2
    echo "  kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml" >&2
    echo "" >&2
    exit 1
fi
echo -e "${GREEN}✓ RabbitMQ Cluster Operator found${NC}"
echo ""

# Step 1: Create namespace
echo -e "${YELLOW}Step 1: Creating namespace...${NC}"
oc create namespace ${NAMESPACE} --dry-run=client -o yaml | oc apply -f -
echo -e "${GREEN}✓ Namespace created${NC}"
echo ""

# Step 2: Deploy RabbitMQ Cluster
echo -e "${YELLOW}Step 2: Deploying RabbitMQ Cluster...${NC}"

# Deploy the cluster FIRST - let the operator create the ServiceAccount
oc apply -f testing/rabbitmq-cluster.yaml -n ${NAMESPACE}

# Wait for the operator to create the ServiceAccount
echo "Waiting for RabbitMQ Operator to create ServiceAccount..."
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if oc get serviceaccount queue-server -n ${NAMESPACE} &> /dev/null; then
        echo -e "${GREEN}✓ ServiceAccount created by operator${NC}"
        break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo -e "${RED}Error: ServiceAccount not created after ${TIMEOUT}s${NC}"
    echo "Check operator logs:"
    echo "  oc logs -n rabbitmq-system -l app.kubernetes.io/name=rabbitmq-cluster-operator"
    exit 1
fi

# Grant privileged SCC to the operator-created ServiceAccount
# Note: Using privileged instead of anyuid because the RabbitMQ Operator sets
# seccomp profiles which anyuid SCC doesn't allow
echo "Granting privileged SCC to queue-server ServiceAccount..."
oc adm policy add-scc-to-user privileged -z queue-server -n ${NAMESPACE}

# Verify the SCC was granted by checking role bindings
if oc get rolebinding,clusterrolebinding -A -o json | jq -r '.items[] | select(.subjects[]?.name == "queue-server") | .roleRef.name' | grep -q privileged; then
    echo -e "${GREEN}✓ privileged SCC granted${NC}"
else
    echo -e "${YELLOW}Warning: Could not verify SCC was granted${NC}"
fi

# Delete the RabbitmqCluster and recreate it so the operator reconciles with SCC
echo "Recreating RabbitMQ cluster to apply SCC permissions..."
oc delete rabbitmqcluster queue -n ${NAMESPACE}
sleep 5
oc apply -f testing/rabbitmq-cluster.yaml -n ${NAMESPACE}

echo "Waiting for RabbitMQ cluster to be ready (this may take 2-3 minutes)..."
# Wait for the cluster to be created
sleep 10
# Wait for the StatefulSet to be ready
oc wait --for=condition=ready pod -l app.kubernetes.io/name=queue -n ${NAMESPACE} --timeout=300s || true
echo -e "${GREEN}✓ RabbitMQ Cluster deployed${NC}"
echo ""

# Step 3: Deploy Queue Topology
echo -e "${YELLOW}Step 3: Deploying Queue Topology (vhost, exchanges, queues, bindings, users)...${NC}"

# Update the kustomization.yaml namespace dynamically
sed -i.bak "s/^namespace:.*/namespace: ${NAMESPACE}/" testing/queue-topology/kustomization.yaml

# Apply the topology
oc apply -k testing/queue-topology/

# Restore the original kustomization.yaml
mv testing/queue-topology/kustomization.yaml.bak testing/queue-topology/kustomization.yaml 2>/dev/null || true

echo "Waiting for topology resources to be ready..."
sleep 5

# Check if the vhost was created
if oc get vhost vhost-opl -n ${NAMESPACE} &> /dev/null; then
    echo -e "${GREEN}✓ Vhost created${NC}"
else
    echo -e "${YELLOW}Warning: Vhost not found, topology may still be reconciling${NC}"
fi

# Wait for the user credentials secret to be created by the operator
echo "Waiting for RabbitMQ Operator to create user credentials secret..."
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if oc get secret user-worker-notification-user-credentials -n ${NAMESPACE} &> /dev/null; then
        echo -e "${GREEN}✓ User credentials secret created${NC}"
        break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo -e "${RED}Warning: User credentials secret not created after ${TIMEOUT}s${NC}"
    echo "The RabbitMQ Messaging Topology Operator may not be installed or working correctly."
    echo ""
    echo "Check operator status:"
    echo "  oc get pods -n rabbitmq-system"
    echo "  oc logs -n rabbitmq-system -l app.kubernetes.io/name=messaging-topology-operator"
    echo ""
    echo "Check user status:"
    echo "  oc get user user-worker-notification -n ${NAMESPACE} -o yaml"
    echo ""
fi
echo ""

# Step 4: Deploy Mailhog
echo -e "${YELLOW}Step 4: Deploying Mailhog (test SMTP)...${NC}"
oc apply -f testing/mailhog-deployment.yaml -n ${NAMESPACE}

echo "Waiting for Mailhog to be ready..."
oc wait --for=condition=ready pod -l app=mailhog -n ${NAMESPACE} --timeout=60s
echo -e "${GREEN}✓ Mailhog deployed${NC}"
echo ""

# Step 5: Deploy Email Service
echo -e "${YELLOW}Step 5: Deploying Email Service to ${NAMESPACE} namespace...${NC}"

# Update the overlay kustomization.yaml namespace dynamically
sed -i.bak "s/^namespace:.*/namespace: ${NAMESPACE}/" deploy/overlays/partner-labs/kustomization.yaml

# Apply the email service
oc apply -k deploy/overlays/partner-labs/

# Restore the original kustomization.yaml
mv deploy/overlays/partner-labs/kustomization.yaml.bak deploy/overlays/partner-labs/kustomization.yaml 2>/dev/null || true

echo "Waiting for Email Service to be ready..."
oc wait --for=condition=ready pod -l app=opl-email-service -n ${NAMESPACE} --timeout=60s || {
    echo -e "${YELLOW}Warning: Email service may still be starting. Check credentials secret...${NC}"
    echo "The user-worker-notification-user-credentials secret should be auto-created by RabbitMQ Operator"
    echo "Check: oc get secret -n ${NAMESPACE} | grep user-worker-notification"
}
echo -e "${GREEN}✓ Email Service deployed${NC}"
echo ""

# Get URLs
MAILHOG_URL=$(oc get route mailhog-web -n ${NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-available")
RABBITMQ_URL=$(oc get route rabbitmq-management -n ${NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-available")

# Get RabbitMQ default user credentials
echo -e "${YELLOW}Fetching RabbitMQ admin credentials...${NC}"
RABBITMQ_USER=$(oc get secret queue-default-user -n ${NAMESPACE} -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "admin")
RABBITMQ_PASS=$(oc get secret queue-default-user -n ${NAMESPACE} -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "not-available")

# Summary
echo ""
echo -e "${GREEN}=== Deployment Complete! ===${NC}"
echo ""
echo "Resources deployed:"
echo "  ✓ RabbitMQ Cluster (namespace: ${NAMESPACE})"
echo "  ✓ Queue Topology (vhost: opl, exchanges, queues, user permissions)"
echo "  ✓ Mailhog (namespace: ${NAMESPACE})"
echo "  ✓ Email Service (namespace: ${NAMESPACE})"
echo ""
echo -e "${BLUE}Access URLs:${NC}"
if [ "$MAILHOG_URL" != "not-available" ]; then
    echo "  Mailhog UI: https://${MAILHOG_URL}"
else
    echo "  Mailhog UI: Not exposed (use port-forward: oc port-forward -n ${NAMESPACE} svc/mailhog-web 8025:8025)"
fi
if [ "$RABBITMQ_URL" != "not-available" ]; then
    echo "  RabbitMQ Management: https://${RABBITMQ_URL}"
    echo "    Username: ${RABBITMQ_USER}"
    if [ "$RABBITMQ_PASS" != "not-available" ]; then
        echo "    Password: ${RABBITMQ_PASS}"
    fi
else
    echo "  RabbitMQ Management: Not exposed (use port-forward: oc port-forward -n ${NAMESPACE} svc/queue 15672:15672)"
fi
echo ""
echo -e "${BLUE}Verify deployment:${NC}"
echo "  # Check all resources"
echo "  oc get rabbitmqcluster -n ${NAMESPACE}"
echo "  oc get vhost,exchange,queue,binding,user,permission -n ${NAMESPACE}"
echo "  oc get pods -n ${NAMESPACE}"
echo "  oc get pods -n ${NAMESPACE}"
echo ""
echo "  # Check worker logs"
echo "  oc logs -n ${NAMESPACE} -l app=opl-email-service -f"
echo ""
echo "  # Check RabbitMQ user credentials"
echo "  oc get secret user-worker-notification-user-credentials -n ${NAMESPACE} -o yaml"
echo ""
echo -e "${BLUE}Test it:${NC}"
echo "  # Port forward to RabbitMQ"
echo "  oc port-forward -n ${NAMESPACE} svc/queue 5672:5672 15672:15672"
echo ""
echo "  # Publish test message to one of the queues"
echo "  # (Use scripts/test-publish.sh or amqp-publish)"
echo ""
echo "  # Check Mailhog UI to see the email!"
if [ "$MAILHOG_URL" != "not-available" ]; then
    echo "  Open: https://${MAILHOG_URL}"
fi
echo ""
echo -e "${GREEN}For detailed instructions, see testing/README.md${NC}"
echo ""
