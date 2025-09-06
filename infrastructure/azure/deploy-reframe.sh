#!/bin/bash

# Deploy Reframe Docker container with specific configuration

set -e

# Default values
VM_IP=""
VM_SIZE=""
IMAGE_TAG="latest"
ACR_SERVER="plasmatic.azurecr.io"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --vm-ip)
            VM_IP="$2"
            shift 2
            ;;
        --vm-size)
            VM_SIZE="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [ -z "$VM_IP" ] || [ -z "$VM_SIZE" ]; then
    echo "Error: --vm-ip and --vm-size are required"
    exit 1
fi

# Load VM configuration
CONFIG_FILE="infrastructure/azure/vm-configs/${VM_SIZE}.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file not found: $CONFIG_FILE"
    exit 1
fi

echo "=========================================="
echo "Deploying Reframe to $VM_IP"
echo "VM Size: $VM_SIZE"
echo "Image Tag: $IMAGE_TAG"
echo "=========================================="

# Copy configuration file to VM
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$CONFIG_FILE" azureuser@"$VM_IP":/tmp/vm-config.json

# Copy deployment script to VM
cat << 'DEPLOY_SCRIPT' > /tmp/deploy-reframe.sh
#!/bin/bash
set -e

# Load configuration
CONFIG_FILE="/tmp/vm-config.json"
THREAD_COUNTS=$(jq -r '.thread_counts[]' "$CONFIG_FILE")
MAX_CONCURRENT_TASKS=$(jq -r '.max_concurrent_tasks[]' "$CONFIG_FILE")

# Login to Azure Container Registry
echo "$ACR_PASSWORD" | docker login "$ACR_SERVER" -u "$ACR_USERNAME" --password-stdin

# Pull the latest image
docker pull "$ACR_SERVER/reframe:$IMAGE_TAG"

# Stop any existing containers
docker stop reframe-benchmark 2>/dev/null || true
docker rm reframe-benchmark 2>/dev/null || true

# Create docker-compose.yml
cat << EOF > /home/azureuser/docker-compose.yml
version: '3.8'

services:
  reframe:
    image: ${ACR_SERVER}/reframe:${IMAGE_TAG}
    container_name: reframe-benchmark
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
      - REFRAME_THREAD_COUNT=4
      - REFRAME_MAX_CONCURRENT_TASKS=16
    restart: unless-stopped
    mem_limit: 80%
    cpus: 0.95
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
EOF

# Start with default configuration (will be updated during tests)
docker compose up -d

# Wait for service to be ready
echo "Waiting for Reframe to start..."
for i in {1..30}; do
    if curl -s http://localhost:3000/health > /dev/null; then
        echo "Reframe is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# Verify deployment
curl -s http://localhost:3000/health | jq .
DEPLOY_SCRIPT

# Copy deployment script to VM
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    /tmp/deploy-reframe.sh azureuser@"$VM_IP":/home/azureuser/deploy-reframe.sh

# Execute deployment
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$VM_IP" << EOF
# Set environment variables
export ACR_SERVER="$ACR_SERVER"
export ACR_USERNAME="${ACR_USERNAME}"
export ACR_PASSWORD="${ACR_PASSWORD}"
export IMAGE_TAG="$IMAGE_TAG"

# Make script executable and run
chmod +x /home/azureuser/deploy-reframe.sh
/home/azureuser/deploy-reframe.sh
EOF

echo "=========================================="
echo "Reframe deployment complete!"
echo "API endpoint: http://$VM_IP:3000"
echo "==========================================