# Automated Benchmarking System

## Overview
Automated benchmarking pipeline for Reframe application using GitHub Actions, Azure infrastructure, and both containerized and native VM deployments.

### Key Updates
- **Automatic Thread Count Configuration**: Reframe now automatically sets thread count equal to CPU count for optimal performance
- **Native VM Deployment**: Direct VM deployment without Docker overhead for performance testing
- **Dual Deployment Options**: Support for both Docker-based and native deployments

## Architecture

### Components
- **Reframe Application**: Target application to benchmark (located in `../Reframe`)
- **Benchmark Runner**: Dedicated VM (Standard_B2ls_v2) running Docker container with benchmark
- **Target VMs**: Variable-sized VMs hosting Reframe application
- **GitHub Actions**: Orchestration layer following infra-automation patterns
- **Azure Container Registry**: Hosts Reframe Docker images (org-level ACR)
- **Resource Group**: Single ephemeral resource group for all resources
- **Private Network**: VMs communicate via Azure VNet (no public IPs)
- **Report Storage**: Results committed to `reports/` directory in repo

### Workflow Stages
1. **Infrastructure Provisioning**: Terraform-based Azure resource creation
2. **Application Deployment**: Docker-based deployment from ACR
3. **Benchmark Execution**: Performance testing from dedicated runner
4. **Report Generation**: Metrics collection and artifact storage
5. **Cleanup**: Complete resource teardown and cost optimization

### Integration Points
- **infra-automation**: Reuses deployment scripts and Docker configurations
- **Reframe**: Source application with Dockerfile for containerization
- **Benchmark Script**: Uses existing `../Reframe/test/simple_benchmark.py`
- **Organization Secrets**: Leverages existing Azure and ACR credentials

## Directory Structure
```
benchmarks/
├── .github/
│   └── workflows/         # GitHub Actions workflows
│       ├── provision.yml   # Infrastructure provisioning via Azure CLI
│       ├── deploy.yml      # Application deployment
│       ├── benchmark.yml   # Benchmark execution
│       ├── cleanup.yml     # Resource cleanup
│       └── main.yml        # Main orchestration workflow
├── scripts/               # Deployment and utility scripts
│   ├── provision-vms.sh   # Create Azure resources
│   ├── cloud-init-runner.yml  # Benchmark runner initialization
│   ├── cloud-init-target.yml  # Target VM initialization
│   └── docker-compose-benchmark.yml  # Benchmark runner compose file
├── benchmark/
│   └── configs/           # Benchmark configurations
└── reports/               # Stored benchmark reports
    ├── benchmark_B2s_2024-01-15_001.json
    ├── benchmark_B4ms_2024-01-15_002.json
    └── ...
```

## Prerequisites
- Azure subscription with appropriate permissions
- GitHub repository with Actions enabled
- Azure Container Registry with Reframe Docker image (org-level ACR)
- Service Principal for Azure authentication (org-level secret)

## Configuration

### GitHub Organization Secrets (Available)
These secrets are configured at the organization level and available to this repository:

#### Azure & Infrastructure
- `AZURE_CREDENTIALS`: Service Principal JSON for Azure authentication

#### Azure Container Registry
- `ACR_URL`: Azure Container Registry URL
- `ACR_USERNAME`: Container registry username
- `ACR_PASSWORD`: Container registry password

### GitHub Variables (Configured)
These variables are already configured at the repository/organization level:
- `PROJECT_NAME`: `reframe-benchmark`
- `RESOURCE_GROUP`: `reframe-benchmark-resources`
- `BENCHMARK_VM_SIZE`: `Standard_B2ls_v2` (fixed)
- `AZURE_LOCATION`: Azure region (if configured, otherwise defaults to `East US`)

### Workflow Input Parameters
These parameters can be provided when triggering the workflow:

#### VM Configuration
- `TARGET_VM_SIZE`: Target VM size (e.g., `Standard_B2s`, `Standard_B4ms`, `Standard_B8ms`)

#### Benchmark Configuration
- `BENCHMARK_REQUESTS`: Total number of requests (default: 100000)
- `BENCHMARK_CONCURRENT`: Number of concurrent connections (default: 128)
- `BENCHMARK_CONFIGS`: Comma-separated concurrency levels (default: "8,32,128,256")

