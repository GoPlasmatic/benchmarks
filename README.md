# Plasmatic Benchmarks

Centralized benchmarking infrastructure for all Plasmatic products, providing automated performance testing, resource provisioning, and reporting capabilities.

## Overview

This repository contains benchmarking scripts, CI/CD pipelines, and infrastructure provisioning tools for performance testing of Plasmatic products. The infrastructure is designed to be product-agnostic and scalable, supporting automated end-to-end benchmarking workflows.

## Architecture

The benchmarking system follows a cloud-native, containerized approach with automated provisioning and cleanup:

```
GitHub Actions → Azure VM Provisioning → Product Deployment → Benchmark Execution → Report Storage → Resource Cleanup
```

## Workflow Sequence

The automated benchmarking process follows these steps:

### 1. Workflow Trigger
- GitHub Actions workflow is triggered (manually or on schedule)
- Configuration specifies target product and benchmark parameters

### 2. Infrastructure Provisioning
- Azure VMs are provisioned based on configuration:
  - Product VM: Sized according to product requirements
  - Benchmark VM: Smaller instance for running benchmark scripts
- Network security groups and connectivity are configured

### 3. Product Deployment
- Product Docker images are pulled from Azure Container Registry
- Docker Compose orchestrates the product stack deployment
- Health checks ensure services are ready

### 4. Benchmark Execution
- Benchmark Docker container is deployed on the benchmark VM
- Scripts execute performance tests against the product instance
- Metrics are collected in real-time

### 5. Report Generation
- Performance metrics are aggregated
- Comprehensive reports are generated (JSON, CSV, HTML formats)
- Reports include:
  - Response time statistics
  - Throughput measurements
  - Error rates
  - Resource utilization

### 6. Report Storage
- Reports are uploaded to Azure Storage Account
- Organized by product, version, and timestamp
- Accessible via secure URLs

### 7. Report Listing
- Workflow provides summary of generated reports
- Direct links to stored reports in Azure Storage
- Performance trend analysis

### 8. Resource Cleanup
- All provisioned VMs are terminated
- Temporary resources are deleted
- Cost optimization through automatic cleanup

## Repository Structure

```
benchmarks/
├── .github/
│   └── workflows/           # GitHub Actions workflows
│       └── benchmark-products.yml
├── infrastructure/          # Infrastructure as Code
│   ├── azure/              # Azure provisioning scripts
│   │   ├── provision-vm.sh
│   │   ├── cleanup.sh
│   │   └── templates/
│   └── common/             # Shared infrastructure components
├── reports/                # Report storage and templates
│   └── templates/
└── products/               # Product-specific benchmarks
    └── reframe/            # Reframe benchmarking
        ├── docker/         # Docker configurations
        │   ├── docker-compose.yml
        │   └── vm-configs/ # VM sizing configurations
        │       ├── 2-core.json
        │       ├── 4-core.json
        │       ├── 8-core.json
        │       └── 16-core.json
        ├── scripts/        # Benchmark scripts
        │   ├── benchmark_transformation.py
        │   ├── batch_config.json
        │   └── requirements.txt
        └── README.md

```

## Configuration

### VM Sizing Strategy

The benchmarking infrastructure tests each product across multiple VM configurations to understand performance scaling characteristics:

#### Standard VM Configurations

**2-Core VM** (Standard_B2s)
```json
{
  "name": "2-core",
  "size": "Standard_B2s",
  "vcpus": 2,
  "memory_gb": 4,
  "use_case": "Baseline performance testing"
}
```

**4-Core VM** (Standard_D4s_v3)
```json
{
  "name": "4-core",
  "size": "Standard_D4s_v3",
  "vcpus": 4,
  "memory_gb": 16,
  "use_case": "Small-scale production workloads"
}
```

**8-Core VM** (Standard_D8s_v3)
```json
{
  "name": "8-core",
  "size": "Standard_D8s_v3",
  "vcpus": 8,
  "memory_gb": 32,
  "use_case": "Medium-scale production workloads"
}
```

