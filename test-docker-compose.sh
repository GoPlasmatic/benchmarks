#!/bin/bash

# Test the new Docker compose-based benchmark approach locally
echo "Testing Docker compose benchmark execution..."

# Test with minimal configuration
gh workflow run main.yml \
  -f target_vm_size="Standard_B2s" \
  -f benchmark_requests="1000" \
  -f benchmark_concurrent="8" \
  -f benchmark_configs="8,16" \
  -f reframe_thread_count="2" \
  -f reframe_max_concurrent_tasks="8" \
  -f reframe_version="latest"

echo "Workflow triggered. Monitor at:"
echo "https://github.com/${GITHUB_REPOSITORY}/actions"