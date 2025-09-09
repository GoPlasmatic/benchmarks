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
# Thread count will be set to CPU count on the VM
REFRAME_THREAD_COUNT=${REFRAME_THREAD_COUNT:-0}

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

echo "Preparing cloud-init for native Reframe deployment..."
cat > /tmp/cloud-init-native.yml << EOF
#cloud-config
package_update: true
packages:
  - build-essential
  - pkg-config
  - libssl-dev
  - git
  - curl
  - jq
  - python3
  - python3-pip

write_files:
  - path: /opt/benchmark/benchmark.py
    permissions: '0755'
    owner: root:root
    content: |
$(cat ./scripts/benchmark.py | sed 's/^/      /')
  
  - path: /etc/systemd/system/reframe.service
    content: |
      [Unit]
      Description=Reframe Application
      After=network.target
      
      [Service]
      Type=simple
      User=reframe
      WorkingDirectory=/opt/reframe
      Environment="RUST_LOG=error"
      # Thread count will be set dynamically based on CPU count
      ExecStartPre=/bin/bash -c 'echo "REFRAME_THREAD_COUNT=\$(nproc)" >> /etc/environment'
      EnvironmentFile=/etc/environment
      ExecStart=/opt/reframe/reframe
      Restart=always
      RestartSec=10
      
      # Performance tuning
      LimitNOFILE=65536
      LimitNPROC=32768
      
      [Install]
      WantedBy=multi-user.target
  
  - path: /opt/setup-reframe-threads.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      # Set REFRAME_THREAD_COUNT to CPU count
      CPU_COUNT=\$(nproc)
      echo "Setting REFRAME_THREAD_COUNT to \${CPU_COUNT} (CPU count)"
      echo "REFRAME_THREAD_COUNT=\${CPU_COUNT}" >> /etc/environment

runcmd:
  # Set up thread count based on CPU
  - /opt/setup-reframe-threads.sh
  
  # Create reframe user
  - useradd -m -s /bin/bash reframe || true
  
  # Install Rust
  - curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  - source /root/.cargo/env
  
  # Extract Reframe from Docker image
  - mkdir -p /opt/reframe
  - cd /opt/reframe
  
  # Install Docker temporarily to extract the binary
  - apt-get install -y docker.io
  - systemctl start docker
  
  # Login to ACR and extract Reframe binary from Docker image
  - |
    echo "Extracting Reframe from Docker image..."
    docker login ${ACR_URL} -u ${ACR_USERNAME} -p ${ACR_PASSWORD}
    
    # Pull the Reframe image
    docker pull ${ACR_URL}/reframe:${REFRAME_VERSION}
    
    # Create a container without running it
    CONTAINER_ID=\$(docker create ${ACR_URL}/reframe:${REFRAME_VERSION})
    
    # Extract the binary and required files
    docker cp \$CONTAINER_ID:/app/reframe /opt/reframe/reframe
    docker cp \$CONTAINER_ID:/app/workflows /opt/reframe/workflows || true
    docker cp \$CONTAINER_ID:/app/scenarios /opt/reframe/scenarios || true
    
    # Clean up
    docker rm \$CONTAINER_ID
    
    # Uninstall Docker to save resources
    systemctl stop docker
    apt-get remove -y docker.io
    apt-get autoremove -y
  
  # Set permissions
  - chown -R reframe:reframe /opt/reframe
  - chmod +x /opt/reframe/reframe
  
  # Install Python dependencies for benchmark
  - pip3 install aiohttp
  
  # Start Reframe service
  - systemctl daemon-reload
  - systemctl enable reframe
  - systemctl start reframe
  
  # Wait for service to be ready
  - |
    for i in {1..30}; do
      if curl -f http://localhost:3000/health > /dev/null 2>&1; then
        echo "Reframe is ready!"
        break
      fi
      echo "Waiting for Reframe to start... (attempt \$i/30)"
      sleep 2
    done
EOF

echo "Creating target VM with native deployment..."
az vm create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "reframe-target-${RUN_ID}" \
  --image "Ubuntu2204" \
  --size "${TARGET_VM_SIZE}" \
  --vnet-name "benchmark-vnet-${RUN_ID}" \
  --subnet "benchmark-subnet" \
  --nsg "benchmark-nsg-${RUN_ID}" \
  --public-ip-address "" \
  --custom-data /tmp/cloud-init-native.yml \
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