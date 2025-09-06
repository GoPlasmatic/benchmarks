#!/bin/bash

# Advanced benchmark trigger script with custom configurations
# Usage: ./trigger-benchmark-advanced.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Advanced Reframe Benchmark Trigger ===${NC}"
echo ""

# Default values
VM_SIZES="2-core"
NUM_REQUESTS="5000"
CONCURRENT_LEVELS="64,128,256"
THREAD_COUNTS="auto"
MAX_TASKS="auto"
REFRAME_TAG="latest"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --vm-sizes)
            VM_SIZES="$2"
            shift 2
            ;;
        --requests)
            NUM_REQUESTS="$2"
            shift 2
            ;;
        --concurrent)
            CONCURRENT_LEVELS="$2"
            shift 2
            ;;
        --threads)
            THREAD_COUNTS="$2"
            shift 2
            ;;
        --max-tasks)
            MAX_TASKS="$2"
            shift 2
            ;;
        --tag)
            REFRAME_TAG="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --vm-sizes <sizes>      VM sizes to test (e.g., '2-core,4-core' or 'all')"
            echo "  --requests <num>        Number of requests per test (default: 5000)"
            echo "  --concurrent <levels>   Concurrent request levels (default: '64,128,256')"
            echo "  --threads <counts>      Thread counts to test (e.g., '1,2,4' or 'auto')"
            echo "  --max-tasks <counts>    Max concurrent tasks (e.g., '4,8,16' or 'auto')"
            echo "  --tag <tag>            Reframe Docker image tag (default: latest)"
            echo ""
            echo "Examples:"
            echo "  # Test 2-core VM with specific thread configurations"
            echo "  $0 --vm-sizes 2-core --threads 1,2 --max-tasks 4,8"
            echo ""
            echo "  # Test all VM sizes with auto-detected configurations"
            echo "  $0 --vm-sizes all --threads auto --max-tasks auto"
            echo ""
            echo "  # Quick test with low request count"
            echo "  $0 --vm-sizes 2-core --requests 1000 --concurrent 64"
            echo ""
            echo "  # Custom thread/task combinations"
            echo "  $0 --threads 2,4,8 --max-tasks 8,16,32"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "Configuration:"
echo "  VM Sizes: $VM_SIZES"
echo "  Requests: $NUM_REQUESTS"
echo "  Concurrent Levels: $CONCURRENT_LEVELS"
echo "  Thread Counts: $THREAD_COUNTS"
echo "  Max Tasks: $MAX_TASKS"
echo "  Reframe Tag: $REFRAME_TAG"
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub"
    echo "Run: gh auth login"
    exit 1
fi

echo -e "${GREEN}Triggering benchmark workflow...${NC}"

# Trigger the workflow
gh workflow run benchmark-reframe.yml \
    -f vm_sizes="$VM_SIZES" \
    -f num_requests="$NUM_REQUESTS" \
    -f concurrent_levels="$CONCURRENT_LEVELS" \
    -f thread_counts="$THREAD_COUNTS" \
    -f max_concurrent_tasks="$MAX_TASKS" \
    -f reframe_image_tag="$REFRAME_TAG"

echo ""
echo -e "${GREEN}Workflow triggered successfully!${NC}"
echo ""
echo "To view the run:"
echo "  gh run list --workflow=benchmark-reframe.yml --limit=1"
echo ""
echo "To watch the run:"
echo "  gh run watch"
echo ""
echo "To view logs:"
echo "  gh run view --log"