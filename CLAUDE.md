# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a centralized benchmarking infrastructure repository for all Plasmatic products. It provides automated performance testing, cloud resource provisioning, and comprehensive reporting capabilities.

## Architecture

The benchmarking system follows an automated workflow:
1. GitHub Actions triggers benchmarking
2. Azure VMs are provisioned (product VM + benchmark VM)
3. Products are deployed from Azure Container Registry
4. Benchmarks are executed in Docker containers
5. Reports are stored in Azure Storage
6. Resources are automatically cleaned up

## Repository Structure

- `products/` - Product-specific benchmark scripts
  - `reframe/` - Reframe API benchmarking (MT<->MX transformations)
- `infrastructure/` - Infrastructure as Code (planned)
  - `azure/` - VM provisioning scripts
  - `docker/` - Container configurations
- `.github/workflows/` - CI/CD pipelines (planned)
- `configs/` - Configuration files (planned)

## Current Implementation

### Reframe Benchmarking
- Location: `products/reframe/`
- Main script: `benchmark_transformation.py`
- Features:
  - Transformation API performance testing
  - Concurrent request handling
  - Batch execution support
  - Multiple output formats (JSON, CSV)

## Development Guidelines

1. **Product Integration**: Each product should have its own directory under `products/`
2. **Standard Outputs**: All benchmarks must support JSON and CSV output
3. **Batch Support**: Scripts should support batch configuration files
4. **Error Handling**: Comprehensive error handling and retry logic required
5. **Cloud-Native**: Design for containerized execution in Azure

## Azure Resources Used

- Azure Container Registry (ACR) for Docker images
- Azure VMs for dynamic compute
- Azure Storage for report persistence
- Azure Virtual Network for secure communication

## Python Development

- Use Python 3.8+ for benchmark scripts
- Required packages: requests, tabulate
- Follow PEP 8 style guidelines
- Include comprehensive error handling

## Future Components

The infrastructure is being expanded to include:
- GitHub Actions workflows for automation
- Azure provisioning scripts using Azure CLI
- Docker containers for benchmark execution
- Multi-product support (DataFlow, DataLogic, MXMessage, etc.)

## Testing

- Test benchmark scripts locally first
- Use dry-run modes for infrastructure scripts
- Validate JSON/CSV outputs before integration

## Notes

- All secrets should be stored in GitHub Secrets
- Resource cleanup is critical for cost management
- Reports should be timestamped and versioned
- Support both manual and scheduled execution