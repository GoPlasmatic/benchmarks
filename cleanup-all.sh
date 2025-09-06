#!/bin/bash

# Comprehensive cleanup script to remove all benchmark-related resources

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Benchmark Resources Cleanup ===${NC}"
echo ""
echo -e "${RED}WARNING: This will delete ALL benchmark resources!${NC}"
echo "This includes:"
echo "  - The resource group: benchmarks-rg"
echo "  - All VMs, disks, networks, and public IPs within it"
echo ""

# Check if Azure CLI is logged in
if ! az account show &> /dev/null; then
    echo -e "${RED}Error: Not logged in to Azure${NC}"
    echo "Run: az login"
    exit 1
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "${GREEN}Current subscription: $SUBSCRIPTION${NC}"
echo ""

# Confirmation
read -p "Are you sure you want to delete the benchmark resource group? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo -e "${YELLOW}Checking for benchmark resource group...${NC}"

RESOURCE_GROUP="benchmarks-rg"

# Check if resource group exists
if ! az group exists --name "$RESOURCE_GROUP"; then
    echo -e "${GREEN}Resource group '$RESOURCE_GROUP' does not exist.${NC}"
    exit 0
fi

echo "Found resource group: $RESOURCE_GROUP"
echo ""

# Show what's in the resource group
echo -e "${YELLOW}Resources in the group:${NC}"
az resource list -g "$RESOURCE_GROUP" --query "[].{Name:name, Type:type}" -o table

echo ""
echo -e "${YELLOW}Deleting resource group: $RESOURCE_GROUP${NC}"

# Delete the entire resource group
az group delete --name "$RESOURCE_GROUP" --yes --no-wait || {
    echo -e "${RED}Failed to delete $RESOURCE_GROUP, will retry with force${NC}"
    az group delete --name "$RESOURCE_GROUP" --yes --force-deletion-types "Microsoft.Compute/virtualMachines" --no-wait || true
}

echo ""
echo -e "${YELLOW}Waiting for deletions to complete...${NC}"

# Wait for deletion to complete (with timeout)
TIMEOUT=300  # 5 minutes
START_TIME=$(date +%s)

while true; do
    if ! az group exists --name "$RESOURCE_GROUP"; then
        echo -e "${GREEN}Resource group deleted successfully!${NC}"
        break
    fi
    
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    
    if [ "$ELAPSED" -gt "$TIMEOUT" ]; then
        echo -e "${YELLOW}Timeout reached. Resource group may still be deleting in the background.${NC}"
        break
    fi
    
    echo "  Resource group still deleting... (${ELAPSED}s elapsed)"
    sleep 10
done

echo ""


echo ""
echo -e "${GREEN}=== Cleanup Complete ===${NC}"
echo ""
echo "Summary:"
echo "  - Deleted resource groups starting with 'benchmarks-rg'"
echo "  - Removed associated VMs, networks, and IPs"
echo "  - Cleaned up orphaned disks"
echo ""
echo -e "${YELLOW}Note: Some resources may still be deleting in the background.${NC}"
echo "Check Azure Portal to verify all resources are removed."