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

echo "Preparing cloud-init for target VM..."
cat > /tmp/cloud-init-target.yml << EOF
#cloud-config
package_update: true
packages:
  - docker.io
  - docker-compose
  - curl

write_files:
  - path: /opt/reframe/docker-compose.yml
    content: |
      version: '3.8'
      services:
        reframe:
          image: ${ACR_URL}/reframe:${REFRAME_VERSION}
          container_name: reframe
          ports:
            - "3000:3000"
          environment:
            - RUST_LOG=error
            - REFRAME_THREAD_COUNT=${REFRAME_THREAD_COUNT}
            - REFRAME_MAX_CONCURRENT_TASKS=${REFRAME_MAX_CONCURRENT_TASKS}
          restart: unless-stopped
          healthcheck:
            test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
            interval: 10s
            timeout: 5s
            retries: 5

runcmd:
  - systemctl start docker
  - systemctl enable docker
  - docker login ${ACR_URL} -u ${ACR_USERNAME} -p ${ACR_PASSWORD}
  - cd /opt/reframe && docker-compose pull
  - cd /opt/reframe && docker-compose up -d
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
  --generate-ssh-keys \
  --no-wait

echo "Using cloud-init for benchmark runner..."
# Use the pre-created cloud-init file
cp ./scripts/cloud-init-runner.yml /tmp/cloud-init-runner.yml

echo "Creating benchmark runner VM..."
az vm create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "reframe-runner-${RUN_ID}" \
  --image "Ubuntu2204" \
  --size "${BENCHMARK_VM_SIZE}" \
  --vnet-name "benchmark-vnet-${RUN_ID}" \
  --subnet "benchmark-subnet" \
  --nsg "benchmark-nsg-${RUN_ID}" \
  --public-ip-address "" \
  --custom-data /tmp/cloud-init-runner.yml \
  --admin-username "azureuser" \
  --generate-ssh-keys

echo "Getting VM IPs..."
TARGET_IP=$(az vm list-ip-addresses \
  --resource-group "${RESOURCE_GROUP}" \
  --name "reframe-target-${RUN_ID}" \
  --query "[0].virtualMachine.network.privateIpAddresses[0]" -o tsv)

RUNNER_IP=$(az vm list-ip-addresses \
  --resource-group "${RESOURCE_GROUP}" \
  --name "reframe-runner-${RUN_ID}" \
  --query "[0].virtualMachine.network.privateIpAddresses[0]" -o tsv)

echo "Target VM IP: ${TARGET_IP}"
echo "Runner VM IP: ${RUNNER_IP}"

# Output for GitHub Actions
echo "target_vm_ip=${TARGET_IP}" >> $GITHUB_OUTPUT
echo "runner_vm_ip=${RUNNER_IP}" >> $GITHUB_OUTPUT
echo "run_id=${RUN_ID}" >> $GITHUB_OUTPUT