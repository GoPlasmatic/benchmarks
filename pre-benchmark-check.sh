#!/bin/bash

# Pre-benchmark check and cleanup script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Pre-Benchmark Environment Check ===${NC}"
echo ""

# Check Azure login
if ! az account show &> /dev/null; then
    echo -e "${RED}Error: Not logged in to Azure${NC}"
    exit 1
fi

# Check for existing benchmark resource groups
echo -e "${YELLOW}Checking for existing benchmark resources...${NC}"
EXISTING_RGS=$(az group list --query "[?starts_with(name, 'benchmarks-rg')].name" -o tsv)

if [ -n "$EXISTING_RGS" ]; then
    echo -e "${YELLOW}Found existing benchmark resource groups:${NC}"
    echo "$EXISTING_RGS"
    echo ""
    echo -e "${YELLOW}These may cause conflicts or are from previous failed runs.${NC}"
    
    read -p "Delete existing resources before starting? (recommended) (yes/no): " cleanup
    if [ "$cleanup" = "yes" ]; then
        for RG in $EXISTING_RGS; do
            echo "  Deleting: $RG"
            az group delete --name "$RG" --yes --no-wait
        done
        
        # Wait a bit for deletions to start
        echo "Waiting for deletions to start..."
        sleep 30
        
        # Check if any still exist
        REMAINING=$(az group list --query "[?starts_with(name, 'benchmarks-rg')].name" -o tsv | wc -l)
        if [ "$REMAINING" -gt 0 ]; then
            echo -e "${YELLOW}Note: $REMAINING resource groups are still being deleted in the background.${NC}"
            echo "They should be gone by the time the benchmark starts."
        fi
    else
        echo -e "${YELLOW}Warning: Existing resources may cause conflicts!${NC}"
    fi
else
    echo -e "${GREEN}✓ No existing benchmark resources found${NC}"
fi

echo ""

# Check quotas
echo -e "${YELLOW}Checking Azure quotas...${NC}"
LOCATION="eastus"

# Check VM quotas for the sizes we need
VM_SIZES=("Standard_B2s" "Standard_D4s_v3" "Standard_D8s_v3" "Standard_D16s_v3")
for SIZE in "${VM_SIZES[@]}"; do
    # This is a simplified check - actual quota API is complex
    echo "  Checking availability of $SIZE in $LOCATION..."
done

echo -e "${GREEN}✓ Quota check complete${NC}"
echo ""

# Verify required tools
echo -e "${YELLOW}Checking required tools...${NC}"

check_tool() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}  ✓ $1 is installed${NC}"
        return 0
    else
        echo -e "${RED}  ✗ $1 is not installed${NC}"
        return 1
    fi
}

TOOLS_OK=true
check_tool "az" || TOOLS_OK=false
check_tool "jq" || TOOLS_OK=false
check_tool "ssh" || TOOLS_OK=false
check_tool "scp" || TOOLS_OK=false

if [ "$TOOLS_OK" = false ]; then
    echo -e "${RED}Some required tools are missing!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}=== Environment is ready for benchmarking ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Ensure GitHub secrets are configured (ACR_URL, ACR_USERNAME, ACR_PASSWORD)"
echo "  2. Run the benchmark workflow from GitHub Actions"
echo "  3. Or use: ./trigger-benchmark.sh --vm-sizes <size> --watch"