#!/bin/bash
# Port forward script for local testing
# Allows you to connect to RabbitMQ and Mailhog from your local machine

set -e

NAMESPACE="opl-email-service"

echo "========================================="
echo "Starting port forwarding for local testing"
echo "========================================="
echo ""
echo "Services:"
echo "  • RabbitMQ AMQP:       localhost:5672"
echo "  • RabbitMQ Management: localhost:15672"
echo "  • Mailhog Web UI:      localhost:8025"
echo ""
echo "Press Ctrl+C to stop all port forwards"
echo ""

# Trap Ctrl+C and kill all background jobs
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

# Port forward RabbitMQ AMQP
echo "Starting RabbitMQ AMQP port forward (5672)..."
oc port-forward -n $NAMESPACE svc/rabbitmq 5672:5672 &

# Port forward RabbitMQ Management UI
echo "Starting RabbitMQ Management port forward (15672)..."
oc port-forward -n $NAMESPACE svc/rabbitmq 15672:15672 &

# Port forward Mailhog web UI
echo "Starting Mailhog web UI port forward (8025)..."
oc port-forward -n $NAMESPACE svc/mailhog-web 8025:8025 &

echo ""
echo "✓ Port forwarding started!"
echo ""
echo "Access services at:"
echo "  • RabbitMQ Management: http://localhost:15672 (admin/admin-password-change-me)"
echo "  • Mailhog Web UI:      http://localhost:8025"
echo ""
echo "Publish test messages with:"
echo "  ./test-publish.sh your-email@example.com"
echo "  python3 test-publish-python.py your-email@example.com"
echo ""

# Wait for all background processes
wait
