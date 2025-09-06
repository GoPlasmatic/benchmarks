#!/bin/bash

# Force cleanup of ALL benchmark-related resources
# This script will find and delete all resources even if they're orphaned

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Force Cleanup of ALL Benchmark Resources ===${NC}"
echo ""
echo -e "${RED}WARNING: This will delete ALL benchmark-related resources across ALL resource groups!${NC}"
echo ""

# Check Azure login
if ! az account show &> /dev/null; then
    echo -e "${RED}Error: Not logged in to Azure${NC}"
    exit 1
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "${GREEN}Current subscription: $SUBSCRIPTION${NC}"
echo ""

read -p "Are you SURE you want to force cleanup all benchmark resources? (type 'yes' to confirm): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo -e "${YELLOW}Step 1: Looking for benchmark resource groups...${NC}"

# Find all resource groups with benchmark prefix
RESOURCE_GROUPS=$(az group list --query "[?contains(name, 'benchmark')].name" -o tsv)

if [ -n "$RESOURCE_GROUPS" ]; then
    echo "Found resource groups:"
    echo "$RESOURCE_GROUPS"
    
    for RG in $RESOURCE_GROUPS; do
        echo ""
        echo -e "${YELLOW}Deleting resource group: $RG${NC}"
        az group delete --name "$RG" --yes --no-wait || true
    done
fi

echo ""
echo -e "${YELLOW}Step 2: Looking for orphaned disks...${NC}"

# Find all disks with benchmark in the name
DISKS=$(az disk list --query "[?contains(name, 'benchmark')].{Name:name, RG:resourceGroup}" -o tsv)

if [ -n "$DISKS" ]; then
    echo "Found orphaned disks:"
    echo "$DISKS"
    
    while IFS=$'\t' read -r DISK_NAME RG; do
        echo "Deleting disk: $DISK_NAME in $RG"
        az disk delete --name "$DISK_NAME" --resource-group "$RG" --yes --no-wait || true
    done <<< "$DISKS"
else
    echo "No orphaned disks found"
fi

echo ""
echo -e "${YELLOW}Step 3: Looking for orphaned network interfaces...${NC}"

# Find all NICs with benchmark in the name
NICS=$(az network nic list --query "[?contains(name, 'benchmark')].{Name:name, RG:resourceGroup}" -o tsv)

if [ -n "$NICS" ]; then
    echo "Found orphaned NICs:"
    echo "$NICS"
    
    while IFS=$'\t' read -r NIC_NAME RG; do
        echo "Deleting NIC: $NIC_NAME in $RG"
        az network nic delete --name "$NIC_NAME" --resource-group "$RG" --no-wait || true
    done <<< "$NICS"
else
    echo "No orphaned NICs found"
fi

echo ""
echo -e "${YELLOW}Step 4: Looking for orphaned public IPs...${NC}"

# Find all public IPs with benchmark in the name
IPS=$(az network public-ip list --query "[?contains(name, 'benchmark')].{Name:name, RG:resourceGroup}" -o tsv)

if [ -n "$IPS" ]; then
    echo "Found orphaned public IPs:"
    echo "$IPS"
    
    while IFS=$'\t' read -r IP_NAME RG; do
        echo "Deleting public IP: $IP_NAME in $RG"
        az network public-ip delete --name "$IP_NAME" --resource-group "$RG" --no-wait || true
    done <<< "$IPS"
else
    echo "No orphaned public IPs found"
fi

echo ""
echo -e "${YELLOW}Step 5: Looking for orphaned NSGs...${NC}"

# Find all NSGs with benchmark in the name
NSGS=$(az network nsg list --query "[?contains(name, 'benchmark')].{Name:name, RG:resourceGroup}" -o tsv)

if [ -n "$NSGS" ]; then
    echo "Found orphaned NSGs:"
    echo "$NSGS"
    
    while IFS=$'\t' read -r NSG_NAME RG; do
        echo "Deleting NSG: $NSG_NAME in $RG"
        az network nsg delete --name "$NSG_NAME" --resource-group "$RG" --no-wait || true
    done <<< "$NSGS"
else
    echo "No orphaned NSGs found"
fi

echo ""
echo -e "${YELLOW}Step 6: Looking for orphaned virtual networks...${NC}"

# Find all VNets with benchmark in the name
VNETS=$(az network vnet list --query "[?contains(name, 'benchmark')].{Name:name, RG:resourceGroup}" -o tsv)

if [ -n "$VNETS" ]; then
    echo "Found orphaned VNets:"
    echo "$VNETS"
    
    while IFS=$'\t' read -r VNET_NAME RG; do
        echo "Deleting VNet: $VNET_NAME in $RG"
        az network vnet delete --name "$VNET_NAME" --resource-group "$RG" --no-wait || true
    done <<< "$VNETS"
else
    echo "No orphaned VNets found"
fi

echo ""
echo -e "${YELLOW}Step 7: Checking specific resource group 'benchmarks-rg'...${NC}"

# Try to delete the main resource group
if az group show --name "benchmarks-rg" &>/dev/null; then
    echo "Found benchmarks-rg, deleting..."
    az group delete --name "benchmarks-rg" --yes --no-wait || true
else
    echo "benchmarks-rg not found or already deleted"
fi

echo ""
echo -e "${YELLOW}Waiting for deletions to complete (max 2 minutes)...${NC}"

TIMEOUT=120
START_TIME=$(date +%s)

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    
    if [ "$ELAPSED" -gt "$TIMEOUT" ]; then
        echo "Timeout reached. Resources may still be deleting in the background."
        break
    fi
    
    # Check if main resource group still exists
    if ! az group show --name "benchmarks-rg" &>/dev/null; then
        echo -e "${GREEN}Main resource group deleted!${NC}"
        break
    fi
    
    echo "  Still deleting... (${ELAPSED}s elapsed)"
    sleep 10
done

echo ""
echo -e "${GREEN}=== Force Cleanup Complete ===${NC}"
echo ""
echo "Summary:"
echo "  - Deleted all benchmark-related resource groups"
echo "  - Removed orphaned disks, NICs, IPs, NSGs, and VNets"
echo ""
echo -e "${YELLOW}Note: Some resources may still be deleting in the background.${NC}"
echo "Run 'az resource list --query \"[?contains(name, 'benchmark')]\"' to verify"
echo ""
echo "Current quota usage:"
az vm list-usage --location eastus --query "[?name.value=='cores'].{Name:name.value, Current:currentValue, Limit:limit}" -o table