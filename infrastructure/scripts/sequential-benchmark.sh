#!/bin/bash

# Sequential Benchmark Orchestrator
# This script provisions VMs one at a time, runs benchmarks, and cleans up

set -e

echo "=========================================="
echo "Sequential Benchmark Orchestrator"
echo "=========================================="
echo "VM Sizes: $VM_SIZES"
echo "Benchmark VM: $BENCHMARK_VM_IP"
echo "Requests: $NUM_REQUESTS"
echo "Concurrent Levels: $CONCURRENT_LEVELS"
echo "=========================================="

# Convert comma-separated VM sizes to array
IFS=',' read -ra VM_SIZE_ARRAY <<< "$VM_SIZES"

# Track overall progress
TOTAL_VMS=${#VM_SIZE_ARRAY[@]}
CURRENT_VM=0

# Verify benchmark VM is ready before starting
echo "Verifying benchmark VM setup..."
if ! ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 azureuser@"$BENCHMARK_VM_IP" << 'EOF'
set -e
echo "Connected to benchmark VM"

# Check if enhanced_benchmark.py exists
if [ ! -f /home/azureuser/enhanced_benchmark.py ]; then
    echo "ERROR: Benchmark script not found on benchmark VM!"
    echo "Contents of /home/azureuser:"
    ls -la /home/azureuser/
    exit 1
fi

# Check Python packages
echo "Checking Python packages..."
if ! python3 -c "import aiohttp, requests, psutil, pandas, matplotlib, jinja2" 2>/dev/null; then
    echo "Installing missing Python packages..."
    pip3 install --user aiohttp requests psutil pandas matplotlib jinja2
fi

echo "Benchmark VM is ready!"
EOF
then
    echo "ERROR: Benchmark VM setup verification failed!"
    echo "Check if:"
    echo "  1. Benchmark VM IP is correct: $BENCHMARK_VM_IP"
    echo "  2. SSH key is properly configured"
    echo "  3. Benchmark scripts were copied to the VM"
    exit 1
fi

# Main loop - process each VM size sequentially
for VM_SIZE in "${VM_SIZE_ARRAY[@]}"; do
    CURRENT_VM=$((CURRENT_VM + 1))
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Processing VM $CURRENT_VM of $TOTAL_VMS: $VM_SIZE"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Step 1: Verify resource group exists
    echo "Step 1/8: Verifying resource group..."
    if ! az group show --name "${AZURE_RESOURCE_GROUP}" &>/dev/null; then
        echo "Creating resource group: ${AZURE_RESOURCE_GROUP}"
        az group create \
            --name "${AZURE_RESOURCE_GROUP}" \
            --location "$AZURE_LOCATION"
    else
        echo "Using existing resource group: ${AZURE_RESOURCE_GROUP}"
    fi
    
    # Step 2: Provision Product VM
    echo "Step 2/8: Provisioning $VM_SIZE Product VM..."
    
    # Run provisioning and capture output
    PROVISION_OUTPUT=$(bash infrastructure/azure/provision-product-vm.sh \
        --vm-size "$VM_SIZE" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --location "$AZURE_LOCATION" 2>&1)
    
    # Extract IP from the last line
    PRODUCT_VM_IP=$(echo "$PROVISION_OUTPUT" | tail -n 1)
    
    # Validate IP address
    if [[ ! "$PRODUCT_VM_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "ERROR: Failed to get valid Product VM IP address"
        echo "Provisioning output:"
        echo "$PROVISION_OUTPUT"
        echo "Skipping this VM configuration..."
        # Note: Not deleting resource group as it's shared
        continue
    fi
    
    echo "Product VM IP: $PRODUCT_VM_IP"
    
    # Step 3: Deploy Reframe application
    echo "Step 3/8: Deploying Reframe to Product VM..."
    
    # Debug: Check ACR variables
    echo "Debug: ACR_URL=${ACR_URL}"
    echo "Debug: ACR_USERNAME=${ACR_USERNAME}"
    echo "Debug: REFRAME_IMAGE_TAG=${REFRAME_IMAGE_TAG}"
    
    # Validate ACR configuration
    if [ -z "$ACR_URL" ] || [ -z "$ACR_USERNAME" ] || [ -z "$ACR_PASSWORD" ]; then
        echo "ERROR: ACR configuration is missing!"
        echo "  ACR_URL: ${ACR_URL:-'NOT SET'}"
        echo "  ACR_USERNAME: ${ACR_USERNAME:-'NOT SET'}"
        echo "  ACR_PASSWORD: ${ACR_PASSWORD:+'SET'}"
        echo "Skipping this VM configuration..."
        # Note: Not deleting resource group as it's shared
        continue
    fi
    
    # Login to ACR and deploy Reframe
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$PRODUCT_VM_IP" << EOF
# Login to Azure Container Registry
echo "Logging into ACR: ${ACR_URL}"
echo "$ACR_PASSWORD" | docker login ${ACR_URL} -u "$ACR_USERNAME" --password-stdin

if [ \$? -ne 0 ]; then
    echo "ERROR: Failed to login to ACR"
    exit 1
fi

# Pull the Reframe image
echo "Pulling image: ${ACR_URL}/reframe:${REFRAME_IMAGE_TAG}"
docker pull ${ACR_URL}/reframe:${REFRAME_IMAGE_TAG}

if [ \$? -ne 0 ]; then
    echo "ERROR: Failed to pull Reframe image"
    exit 1
fi

# Create docker-compose.yml (will be updated per test)
cat << COMPOSE > /home/azureuser/docker-compose.yml
services:
  reframe:
    image: ${ACR_URL}/reframe:${REFRAME_IMAGE_TAG}
    container_name: reframe-benchmark
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
      - REFRAME_THREAD_COUNT=4
      - REFRAME_MAX_CONCURRENT_TASKS=16
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 6G
          cpus: '0.95'
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
COMPOSE

# Start with default configuration
docker compose up -d
EOF
    
    # Step 4: Verify Reframe is running
    echo "Step 4/8: Verifying Reframe deployment..."
    for i in {1..30}; do
        if curl -s "http://${PRODUCT_VM_IP}:3000/health" > /dev/null 2>&1; then
            echo "✓ Reframe is running and healthy!"
            curl -s "http://${PRODUCT_VM_IP}:3000/health" | jq .
            break
        fi
        echo "Waiting for Reframe to start... ($i/30)"
        sleep 5
    done
    
    # Verify one more time
    if ! curl -s "http://${PRODUCT_VM_IP}:3000/health" > /dev/null 2>&1; then
        echo "ERROR: Reframe failed to start on $VM_SIZE VM!"
        echo "Skipping this VM and cleaning up..."
        az group delete --name "${AZURE_RESOURCE_GROUP}-${VM_SIZE}" --yes --no-wait
        continue
    fi
    
    # Step 5: Run benchmark tests
    echo "Step 5/8: Running benchmark tests on $VM_SIZE..."
    
    # Load VM configuration to get thread counts and max tasks
    CONFIG_FILE="infrastructure/azure/vm-configs/${VM_SIZE}.json"
    THREAD_COUNTS=$(jq -r '.thread_counts[]' "$CONFIG_FILE" | tr '\n' ' ')
    MAX_TASKS=$(jq -r '.max_concurrent_tasks[]' "$CONFIG_FILE" | tr '\n' ' ')
    
    TEST_NUM=0
    for thread_count in $THREAD_COUNTS; do
        for max_tasks in $MAX_TASKS; do
            TEST_NUM=$((TEST_NUM + 1))
            echo ""
            echo "--- Test Configuration $TEST_NUM for $VM_SIZE ---"
            echo "Thread Count: $thread_count"
            echo "Max Concurrent Tasks: $max_tasks"
            
            # Update Reframe configuration
            ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$PRODUCT_VM_IP" << EOF
# Stop current container
docker stop reframe-benchmark 2>/dev/null || true
docker rm reframe-benchmark 2>/dev/null || true

# Start with new configuration
docker run -d \
    --name reframe-benchmark \
    -p 3000:3000 \
    -e NODE_ENV=production \
    -e PORT=3000 \
    -e REFRAME_THREAD_COUNT=$thread_count \
    -e REFRAME_MAX_CONCURRENT_TASKS=$max_tasks \
    --restart unless-stopped \
    --memory="6g" \
    --cpus="0.95" \
    ${ACR_URL}/reframe:${REFRAME_IMAGE_TAG}

# Wait for service to be ready
sleep 10
EOF
            
            # Run benchmark on benchmark VM
            echo "Running benchmark test ${TEST_NUM} on benchmark VM..."
            echo "  Target: http://${PRODUCT_VM_IP}:3000"
            echo "  Requests: $NUM_REQUESTS"
            echo "  Concurrent levels: $CONCURRENT_LEVELS"
            echo "  Starting at: $(date)"
            
            # Use timeout command to prevent hanging (5 minutes max per test)
            if ! timeout 300 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                -o ServerAliveInterval=10 -o ServerAliveCountMax=3 \
                azureuser@"$BENCHMARK_VM_IP" << EOF
set -e
cd /home/azureuser

# Check if script exists
if [ ! -f enhanced_benchmark.py ]; then
    echo "ERROR: enhanced_benchmark.py not found!"
    ls -la
    exit 1
fi

echo "Starting benchmark execution..."

# Run benchmark with specific configuration (unbuffered output)
python3 -u enhanced_benchmark.py \
    --base-url "http://${PRODUCT_VM_IP}:3000" \
    --vm-size "$VM_SIZE" \
    --num-requests $NUM_REQUESTS \
    --concurrent-levels "$CONCURRENT_LEVELS" \
    --output-dir "results_${VM_SIZE}_test${TEST_NUM}"

echo "Benchmark execution completed for test ${TEST_NUM}"
EOF
            then
                echo "ERROR: Benchmark test ${TEST_NUM} timed out or failed!"
                continue
            fi
        done
    done
    
    # Step 6: Collect and aggregate results
    echo "Step 6/8: Collecting results for $VM_SIZE..."
    
    # Aggregate results on benchmark VM
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$BENCHMARK_VM_IP" << EOF
cd /home/azureuser
python3 << 'PYTHON'
import json
import glob
from pathlib import Path

vm_size = '$VM_SIZE'
all_results = []

# Collect all result files for this VM
for result_file in glob.glob(f'results_{vm_size}_*/benchmark_results_*.json'):
    with open(result_file) as f:
        data = json.load(f)
        for result in data.get('results', []):
            result['vm_size'] = vm_size
            all_results.append(result)

# Save aggregated results
output = {
    'vm_size': vm_size,
    'num_requests': $NUM_REQUESTS,
    'concurrent_levels': '$CONCURRENT_LEVELS'.split(','),
    'total_tests': len(all_results),
    'results': all_results
}

with open(f'aggregated_results_{vm_size}.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"Aggregated {len(all_results)} test results for {vm_size}")
PYTHON
EOF
    
    # Copy results to local machine
    mkdir -p "${RESULTS_DIR}/${VM_SIZE}"
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        azureuser@"$BENCHMARK_VM_IP":/home/azureuser/aggregated_results_${VM_SIZE}.json \
        "${RESULTS_DIR}/${VM_SIZE}/"
    
    # Step 7: Extract resource metrics (optional)
    echo "Step 7/8: Extracting Azure metrics for $VM_SIZE..."
    
    # Get VM name dynamically (since we use unique names)
    VM_NAME=$(az vm list \
        -g "${AZURE_RESOURCE_GROUP}" \
        --query "[?contains(name, '$VM_SIZE')].name | [0]" -o tsv)
    
    # Get basic VM metrics from Azure
    if [ -n "$VM_NAME" ]; then
        VM_METRICS=$(az vm show \
            --resource-group "${AZURE_RESOURCE_GROUP}" \
            --name "$VM_NAME" \
            --query "{vmSize: hardwareProfile.vmSize, location: location}" \
            -o json)
    else
        VM_METRICS='{"vmSize": "'$VM_SIZE'", "location": "'$AZURE_LOCATION'"}'
    fi
    
    echo "$VM_METRICS" > "${RESULTS_DIR}/${VM_SIZE}/vm_metrics.json"
    
    # Step 8: Cleanup VM for this size (but keep resource group)
    echo "Step 8/8: Cleaning up $VM_SIZE VM..."
    # Delete the specific VM to free resources
    if [ -n "$VM_NAME" ]; then
        echo "Deleting VM: $VM_NAME"
        az vm delete \
            --resource-group "${AZURE_RESOURCE_GROUP}" \
            --name "$VM_NAME" \
            --yes \
            --no-wait
    fi
    
    echo ""
    echo "✅ Completed benchmarking for $VM_SIZE"
    echo "Results saved to: ${RESULTS_DIR}/${VM_SIZE}/"
    
    # Clean up benchmark VM results for next run
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@"$BENCHMARK_VM_IP" << EOF
# Clean up test result directories but keep aggregated results
rm -rf results_${VM_SIZE}_*
EOF
    
    # Brief pause before next VM
    if [ $CURRENT_VM -lt $TOTAL_VMS ]; then
        echo "Waiting 30 seconds before provisioning next VM..."
        sleep 30
    fi
done

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  All benchmarks completed successfully!"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Summary:"
echo "- VMs tested: $TOTAL_VMS"
echo "- Results directory: $RESULTS_DIR"
echo ""

# Final cleanup - copy all aggregated results from benchmark VM
echo "Copying final aggregated results..."
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    azureuser@"$BENCHMARK_VM_IP":/home/azureuser/aggregated_results_*.json \
    "${RESULTS_DIR}/" 2>/dev/null || true

echo "Sequential benchmark execution complete!"