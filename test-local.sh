#!/bin/bash
# Local test script to validate configuration

set -e

echo "Testing benchmark configuration..."
echo "================================="

# Check required environment variables
echo "Checking environment variables..."
required_vars=(
    "RESOURCE_GROUP"
    "PROJECT_NAME"
    "BENCHMARK_VM_SIZE"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Missing required variable: $var"
        exit 1
    else
        echo "✅ $var = ${!var}"
    fi
done

# Check if scripts are executable
echo ""
echo "Checking scripts..."
scripts=(
    "scripts/provision-vms.sh"
    "scripts/provision-native-vm.sh"
    "scripts/benchmark.py"
)

for script in "${scripts[@]}"; do
    if [ -f "$script" ]; then
        echo "✅ Found: $script"
        chmod +x "$script"
    else
        echo "❌ Missing: $script"
        exit 1
    fi
done

# Check GitHub Actions workflows
echo ""
echo "Checking workflows..."
workflows=(
    ".github/workflows/main.yml"
)

for workflow in "${workflows[@]}"; do
    if [ -f "$workflow" ]; then
        echo "✅ Found: $workflow"
        # Basic YAML validation
        python3 -c "import yaml; yaml.safe_load(open('$workflow'))" 2>/dev/null && \
            echo "  ✓ Valid YAML" || echo "  ⚠ YAML validation failed"
    else
        echo "❌ Missing: $workflow"
    fi
done

# Check if Reframe test script exists
echo ""
echo "Checking Reframe integration..."
if [ -f "../Reframe/test/simple_benchmark.py" ]; then
    echo "✅ Found Reframe benchmark script"
else
    echo "⚠ Reframe benchmark script not found at ../Reframe/test/simple_benchmark.py"
fi

# Check if docker-compose exists
if [ -f "../Reframe/docker-compose.yml" ]; then
    echo "✅ Found Reframe docker-compose.yml"
else
    echo "⚠ Reframe docker-compose.yml not found"
fi

# Test Python benchmark script syntax
echo ""
echo "Testing Python script syntax..."
python3 -m py_compile scripts/benchmark.py && \
    echo "✅ Python script syntax valid" || \
    echo "❌ Python script has syntax errors"

echo ""
echo "================================="
echo "Local tests completed!"
echo ""
echo "To run the benchmark pipeline:"
echo "  Docker-based: gh workflow run main.yml -f target_vm_size=Standard_B2s"
echo "  Native VM: gh workflow run benchmark-native.yml -f target_vm_size=Standard_B2s"