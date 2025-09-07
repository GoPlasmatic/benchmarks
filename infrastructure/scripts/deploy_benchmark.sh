#!/bin/bash

# Optimized Benchmark Deployment Script for Azure VMs
# This script sets up the environment with performance optimizations

set -e

# Configuration
VM_SIZE="${1:-8-core}"
REFRAME_URL="${2:-http://localhost:3000}"
NUM_REQUESTS="${3:-100000}"
CONCURRENT_LEVELS="${4:-64,128,256,512}"

echo "========================================="
echo "Optimized Benchmark Deployment"
echo "========================================="
echo "VM Size: $VM_SIZE"
echo "Reframe URL: $REFRAME_URL"
echo "Requests: $NUM_REQUESTS"
echo "Concurrent Levels: $CONCURRENT_LEVELS"
echo ""

# Function to optimize system settings
optimize_system() {
    echo "Applying system optimizations..."
    
    # Increase file descriptor limits
    sudo sysctl -w fs.file-max=2097152
    sudo sysctl -w fs.nr_open=2097152
    
    # Network optimizations for high throughput
    sudo sysctl -w net.core.somaxconn=65535
    sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65535
    sudo sysctl -w net.core.netdev_max_backlog=65535
    sudo sysctl -w net.ipv4.tcp_tw_reuse=1
    sudo sysctl -w net.ipv4.tcp_fin_timeout=15
    sudo sysctl -w net.ipv4.ip_local_port_range="1024 65535"
    
    # TCP optimizations
    sudo sysctl -w net.ipv4.tcp_keepalive_time=300
    sudo sysctl -w net.ipv4.tcp_keepalive_probes=5
    sudo sysctl -w net.ipv4.tcp_keepalive_intvl=15
    
    # Buffer sizes for high-throughput
    sudo sysctl -w net.core.rmem_default=262144
    sudo sysctl -w net.core.wmem_default=262144
    sudo sysctl -w net.core.rmem_max=134217728
    sudo sysctl -w net.core.wmem_max=134217728
    sudo sysctl -w net.ipv4.tcp_rmem="4096 262144 134217728"
    sudo sysctl -w net.ipv4.tcp_wmem="4096 262144 134217728"
    
    # Connection tracking for high connection count
    sudo sysctl -w net.netfilter.nf_conntrack_max=1000000
    sudo sysctl -w net.netfilter.nf_conntrack_tcp_timeout_established=1800
    
    # Update ulimits for the current session
    ulimit -n 1048576
    ulimit -u 32768
    
    echo "System optimizations applied."
}

# Function to setup Python environment
setup_python_env() {
    echo "Setting up Python environment..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install requirements
    pip install aiohttp psutil tabulate
    
    echo "Python environment ready."
}

# Function to run benchmark with specific configuration
run_benchmark_config() {
    local threads=$1
    local max_tasks=$2
    local concurrent=$3
    local test_name="${4:-test}"
    
    echo ""
    echo "--- Running Test: $test_name ---"
    echo "Threads: $threads, Max Tasks: $max_tasks, Concurrent: $concurrent"
    
    # Set environment variables for the server (if local)
    export REFRAME_THREAD_COUNT=$threads
    export REFRAME_MAX_CONCURRENT_TASKS=$max_tasks
    
    # Run the optimized benchmark
    python3 products/reframe/benchmark/optimized_benchmark.py \
        --base-url "$REFRAME_URL" \
        --vm-size "$VM_SIZE" \
        --num-requests "$NUM_REQUESTS" \
        --concurrent-levels "$concurrent" \
        --output-dir "results/${VM_SIZE}"
    
    # Cool down period between tests
    echo "Cooling down for 10 seconds..."
    sleep 10
}

# Main execution
main() {
    # Create results directory
    mkdir -p "results/${VM_SIZE}"
    
    # Apply system optimizations
    optimize_system
    
    # Setup Python environment
    setup_python_env
    
    # Load VM configuration
    CONFIG_FILE="infrastructure/azure/vm-configs/${VM_SIZE}.json"
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: Configuration file not found: $CONFIG_FILE"
        exit 1
    fi
    
    # Extract thread counts and max tasks from config
    THREAD_COUNTS=$(python3 -c "import json; print(','.join(map(str, json.load(open('$CONFIG_FILE'))['thread_counts'])))")
    MAX_TASKS=$(python3 -c "import json; print(','.join(map(str, json.load(open('$CONFIG_FILE'))['max_concurrent_tasks'])))")
    
    echo ""
    echo "Starting benchmark suite..."
    echo "Thread counts: $THREAD_COUNTS"
    echo "Max concurrent tasks: $MAX_TASKS"
    echo "Concurrent levels: $CONCURRENT_LEVELS"
    
    # Run benchmarks for each configuration
    IFS=',' read -ra THREADS <<< "$THREAD_COUNTS"
    IFS=',' read -ra TASKS <<< "$MAX_TASKS"
    IFS=',' read -ra LEVELS <<< "$CONCURRENT_LEVELS"
    
    test_num=0
    for thread in "${THREADS[@]}"; do
        for task in "${TASKS[@]}"; do
            for level in "${LEVELS[@]}"; do
                test_num=$((test_num + 1))
                run_benchmark_config "$thread" "$task" "$level" "test_${test_num}"
            done
        done
    done
    
    echo ""
    echo "========================================="
    echo "Benchmark suite completed!"
    echo "Results saved to: results/${VM_SIZE}/"
    echo "========================================="
}

# Run main function
main