**16-Core VM** (Standard_D16s_v3)
```json
{
  "name": "16-core",
  "size": "Standard_D16s_v3",
  "vcpus": 16,
  "memory_gb": 64,
  "use_case": "High-performance production workloads"
}
```

#### Benchmark VM Configuration
The benchmark script VM remains constant across all tests:
```json
{
  "size": "Standard_B2s",
  "vcpus": 2,
  "memory_gb": 4,
  "disk_size_gb": 32,
  "purpose": "Running benchmark scripts only"
}
```

## GitHub Actions Workflow

### Manual Trigger
```yaml
workflow_dispatch:
  inputs:
    product:
      description: 'Product to benchmark'
      required: true
      type: choice
      options:
        - reframe
    vm_configs:
      description: 'VM configurations to test'
      required: true
      type: choice
      options:
        - '2-core'
        - '4-core'
        - '8-core'
        - '16-core'
        - 'all'
      default: 'all'
    iterations:
      description: 'Number of benchmark iterations per VM config'
      default: '1000'
    concurrent_requests:
      description: 'Number of concurrent requests'
      default: '10'
```

### Scheduled Execution
```yaml
schedule:
  - cron: '0 2 * * 1'  # Weekly on Monday at 2 AM
```

## Products

Each product has its own benchmarking setup with product-specific Docker configurations and multiple VM sizing options for performance comparison.

### Reframe

**Product Setup:**
- **Docker Image**: `plasmatic.azurecr.io/reframe:latest`
- **Deployment**: Docker Compose based deployment
- **API Endpoint**: Port 3000
- **Health Check**: `/health` endpoint

**Benchmarking Capabilities:**
- SWIFT MT ↔ ISO 20022 transformation testing
- Message generation and validation
- Concurrent request handling (1-50 threads)
- Batch execution support

**VM Configurations:**
Multiple VM sizes are tested to understand scaling characteristics:
- **2-core**: Baseline performance metrics
- **4-core**: Small-scale production simulation
- **8-core**: Medium-scale production simulation
- **16-core**: High-performance production simulation

**Benchmark Scripts:**
- Location: `products/reframe/scripts/`
- Main script: `benchmark_transformation.py`
- Configuration: `batch_config.json`
- Execution: Local Python scripts on benchmark VM

**Performance Metrics Collected:**
- Response time (min, max, mean, median, p95, p99)
- Throughput (requests/second)
- Success/failure rates
- CPU utilization per core count
- Memory usage patterns
- Scaling efficiency (2-core → 16-core)

## Azure Resources

### Required Azure Services
- **Azure Container Registry**: Product Docker images storage
- **Azure Virtual Machines**: Dynamic compute resources
- **Azure Storage Account**: Benchmark reports storage
- **Azure Virtual Network**: Secure communication between VMs

### Service Principal Requirements
- VM create/delete permissions
- Container Registry pull access
- Storage Account write access
- Network security group management

## Environment Variables

```bash
# Azure Configuration
AZURE_SUBSCRIPTION_ID=xxx
AZURE_RESOURCE_GROUP=benchmarks-rg
AZURE_STORAGE_ACCOUNT=benchmarkstorage
AZURE_CONTAINER_REGISTRY=plasmatic.azurecr.io

# GitHub Secrets
AZURE_CREDENTIALS=<service-principal-json>
AZURE_STORAGE_KEY=xxx
ACR_USERNAME=xxx
ACR_PASSWORD=xxx
```

## Usage

### Manual Benchmark Run

#### Single VM Configuration
```bash
# Benchmark with specific VM size
gh workflow run benchmark-products.yml \
  -f product=reframe \
  -f vm_configs=4-core \
  -f iterations=1000 \
  -f concurrent_requests=10
```

#### All VM Configurations (Performance Comparison)
```bash
# Run benchmarks across all VM sizes for comparison
gh workflow run benchmark-products.yml \
  -f product=reframe \
  -f vm_configs=all \
  -f iterations=1000 \
  -f concurrent_requests=10
```