#### Reframe Performance Tuning
- `REFRAME_THREAD_COUNT`: Thread pool size (default: 4)
- `REFRAME_MAX_CONCURRENT_TASKS`: Max concurrent tasks (default: 16)

### Environment Variables
#### Docker Deployment (Auto-configured)
These are set based on docker-compose.yml configuration:
- `RUST_LOG`: Logging level (set to: `error`)
- `REFRAME_THREAD_COUNT`: Automatically set to CPU count (optimal performance)
- `REFRAME_URL`: Target URL for benchmark runner (auto-set to private IP)

#### Native VM Deployment
- `RUST_LOG`: Logging level (set to: `error`)
- `REFRAME_THREAD_COUNT`: Automatically detected from CPU count via `nproc`
- Thread count is set in `/etc/environment` during VM initialization

### VM Specifications
- **Benchmark Runner**: Standard_B2ls_v2 (2 vCPUs, 4GB RAM) - Fixed
- **Target Application**: Configurable via `TARGET_VM_SIZE` input

## Usage

### Manual Trigger

#### Docker-based Deployment
```bash
# Basic benchmark run
gh workflow run main.yml -f target_vm_size=Standard_B4ms

# Custom benchmark configuration
gh workflow run main.yml \
  -f target_vm_size=Standard_B8ms \
  -f client_total_requests=200000 \
  -f client_concurrency_levels="16,64,128,256,512"
```

#### Native VM Deployment (Recommended for Performance Testing)
```bash
# Basic native benchmark run (thread count auto-detected from CPU)
gh workflow run benchmark-native.yml -f target_vm_size=Standard_B4ms

# Custom native benchmark configuration
gh workflow run benchmark-native.yml \
  -f target_vm_size=Standard_B16ms \
  -f client_total_requests=500000 \
  -f client_concurrency_levels="64,256,512,1024"

# Test different VM sizes
gh workflow run benchmark-native.yml -f target_vm_size=Standard_D4s_v5
gh workflow run benchmark-native.yml -f target_vm_size=Standard_D8s_v5
gh workflow run benchmark-native.yml -f target_vm_size=Standard_D16s_v5
```

### Automated Trigger
Workflows can be triggered on:
- Push to main branch (with path filters)
- Pull requests (benchmark comparison)
- Schedule (nightly performance regression tests)
- Manual dispatch (with input parameters)

## Workflow Details

### 1. Provision Infrastructure (`provision.yml`)
Using Azure CLI for ephemeral resources:
- **Single Resource Group**: All resources in one group for atomic cleanup
- **No State Storage**: Resources are ephemeral, no Terraform state needed
- **Resource Naming**: `${PROJECT_NAME}-${ENVIRONMENT}-${TIMESTAMP}` convention
- **Private Network Setup**: 
  - Virtual network with private subnet (10.0.1.0/24)
  - No public IPs assigned to VMs
  - Internal communication only via private IPs
  - GitHub runner manages deployment via Azure CLI
- **VM Provisioning**:
  - Benchmark runner: Standard_B2ls_v2 with Docker pre-installed
  - Target application: Configurable size with Docker pre-installed
  - Both VMs in same VNet for local communication
  - No persistent storage disks (ephemeral only)
- **Cloud-init**: Automated setup without SSH access

### 2. Deploy Application (`deploy.yml`)
Automated deployment via cloud-init:
- **ACR Authentication**: Uses org-level ACR credentials
- **Docker Deployment**: 
  - Pull Reframe image from ACR
  - Run with docker-compose configuration
  - Set performance tuning environment variables
