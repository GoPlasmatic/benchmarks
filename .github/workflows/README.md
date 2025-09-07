# GitHub Actions Workflows

This directory contains automated workflows for performance benchmarking and monitoring.

## Workflows

### 1. `investigate-performance.yml`
**Purpose**: Deep performance investigation with Azure infrastructure provisioning

**Trigger Methods**:
- Manual dispatch from Actions tab
- Called by other workflows when issues detected

**Parameters**:
- `vm_size`: VM configuration to test (2-core, 4-core, 8-core, 16-core)
- `investigation_type`: Type of investigation (diagnostic, degradation, comparison, full)
- `reframe_url`: Optional - existing server URL (skips provisioning)
- `num_waves`: Number of waves for degradation testing
- `num_requests`: Total requests per test

**Outputs**:
- Performance report as GitHub Issue comment
- Artifacts with detailed logs and metrics
- Azure Storage persistence of results

### 2. `continuous-performance.yml`
**Purpose**: Automated performance monitoring and regression detection

**Trigger Methods**:
- Every 6 hours (cron schedule)
- On push to main branch
- On pull requests

**Features**:
- Quick performance health checks
- PR regression testing
- Automatic escalation to full investigation
- Performance dashboard updates
- Slack/Issue alerts

### 3. `benchmark-reframe.yml`
**Purpose**: Standard benchmarking workflow

**Features**:
- Azure VM provisioning
- Multi-configuration testing
- Result aggregation and reporting

### 4. `setup-requirements.yml`
**Purpose**: Reusable workflow for environment setup

**Features**:
- Python environment configuration
- System optimizations
- Dependency installation

## Required Secrets

Configure these in Repository Settings → Secrets:

```yaml
AZURE_CREDENTIALS        # Azure service principal JSON
AZURE_STORAGE_ACCOUNT   # Storage account name
AZURE_STORAGE_KEY       # Storage account key
SLACK_WEBHOOK_URL       # Optional: Slack notifications
```

### Creating Azure Credentials

```bash
# Create service principal
az ad sp create-for-rbac --name "github-actions" \
  --role contributor \
  --scopes /subscriptions/{subscription-id} \
  --sdk-auth

# Copy the JSON output to AZURE_CREDENTIALS secret
```

## Usage Examples

### Manual Investigation

1. Go to Actions tab
2. Select "Investigate Performance"
3. Click "Run workflow"
4. Configure parameters:
   - VM Size: `8-core`
   - Investigation Type: `full`
   - Num Requests: `50000`
5. Click "Run workflow"

### Check Performance Status

```bash
# View latest performance metrics
cat PERFORMANCE.md

# Check metrics history
tail -n 10 .metrics/history.jsonl
```

### Local Testing

```bash
# Run diagnostic locally
python3 products/reframe/benchmark/diagnose_performance.py \
  --base-url http://localhost:3000

# Run degradation analysis
python3 products/reframe/benchmark/investigate_degradation.py \
  --base-url http://localhost:3000 \
  --waves 10

# Run fixed benchmark
python3 products/reframe/benchmark/fixed_benchmark.py \
  --base-url http://localhost:3000 \
  --vm-size 8-core \
  --num-requests 50000
```

## Performance Thresholds

Default alert thresholds (configurable in workflows):

| Metric | Threshold | Action |
|--------|-----------|--------|
| Degradation | > 20% | Trigger full investigation |
| P99 Latency | > 500ms | Create alert issue |
| Success Rate | < 95% | Send Slack notification |
| Throughput Drop | > 10% in PR | Block PR merge |

## Troubleshooting

### Workflow Fails with "Resource not found"
- Ensure Azure credentials are configured correctly
- Check resource group exists
- Verify subscription has required quotas

### Performance Tests Timeout
- Check server is accessible from runner
- Verify network security groups allow traffic
- Increase timeout values in workflow

### Degradation Not Detected
- Review threshold settings
- Check if using fixed_benchmark.py (prevents degradation)
- Verify server configuration

## Architecture

```
┌─────────────────┐
│ GitHub Actions  │
│    Runner       │
└────────┬────────┘
         │
    ┌────▼────┐
    │ Deploy  │
    │  VMs    │
    └────┬────┘
         │
    ┌────▼────────────┐
    │  Benchmark VM   │
    │  - Run tests    │
    │  - Collect data │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Reframe VM     │
    │  - API Server   │
    │  - 8 workers    │
    └─────────────────┘
```

## Best Practices

1. **Resource Cleanup**: VMs are automatically deleted after runs
2. **Cost Management**: Use smallest VM size that reproduces issues
3. **Monitoring**: Check dashboard daily for trends
4. **Alerts**: Configure Slack webhook for immediate notifications
5. **PR Testing**: Always run performance checks on PRs

## Contributing

When modifying workflows:
1. Test locally first using act or similar tools
2. Use reusable workflows for common tasks
3. Document new parameters in this README
4. Update thresholds based on baseline performance