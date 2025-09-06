#!/bin/bash

# Cleanup Azure resources after benchmarking

set -e

# Default values
RESOURCE_GROUP=""
FORCE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
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
echo "Cleaning up Azure Resources"
echo "Resource Group: $RESOURCE_GROUP"
echo "=========================================="

# Check if resource group exists
if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
    echo "Resource group $RESOURCE_GROUP does not exist. Nothing to clean up."
    exit 0
fi

# Confirmation prompt (unless --force is used)
if [ "$FORCE" != true ]; then
    echo ""
    echo "WARNING: This will delete all resources in resource group: $RESOURCE_GROUP"
    echo "This includes:"
    echo "  - Virtual Machines"
    echo "  - Network interfaces"
    echo "  - Public IP addresses"
    echo "  - Virtual networks"
    echo "  - Network security groups"
    echo "  - Disks"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "Cleanup cancelled."
        exit 0
    fi
fi

# Delete resource group and all contained resources
echo "Deleting resource group $RESOURCE_GROUP..."
# Using --force-deletion-types to ensure all resources including disks are deleted
az group delete \
    --name "$RESOURCE_GROUP" \
    --yes \
    --force-deletion-types "Microsoft.Compute/virtualMachines" \
    --no-wait

echo "=========================================="
echo "Cleanup initiated successfully!"
echo "Resource group deletion is in progress."
echo "This may take several minutes to complete."
echo "=========================================="

# Optional: Wait for deletion to complete
if [ "$FORCE" = true ]; then
    echo "Waiting for deletion to complete..."
    az group wait \
        --name "$RESOURCE_GROUP" \
        --deleted \
        --timeout 600 2>/dev/null || true
    
    echo "Resource group $RESOURCE_GROUP has been deleted."
fi