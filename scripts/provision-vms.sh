#!/bin/bash
set -e

# Arguments
RESOURCE_GROUP=$1
LOCATION=$2
TARGET_VM_SIZE=$3
BENCHMARK_VM_SIZE=$4
RUN_ID=$5

# Environment variables (from GitHub secrets)
ACR_URL=${ACR_URL}
ACR_USERNAME=${ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD}
REFRAME_VERSION=${REFRAME_VERSION:-latest}
REFRAME_THREAD_COUNT=${REFRAME_THREAD_COUNT:-4}
REFRAME_MAX_CONCURRENT_TASKS=${REFRAME_MAX_CONCURRENT_TASKS:-16}

echo "Creating resource group: ${RESOURCE_GROUP}"
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" || true

echo "Creating virtual network..."
az network vnet create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "benchmark-vnet-${RUN_ID}" \
  --address-prefix "10.0.0.0/16" \
  --subnet-name "benchmark-subnet" \
  --subnet-prefix "10.0.1.0/24"

echo "Creating NSG..."
az network nsg create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "benchmark-nsg-${RUN_ID}"

# No public access rules needed - VMs communicate internally only

echo "Preparing cloud-init for target VM with benchmark runner..."
cat > /tmp/cloud-init-target.yml << EOF
#cloud-config
package_update: true
packages:
  - docker.io
  - docker-compose
  - curl
  - jq

write_files:
  - path: /opt/benchmark/benchmark.py
    permissions: '0755'
    owner: root:root
    content: |
$(cat ./scripts/benchmark.py | sed 's/^/      /')
  - path: /opt/reframe/docker-compose.yml
    content: |
      version: '3.8'
      services:
        reframe-app:
          image: ${ACR_URL}/reframe:${REFRAME_VERSION}
          container_name: reframe-app
          ports:
            - "3000:3000"
          environment:
            - RUST_LOG=error
            - REFRAME_THREAD_COUNT=${REFRAME_THREAD_COUNT}
            - REFRAME_MAX_CONCURRENT_TASKS=${REFRAME_MAX_CONCURRENT_TASKS}
          networks:
            - reframe-network
          healthcheck:
            test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
            interval: 10s
            timeout: 5s
            retries: 5
            start_period: 30s
        
        benchmark-runner:
          image: python:3.11-slim
          container_name: benchmark-runner
          depends_on:
            reframe-app:
              condition: service_healthy
          environment:
            - REFRAME_URL=http://reframe-app:3000
            - PYTHONUNBUFFERED=1
            - BENCHMARK_REQUESTS=\${BENCHMARK_REQUESTS:-100000}
            - BENCHMARK_CONFIGS=\${BENCHMARK_CONFIGS:-8,32,128}
            - BENCHMARK_WARMUP=10
          networks:
            - reframe-network
          profiles:
            - benchmark
          volumes:
            - /opt/benchmark/benchmark.py:/app/benchmark.py:ro
          command: sh -c "pip install --no-cache-dir aiohttp && python3 /app/benchmark.py"
      
      networks:
        reframe-network:
          driver: bridge

runcmd:
  - systemctl start docker
  - systemctl enable docker
  - docker login ${ACR_URL} -u ${ACR_USERNAME} -p ${ACR_PASSWORD}
  - mkdir -p /opt/benchmark
  - cd /opt/reframe && docker-compose pull
  - cd /opt/reframe && docker-compose up -d reframe-app
EOF

echo "Creating target VM..."
az vm create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "reframe-target-${RUN_ID}" \
  --image "Ubuntu2204" \
  --size "${TARGET_VM_SIZE}" \
  --vnet-name "benchmark-vnet-${RUN_ID}" \
  --subnet "benchmark-subnet" \
  --nsg "benchmark-nsg-${RUN_ID}" \
  --public-ip-address "" \
  --custom-data /tmp/cloud-init-target.yml \
  --admin-username "azureuser" \
  --generate-ssh-keys

echo "Getting VM IP..."
TARGET_IP=$(az vm list-ip-addresses \
  --resource-group "${RESOURCE_GROUP}" \
  --name "reframe-target-${RUN_ID}" \
  --query "[0].virtualMachine.network.privateIpAddresses[0]" -o tsv)

echo "Target VM IP: ${TARGET_IP}"

# Output for GitHub Actions
echo "target_vm_ip=${TARGET_IP}" >> $GITHUB_OUTPUT
echo "run_id=${RUN_ID}" >> $GITHUB_OUTPUT