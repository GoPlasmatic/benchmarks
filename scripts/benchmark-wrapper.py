#!/usr/bin/env python3
"""
Wrapper script to run simple_benchmark.py and output JSON format
"""

import subprocess
import json
import sys
import os
import re
from datetime import datetime

def parse_benchmark_output(output):
    """Parse the text output from simple_benchmark.py"""
    results = []
    lines = output.split('\n')
    
    # Look for test results
    current_test = None
    for line in lines:
        # Match lines like "Testing with 8 concurrent requests"
        if "Testing with" in line and "concurrent" in line:
            match = re.search(r'(\d+)\s+concurrent', line)
            if match:
                current_test = {
                    'configuration': f"{match.group(1)} concurrent",
                    'concurrent': int(match.group(1))
                }
        
        # Match throughput line
        elif "Throughput:" in line and current_test:
            match = re.search(r'([\d.]+)\s*req/s', line)
            if match:
                current_test['throughput'] = float(match.group(1))
        
        # Match latency lines
        elif "Latency" in line and current_test:
            # Parse various latency metrics
            if "min:" in line:
                match = re.search(r'min:\s*([\d.]+)', line)
                if match:
                    if 'latency' not in current_test:
                        current_test['latency'] = {}
                    current_test['latency']['min'] = float(match.group(1))
            
            if "avg:" in line:
                match = re.search(r'avg:\s*([\d.]+)', line)
                if match:
                    if 'latency' not in current_test:
                        current_test['latency'] = {}
                    current_test['latency']['avg'] = float(match.group(1))
            
            if "p95:" in line:
                match = re.search(r'p95:\s*([\d.]+)', line)
                if match:
                    if 'latency' not in current_test:
                        current_test['latency'] = {}
                    current_test['latency']['p95'] = float(match.group(1))
            
            if "p99:" in line:
                match = re.search(r'p99:\s*([\d.]+)', line)
                if match:
                    if 'latency' not in current_test:
                        current_test['latency'] = {}
                    current_test['latency']['p99'] = float(match.group(1))
            
            if "max:" in line:
                match = re.search(r'max:\s*([\d.]+)', line)
                if match:
                    if 'latency' not in current_test:
                        current_test['latency'] = {}
                    current_test['latency']['max'] = float(match.group(1))
        
        # When we see a summary line or new test, save the current test
        elif ("---" in line or "SUMMARY" in line) and current_test and 'throughput' in current_test:
            results.append(current_test)
            current_test = None
    
    # Add the last test if it exists
    if current_test and 'throughput' in current_test:
        results.append(current_test)
    
    return results

def main():
    # Get environment variables
    reframe_url = os.environ.get('REFRAME_URL', 'http://localhost:3000')
    requests = os.environ.get('BENCHMARK_REQUESTS', '100000')
    configs = os.environ.get('BENCHMARK_CONFIGS', '8,32,128')
    
    # Run simple_benchmark.py
    env = os.environ.copy()
    env['REFRAME_URL'] = reframe_url
    env['BENCHMARK_REQUESTS'] = requests
    env['BENCHMARK_CONFIGS'] = configs
    
    try:
        result = subprocess.run(
            ['python3', '/app/test/simple_benchmark.py'],
            capture_output=True,
            text=True,
            env=env,
            timeout=600
        )
        
        output = result.stdout + result.stderr
        print(output)  # Print the raw output first
        
        # Parse the output
        parsed_results = parse_benchmark_output(output)
        
        # Create JSON output
        json_output = {
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'configuration': {
                'target_url': reframe_url,
                'total_requests': int(requests),
                'concurrency_levels': [int(x.strip()) for x in configs.split(',')]
            },
            'results': parsed_results,
            'summary': {}
        }
        
        # Find best results
        if parsed_results:
            best_throughput = max(parsed_results, key=lambda x: x.get('throughput', 0))
            best_latency = min(parsed_results, key=lambda x: x.get('latency', {}).get('p99', float('inf')))
            
            json_output['summary'] = {
                'best_throughput': {
                    'configuration': best_throughput['configuration'],
                    'value': best_throughput.get('throughput', 0)
                },
                'best_p99_latency': {
                    'configuration': best_latency['configuration'],
                    'value': best_latency.get('latency', {}).get('p99', 0)
                }
            }
        
        # Output JSON with markers
        print("\nJSON_OUTPUT_START")
        print(json.dumps(json_output, indent=2))
        print("JSON_OUTPUT_END")
        
    except subprocess.TimeoutExpired:
        print("Benchmark timed out after 600 seconds")
        sys.exit(1)
    except Exception as e:
        print(f"Error running benchmark: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()