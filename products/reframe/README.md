# Reframe API Transformation Benchmarks

This directory contains benchmarking scripts for the Reframe Transformation API, focusing on MT<->MX message transformation performance.

## Overview

The benchmark script measures the performance of the Reframe Transformation API by:
1. Generating sample messages using the Generate API
2. Transforming messages using the Transformation API
3. Collecting detailed performance metrics

## Installation

Install required Python packages:

```bash
pip install requests tabulate
```

## Usage

### Basic Usage

Benchmark a single message type and scenario:

```bash
python benchmark_transformation.py MT103 standard
```

### Advanced Options

```bash
# Run with 500 iterations and 20 warmup iterations
python benchmark_transformation.py MT103 standard -i 500 -w 20

# Run with 10 concurrent requests
python benchmark_transformation.py MT103 standard -c 10

# Use custom API endpoint
python benchmark_transformation.py MT103 standard -u http://localhost:3000

# Export detailed metrics
python benchmark_transformation.py MT103 standard --export-metrics -o results/

# Set custom timeout (in seconds)
python benchmark_transformation.py MT103 standard -t 60
```

### Batch Benchmarking

Run multiple benchmarks using a configuration file:

```bash
# Run benchmarks from config file
python benchmark_transformation.py --batch batch_config.json

# Export results to CSV
python benchmark_transformation.py --batch batch_config.json --csv -o results/
```

## Configuration File Format

The `batch_config.json` file allows you to define multiple benchmark configurations:

```json
{
  "benchmarks": [
    {
      "message_type": "MT103",
      "scenario": "standard",
      "iterations": 100,
      "warmup_iterations": 10,
      "concurrent_requests": 1
    },
    {
      "message_type": "pacs.008",
      "scenario": "standard",
      "iterations": 100,
      "warmup_iterations": 10,
      "concurrent_requests": 5
    }
  ]
}
```

## Output

### Console Output

The script displays:
- Configuration details
- Progress indicator
- Success rate
- Response time statistics (min, max, mean, median, p95, p99)
- Throughput (requests/second)
- Error summary (if any)

### File Outputs

1. **Summary JSON**: Contains aggregated statistics
   - `summary_<message_type>_<scenario>_<timestamp>.json`

2. **Detailed Metrics JSON**: Contains individual request metrics
   - `metrics_<message_type>_<scenario>_<timestamp>.json`

3. **CSV Export**: Batch results in CSV format
   - `benchmark_results_<timestamp>.csv`

## Metrics Collected

- **Response Time**: Time taken for each transformation request (in milliseconds)
- **Success Rate**: Percentage of successful transformations
- **Throughput**: Requests processed per second
- **Percentiles**: 95th and 99th percentile response times
- **Message Size**: Size of the input message in bytes
- **Errors**: Categorized error counts

## Performance Tuning

### Warmup Iterations
Warmup iterations help stabilize the API and connection pooling before actual measurements:
```bash
python benchmark_transformation.py MT103 standard -w 20
```

### Concurrent Requests
Test the API under concurrent load:
```bash
# Test with 10 concurrent requests
python benchmark_transformation.py MT103 standard -c 10 -i 1000
```

### Timeout Configuration
Adjust timeout for slow networks or complex transformations:
```bash
python benchmark_transformation.py MT103 standard -t 60
```

## Examples

### Example 1: Quick Performance Test
```bash
python benchmark_transformation.py MT103 standard -i 50 -w 5
```

### Example 2: Load Testing
```bash
python benchmark_transformation.py MT103 standard -i 1000 -c 20 -w 50
```

### Example 3: Comprehensive Benchmark Suite
```bash
python benchmark_transformation.py --batch batch_config.json --export-metrics --csv -o results/
```

## Interpreting Results

- **Response Time**: Lower is better. Check p95 and p99 for consistency
- **Throughput**: Higher is better. Should scale with concurrent requests
- **Success Rate**: Should be close to 100% under normal conditions
- **Standard Deviation**: Lower values indicate more consistent performance

## Troubleshooting

### Connection Errors
- Verify the API URL is correct
- Check network connectivity
- Ensure the API is running

### Timeout Errors
- Increase timeout with `-t` flag
- Reduce concurrent requests
- Check API server load

### Generation Failures
- Verify message type and scenario are valid
- Check API documentation for supported combinations