### Expected Outputs

When running with `vm_configs=all`, the workflow will:
1. Provision and test 2-core VM → collect metrics
2. Provision and test 4-core VM → collect metrics
3. Provision and test 8-core VM → collect metrics
4. Provision and test 16-core VM → collect metrics
5. Generate comparison report showing:
   - Performance scaling curve
   - Cost-performance analysis
   - Recommendations for production deployment

### Local Development
```bash
# Run benchmark scripts locally
cd products/reframe/scripts
python3 benchmark_transformation.py MT103 standard -i 100

# Test infrastructure scripts
./infrastructure/azure/provision-vm.sh --dry-run
```

## Reports

### Report Formats
- **JSON**: Detailed metrics and raw data
- **CSV**: Tabular data for analysis
- **HTML**: Visual dashboard with charts
- **Comparison Report**: Performance across VM sizes

### Report Storage Structure
```
benchmarks/
└── reframe/
    ├── 2024-01-15/
    │   ├── 2-core/
    │   │   ├── summary.json
    │   │   └── metrics.csv
    │   ├── 4-core/
    │   │   ├── summary.json
    │   │   └── metrics.csv
    │   ├── 8-core/
    │   │   ├── summary.json
    │   │   └── metrics.csv
    │   ├── 16-core/
    │   │   ├── summary.json
    │   │   └── metrics.csv
    │   └── comparison-report.html
    └── latest/           # Symlink to most recent
```

### Performance Comparison Analysis

The comparison report includes:
- **Scaling Efficiency**: How performance improves from 2-core to 16-core
- **Cost-Performance Ratio**: Performance gain vs. VM cost increase
- **Optimal Configuration**: Recommended VM size based on workload
- **Bottleneck Analysis**: Identifies if app is CPU, memory, or I/O bound

### Accessing Reports
Reports are accessible via:
1. Azure Storage Explorer
2. Direct URLs (with SAS tokens)
3. GitHub Actions artifacts
4. Azure Storage REST API

## Security Considerations

- All secrets stored in GitHub Secrets
- Azure Service Principal with minimal required permissions
- Network isolation between VMs
- Automatic resource cleanup to prevent cost overruns
- Secure communication using private endpoints

## Cost Management

- Automatic VM deprovisioning after benchmarks
- Use of spot instances where applicable
- Resource tagging for cost tracking
- Configurable VM sizes based on requirements

## Contributing

### Adding a New Product

1. Create product directory under `products/`
2. Add benchmark scripts
3. Create Docker Compose configuration
4. Update `configs/products.json`
5. Create GitHub Actions workflow
6. Document in product-specific README

### Benchmark Script Requirements

- Support for batch execution
- Configurable iterations and concurrency
- Standard output formats (JSON, CSV)
- Error handling and retry logic
- Progress reporting

## Monitoring

- GitHub Actions logs for workflow execution
- Azure Monitor for VM metrics
- Application Insights for performance tracking
- Cost alerts for budget management

## Troubleshooting

### Common Issues

1. **VM Provisioning Failures**
   - Check Azure quotas
   - Verify service principal permissions
   - Review region availability

2. **Docker Pull Errors**
   - Verify ACR credentials
   - Check network connectivity
   - Confirm image existence

3. **Benchmark Timeouts**
   - Increase VM size
   - Adjust timeout configurations
   - Check product health

## Future Enhancements

- [ ] Kubernetes-based benchmarking
- [ ] Multi-region testing
- [ ] Comparative benchmarking between versions
- [ ] Real-time monitoring dashboard
- [ ] Cost optimization recommendations
- [ ] Performance regression detection
- [ ] Auto-scaling based on load
- [ ] Integration with APM tools

## License

Proprietary - Plasmatic

## Support

For issues or questions:
- Create an issue in this repository
- Contact the Platform team
- Check the [Wiki](wiki-link) for detailed documentation