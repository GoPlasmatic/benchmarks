#!/bin/bash

# Local testing script to verify configuration before running in GitHub Actions

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Benchmark Configuration Test ===${NC}"
echo ""

# Function to check secret
check_secret() {
    local name=$1
    local value=$2
    if [ -z "$value" ]; then
        echo -e "${RED}✗ $name is not set${NC}"
        return 1
    else
        if [ "$name" = "ACR_PASSWORD" ] || [ "$name" = "AZURE_STORAGE_KEY" ]; then
            echo -e "${GREEN}✓ $name is set (hidden)${NC}"
        else
            echo -e "${GREEN}✓ $name = $value${NC}"
        fi
        return 0
    fi
}

# Load environment from .env if exists
if [ -f .env ]; then
    echo -e "${YELLOW}Loading .env file...${NC}"
    export $(cat .env | grep -v '^#' | xargs)
    echo ""
fi

# Check required secrets
echo -e "${YELLOW}Checking required secrets:${NC}"
ERRORS=0

check_secret "ACR_URL" "$ACR_URL" || ((ERRORS++))
check_secret "ACR_USERNAME" "$ACR_USERNAME" || ((ERRORS++))
check_secret "ACR_PASSWORD" "$ACR_PASSWORD" || ((ERRORS++))

echo ""
echo -e "${YELLOW}Checking optional secrets:${NC}"
check_secret "AZURE_STORAGE_KEY" "$AZURE_STORAGE_KEY" || true

echo ""

# Test Docker login if credentials are available
if [ -n "$ACR_URL" ] && [ -n "$ACR_USERNAME" ] && [ -n "$ACR_PASSWORD" ]; then
    echo -e "${YELLOW}Testing ACR login...${NC}"
    echo "$ACR_PASSWORD" | docker login "$ACR_URL" -u "$ACR_USERNAME" --password-stdin 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ ACR login successful${NC}"
        
        # Test image existence
        echo -e "${YELLOW}Checking if Reframe image exists...${NC}"
        docker pull "${ACR_URL}/reframe:latest" --quiet 2>/dev/null
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Reframe image found${NC}"
        else
            echo -e "${RED}✗ Reframe image not found or not accessible${NC}"
            echo "  Make sure ${ACR_URL}/reframe:latest exists"
            ((ERRORS++))
        fi
    else
        echo -e "${RED}✗ ACR login failed${NC}"
        ((ERRORS++))
    fi
fi

echo ""

# Test Azure CLI
echo -e "${YELLOW}Checking Azure CLI...${NC}"
if command -v az &> /dev/null; then
    echo -e "${GREEN}✓ Azure CLI installed${NC}"
    
    # Check if logged in
    if az account show &> /dev/null; then
        SUBSCRIPTION=$(az account show --query name -o tsv)
        echo -e "${GREEN}✓ Logged in to Azure (Subscription: $SUBSCRIPTION)${NC}"
    else
        echo -e "${YELLOW}! Not logged in to Azure${NC}"
        echo "  Run: az login"
    fi
else
    echo -e "${RED}✗ Azure CLI not installed${NC}"
    echo "  Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    ((ERRORS++))
fi

echo ""

# Check GitHub CLI
echo -e "${YELLOW}Checking GitHub CLI...${NC}"
if command -v gh &> /dev/null; then
    echo -e "${GREEN}✓ GitHub CLI installed${NC}"
    
    if gh auth status &> /dev/null; then
        echo -e "${GREEN}✓ Authenticated with GitHub${NC}"
    else
        echo -e "${YELLOW}! Not authenticated with GitHub${NC}"
        echo "  Run: gh auth login"
    fi
else
    echo -e "${YELLOW}! GitHub CLI not installed${NC}"
    echo "  Install with: brew install gh"
fi

echo ""

# Summary
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}=== All checks passed! ===${NC}"
    echo ""
    echo "You can now run the benchmark with:"
    echo "  ./trigger-benchmark.sh --vm-sizes 2-core --num-requests 100 --watch"
else
    echo -e "${RED}=== Found $ERRORS errors ===${NC}"
    echo ""
    echo "Please fix the issues above before running the benchmark."
    echo ""
    echo "Create a .env file with:"
    echo "  ACR_URL=myregistry.azurecr.io"
    echo "  ACR_USERNAME=username"
    echo "  ACR_PASSWORD=password"
    echo "  AZURE_STORAGE_KEY=key (optional)"
fi

exit $ERRORS