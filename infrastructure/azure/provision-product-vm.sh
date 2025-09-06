#!/bin/bash

# Provision a single product VM with specified configuration

set -e
set -o pipefail

# Default values
LOCATION="eastus"
RESOURCE_GROUP=""
VM_SIZE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --vm-size)
            VM_SIZE="$2"
            shift 2
            ;;
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
if [ -z "$VM_SIZE" ] || [ -z "$RESOURCE_GROUP" ]; then
    echo "Error: --vm-size and --resource-group are required"
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is not installed. Installing..." >&2
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y jq
    else
        echo "Error: Cannot install jq automatically" >&2
        exit 1
    fi
fi

# Load VM configuration
CONFIG_FILE="infrastructure/azure/vm-configs/${VM_SIZE}.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file not found: $CONFIG_FILE" >&2
    echo "Current directory: $(pwd)" >&2
    echo "Looking for: $CONFIG_FILE" >&2
    ls -la infrastructure/azure/vm-configs/ 2>&1 >&2 || echo "Directory not found" >&2
    exit 1
fi

# Extract configuration
AZURE_SKU=$(jq -r '.azure_sku' "$CONFIG_FILE" 2>&1) || {
    echo "Error: Failed to parse JSON with jq" >&2
    echo "jq error: $AZURE_SKU" >&2
    exit 1
}
DISK_SIZE=$(jq -r '.disk_size_gb' "$CONFIG_FILE")

if [ -z "$AZURE_SKU" ] || [ "$AZURE_SKU" = "null" ]; then
    echo "Error: Failed to extract azure_sku from config file" >&2
    echo "Config file contents:" >&2
    cat "$CONFIG_FILE" >&2
    exit 1
fi

echo "=========================================="
echo "Provisioning Product VM"
echo "VM Size: $VM_SIZE"
echo "Azure SKU: $AZURE_SKU"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "=========================================="

# Create Virtual Network
echo "Creating Virtual Network..." >&2
az network vnet create \
    --resource-group "$RESOURCE_GROUP" \
    --name "product-vnet-${VM_SIZE}" \
    --address-prefix "10.0.0.0/16" \
    --subnet-name "product-subnet" \
    --subnet-prefix "10.0.1.0/24" \
    --location "$LOCATION" 2>&1 | tee /dev/stderr || {
    echo "Error: Failed to create virtual network" >&2
    exit 1
}

# Create Network Security Group
echo "Creating Network Security Group..."
az network nsg create \
    --resource-group "$RESOURCE_GROUP" \
    --name "product-nsg-${VM_SIZE}" \
    --location "$LOCATION"

# Allow SSH access
az network nsg rule create \
    --resource-group "$RESOURCE_GROUP" \
    --nsg-name "product-nsg-${VM_SIZE}" \
    --name "AllowSSH" \
    --priority 1000 \
    --protocol Tcp \
    --direction Inbound \
    --source-address-prefixes "*" \
    --source-port-ranges "*" \
    --destination-address-prefixes "*" \
    --destination-port-ranges 22 \
    --access Allow

# Allow HTTP access for Reframe API
az network nsg rule create \
    --resource-group "$RESOURCE_GROUP" \
    --nsg-name "product-nsg-${VM_SIZE}" \
    --name "AllowHTTP" \
    --priority 1001 \
    --protocol Tcp \
    --direction Inbound \
    --source-address-prefixes "*" \
    --source-port-ranges "*" \
    --destination-address-prefixes "*" \
    --destination-port-ranges 3000 \
    --access Allow

# Create Product VM
echo "Creating Product VM (${AZURE_SKU})..."
# Generate unique names to avoid conflicts
TIMESTAMP=$(date +%s)
VM_NAME="reframe-vm-$(echo $VM_SIZE | sed 's/-//g')-${TIMESTAMP}"
IP_NAME="product-ip-$(echo $VM_SIZE | sed 's/-//g')-${TIMESTAMP}"

az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --image "Ubuntu2204" \
    --size "$AZURE_SKU" \
    --admin-username "azureuser" \
    --ssh-key-values ~/.ssh/id_rsa.pub \
    --vnet-name "product-vnet-${VM_SIZE}" \
    --subnet "product-subnet" \
    --nsg "product-nsg-${VM_SIZE}" \
    --public-ip-address "$IP_NAME" \
    --public-ip-sku Standard \
    --os-disk-size-gb "$DISK_SIZE" \
    --location "$LOCATION"

# Get VM IP
PRODUCT_VM_IP=$(az vm show -d \
    -g "$RESOURCE_GROUP" \
    -n "$VM_NAME" \
    --query publicIps -o tsv)

# Wait for VM to be ready
echo "Waiting for VM to be ready..."
sleep 30

# Install Docker
echo "Installing Docker on Product VM..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$PRODUCT_VM_IP" << 'EOF'
# Update system
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker azureuser

# Install monitoring tools
sudo apt-get install -y htop sysstat

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker
EOF

echo "=========================================="
echo "Product VM Provisioning Complete!"
echo "Product VM IP: $PRODUCT_VM_IP"
echo "=========================================="  >&2

# Return ONLY the IP address on stdout (last line)
echo "$PRODUCT_VM_IP"