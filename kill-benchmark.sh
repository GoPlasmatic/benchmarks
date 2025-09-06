#!/bin/bash

# Kill stuck benchmark process

echo "Killing stuck benchmark processes..."

# Find and kill the GitHub Actions run
gh run list --workflow=benchmark-reframe.yml --limit 5 | grep "in_progress" | awk '{print $3}' | while read run_id; do
    echo "Cancelling run: $run_id"
    gh run cancel $run_id
done

echo "GitHub Actions runs cancelled."
echo ""
echo "To restart with reasonable settings, run:"
echo "  gh workflow run benchmark-reframe.yml -f vm_sizes=2-core -f num_requests=1000 -f concurrent_levels=64,128"