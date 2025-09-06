#!/bin/bash

# Provision a small benchmark VM for running benchmark scripts

set -e
set -o pipefail

# Default values
LOCATION="eastus"
RESOURCE_GROUP=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        --location)
            LOCATION="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [ -z "$RESOURCE_GROUP" ]; then
    echo "Error: --resource-group is required"
    exit 1
fi

echo "=========================================="
echo "Provisioning Benchmark VM"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "=========================================="

# Create Virtual Network
echo "Creating Virtual Network..."
az network vnet create \
    --resource-group "$RESOURCE_GROUP" \
    --name "benchmark-vnet" \
    --address-prefix "10.0.0.0/16" \
    --subnet-name "benchmark-subnet" \
    --subnet-prefix "10.0.1.0/24" \
    --location "$LOCATION"

# Create Network Security Group
echo "Creating Network Security Group..."
az network nsg create \
    --resource-group "$RESOURCE_GROUP" \
    --name "benchmark-nsg" \
    --location "$LOCATION"

# Allow SSH access
az network nsg rule create \
    --resource-group "$RESOURCE_GROUP" \
    --nsg-name "benchmark-nsg" \
    --name "AllowSSH" \
    --priority 1000 \
    --protocol Tcp \
    --direction Inbound \
    --source-address-prefixes "*" \
    --source-port-ranges "*" \
    --destination-address-prefixes "*" \
    --destination-port-ranges 22 \
    --access Allow

# Create Benchmark VM (runs benchmark scripts)
echo "Creating Benchmark VM (Standard_B2s)..."
# Generate unique names to avoid conflicts
TIMESTAMP=$(date +%s)
VM_NAME="benchmark-vm-${TIMESTAMP}"
IP_NAME="benchmark-ip-${TIMESTAMP}"

az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --image "Ubuntu2204" \
    --size "Standard_B2s" \
    --admin-username "azureuser" \
    --ssh-key-values ~/.ssh/id_rsa.pub \
    --vnet-name "benchmark-vnet" \
    --subnet "benchmark-subnet" \
    --nsg "benchmark-nsg" \
    --public-ip-address "$IP_NAME" \
    --public-ip-sku Standard \
    --os-disk-size-gb 32 \
    --location "$LOCATION"

# Get VM IP
BENCHMARK_VM_IP=$(az vm show -d \
    -g "$RESOURCE_GROUP" \
    -n "$VM_NAME" \
    --query publicIps -o tsv)

# Wait for VM to be ready
echo "Waiting for VM to be ready..."
sleep 30

# Install Python and dependencies
echo "Setting up Benchmark VM..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$BENCHMARK_VM_IP" << 'EOF'
# Update system
sudo apt-get update
sudo apt-get install -y python3 python3-pip git jq

# Install Python packages
pip3 install --user aiohttp requests psutil pandas matplotlib jinja2

# Create necessary directories
mkdir -p /home/azureuser/infrastructure/azure
mkdir -p /home/azureuser/results
EOF

echo "=========================================="  >&2
echo "Benchmark VM Provisioning Complete!"  >&2
echo "Benchmark VM IP: $BENCHMARK_VM_IP"  >&2
echo "=========================================="  >&2

# Return ONLY the IP address on stdout (last line)
echo "$BENCHMARK_VM_IP"