- **Cloud-init Script**: Automated deployment without SSH
- **Health Checks**: Uses Docker healthcheck (http://localhost:3000/health)
- **Environment Variables**: 
  - `RUST_LOG=error`
  - `REFRAME_THREAD_COUNT` (from workflow input)
  - `REFRAME_MAX_CONCURRENT_TASKS` (from workflow input)

### 3. Run Benchmark (`benchmark.yml`)
- **Docker Execution**: Runs benchmark container with Dockerfile.benchmark
- **Target**: Uses private IP of Reframe VM via `REFRAME_URL` environment variable
- **Benchmark Configuration**:
  - Uses updated `simple_benchmark.py` with `REFRAME_URL` support
  - Runs in Docker container with Python 3.11 and aiohttp
  - Multiple concurrency levels from `BENCHMARK_CONFIGS`
- **Metrics Collection**:
  - **Throughput**: Requests per second (RPS)
  - **Response Latency**: Distribution (p50, p95, p99, p99.9)
  - **CPU Usage**: Average and peak utilization via Azure Monitor
  - **Memory Usage**: System metrics from Azure
- **Error Handling**: Comprehensive failure management with retries
- **Artifact Generation**: Structured JSON reports with all metrics

### 4. Extract & Store Reports
- **Report Generation**: Structured JSON with metadata
- **Git Storage**: Commit to `reports/` directory
- **Naming Convention**: `benchmark_${VM_SIZE}_${DATE}_${RUN_ID}.json`
- **Report Contents**:
  - Reframe version (from Docker image tag)
  - VM size configuration
  - Timestamp and duration
  - All performance metrics
- **Historical Tracking**: Version-controlled in repository

### 5. Cleanup Resources (`cleanup.yml`)
- **Single Command Cleanup**: Delete entire resource group
- **Atomic Operation**: All resources removed together
- **State Cleanup**: Maintain Terraform state consistency
- **Cost Optimization**: Guaranteed no orphaned resources

## Benchmark Script Details

### Using `simple_benchmark.py`
The benchmark script from `../Reframe/test/simple_benchmark.py` is updated to use environment variables:
- **Target URL**: Uses `REFRAME_URL` environment variable (set to http://<private-ip>:3000)
- **Script Parameters** (mapped from workflow inputs):
  - `num_requests`: From `BENCHMARK_REQUESTS` input
  - `concurrent`: From `BENCHMARK_CONCURRENT` input
  - Multiple test runs: From `BENCHMARK_CONFIGS` (comma-separated values)
- **Docker Configuration**:
  - Runs in separate container using `Dockerfile.benchmark`
  - Python 3.11 with aiohttp
  - Environment: `REFRAME_URL` pointing to target VM
  - `PYTHONUNBUFFERED=1` for real-time output

### Metrics Output
The script provides:
- Throughput (requests/second)
- Latency percentiles (p50, p95, p99, p99.9)
- Min/Max/Average latency
- Success rate
- Results in JSON format for artifact storage

### CPU Metrics Collection
Additional monitoring via Azure Monitor API:
- Collected in parallel during benchmark execution
- Average and peak CPU utilization
- Memory usage statistics
- Network throughput

## Development

### Local Testing
```bash
# Test infrastructure provisioning
./scripts/test-provision.sh

# Test benchmark execution
./scripts/test-benchmark.sh

# Manual cleanup
./scripts/cleanup-all.sh
```

### Adding New Benchmarks
1. Add benchmark script to `benchmark/scripts/`
2. Update configuration in `benchmark/configs/`
3. Modify workflow to include new benchmark

## Monitoring & Reporting

### Metrics Collected
- **Throughput**: Requests per second (RPS) over time
- **Response Latency Distribution**:
  - p50 (median)
  - p95 (95th percentile)
  - p99 (99th percentile)
  - p99.9 (99.9th percentile)
  - Min/Max values
- **CPU Usage**:
  - Average CPU utilization (%)
  - Peak CPU utilization (%)
  - CPU usage over time
- **Error Metrics**: Error rate and types
- **Connection Metrics**: Active connections, connection errors

### Report Formats
- JSON (machine-readable)
- HTML (human-readable dashboard)
- CSV (for data analysis)

## Troubleshooting

### Common Issues
1. **Provisioning Failures**: Check Azure quotas and permissions
2. **Deployment Failures**: Verify ACR credentials and image availability
3. **Benchmark Timeouts**: Adjust timeout values in workflow
4. **Cleanup Issues**: Run manual cleanup script

### Debug Mode
Enable debug logging in workflows:
```yaml
env:
  ACTIONS_RUNNER_DEBUG: true
  ACTIONS_STEP_DEBUG: true
```

## Contributing
1. Create feature branch
2. Test changes locally
3. Submit pull request
4. Ensure all checks pass

## License
[Your License]

## Contact
[Your Contact Information]