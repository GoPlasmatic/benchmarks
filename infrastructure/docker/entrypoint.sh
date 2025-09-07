#!/bin/bash

# Entrypoint script for benchmark container
# Applies runtime optimizations and configures environment

set -e

echo "Initializing benchmark container..."

# Apply sysctl settings if running with privileges
if [ "$EUID" -eq 0 ]; then
    echo "Applying system optimizations..."
    sysctl -p /etc/sysctl.conf 2>/dev/null || true
fi

# Set ulimits
ulimit -n 1048576 2>/dev/null || true
ulimit -u 32768 2>/dev/null || true

# Export Python optimizations
export PYTHONUNBUFFERED=1
export PYTHONASYNCIODEBUG=0

# Use uvloop for better async performance
export PYTHON_ASYNCIO_LOOP_POLICY=uvloop

echo "Container ready. Starting benchmark..."
echo "Configuration:"
echo "  VM Size: $BENCHMARK_VM_SIZE"
echo "  Reframe URL: $REFRAME_URL"
echo "  Requests: $BENCHMARK_NUM_REQUESTS"
echo "  Concurrent: $BENCHMARK_CONCURRENT_LEVELS"
echo ""

# Execute the command
exec "$@"