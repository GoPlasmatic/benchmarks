#!/usr/bin/env python3
"""
Modified benchmark script for Azure VM execution
Accepts environment variables for configuration
"""

import asyncio
import aiohttp
import time
import sys
import json
import os

async def make_request(session, url, data):
    """Make a single request and return latency"""
    start = time.perf_counter()
    try:
        async with session.post(url, json=data) as resp:
            await resp.text()
            return time.perf_counter() - start, resp.status == 200
    except:
        return time.perf_counter() - start, False

async def get_sample_message(session):
    """Get a sample MT103 message from the generator API"""
    base_url = os.environ.get('REFRAME_URL', 'http://localhost:3000')
    try:
        async with session.post(f"{base_url}/generate/sample",
                                json={"message_type": "MT103", "config": {"scenario": "standard"}}) as resp:
            if resp.status == 200:
                result = await resp.json()
                return {
                    "message": result.get("result", result.get("message", "")),
                    "options": {"validation": False}
                }
    except:
        pass
    
    # Fallback message
    return {
        "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
        "options": {"validation": False}
    }

async def run_test(num_requests=100, concurrent=8):
    """Run a simple performance test"""
    base_url = os.environ.get('REFRAME_URL', 'http://localhost:3000')
    url = f"{base_url}/transform/mt-to-mx"
    
    async with aiohttp.ClientSession() as session:
        # Get sample message
        print(f"Getting sample message from {base_url}...")
        data = await get_sample_message(session)
        
        # Warmup
        warmup_count = int(os.environ.get('BENCHMARK_WARMUP', '10'))
        print(f"Warming up with {warmup_count} requests...")
        for _ in range(warmup_count):
            await make_request(session, url, data)
        
        print(f"Running {num_requests} requests with {concurrent} concurrent tasks...")
        start_time = time.perf_counter()
        
        latencies = []
        successes = 0
        
        # Process in batches
        for i in range(0, num_requests, concurrent):
            batch_size = min(concurrent, num_requests - i)
            batch = [make_request(session, url, data) for _ in range(batch_size)]
            results = await asyncio.gather(*batch)
            
            for latency, success in results:
                latencies.append(latency)
                if success:
                    successes += 1
        
        total_time = time.perf_counter() - start_time
        
        # Calculate statistics
        latencies.sort()
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        min_latency = latencies[0] if latencies else 0
        max_latency = latencies[-1] if latencies else 0
        
        # Calculate percentiles
        def get_percentile(data, percentile):
            if not data:
                return 0
            index = int(len(data) * percentile / 100)
            if index >= len(data):
                index = len(data) - 1
            return data[index]
        
        p50_latency = get_percentile(latencies, 50)
        p95_latency = get_percentile(latencies, 95)
        p99_latency = get_percentile(latencies, 99)
        p999_latency = get_percentile(latencies, 99.9)
        
        throughput = num_requests / total_time if total_time > 0 else 0
        success_rate = (successes/num_requests)*100 if num_requests > 0 else 0
        
        return {
            'configuration': f'{concurrent} concurrent',
            'total_requests': num_requests,
            'successful_requests': successes,
            'success_rate': success_rate,
            'total_time': total_time,
            'throughput': throughput,
            'latency': {
                'min': min_latency * 1000,
                'avg': avg_latency * 1000,
                'p50': p50_latency * 1000,
                'p95': p95_latency * 1000,
                'p99': p99_latency * 1000,
                'p99.9': p999_latency * 1000,
                'max': max_latency * 1000
            }
        }

async def main():
    """Run benchmark tests based on environment configuration"""
    print("Reframe Performance Benchmark")
    print("="*50)
    
    # Get configuration from environment
    base_url = os.environ.get('REFRAME_URL', 'http://localhost:3000')
    num_requests = int(os.environ.get('BENCHMARK_REQUESTS', '100000'))
    benchmark_configs = os.environ.get('BENCHMARK_CONFIGS', '8,32,128,256')
    
    print(f"Target URL: {base_url}")
    print(f"Total requests per test: {num_requests}")
    print(f"Concurrency levels: {benchmark_configs}")
    print()
    
    # Check if server is running
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/health") as resp:
                if resp.status != 200:
                    print(f"Server at {base_url} is not running!")
                    sys.exit(1)
                health = await resp.json()
                print(f"Server is healthy: {health}")
                print()
    except Exception as e:
        print(f"Cannot connect to server at {base_url}!")
        print(f"Error: {e}")
        sys.exit(1)
    
    # Parse concurrency configs
    concurrency_levels = [int(x.strip()) for x in benchmark_configs.split(',')]
    
    # Run tests
    results = []
    for concurrent in concurrency_levels:
        print(f"\n--- Testing: {concurrent} concurrent connections ---")
        stats = await run_test(num_requests, concurrent)
        results.append(stats)
        
        # Print immediate results
        print(f"  Throughput: {stats['throughput']:.1f} req/s")
        print(f"  Success rate: {stats['success_rate']:.1f}%")
        print(f"  Latency p50: {stats['latency']['p50']:.1f} ms")
        print(f"  Latency p99: {stats['latency']['p99']:.1f} ms")
    
    # Summary
    print("\n" + "="*50)
    print("BENCHMARK SUMMARY")
    print("="*50)
    print(f"{'Config':<15} {'Throughput':<12} {'Success':<10} {'p50':<8} {'p95':<8} {'p99':<8} {'p99.9':<8}")
    print(f"{'              ':<15} {'(req/s)':<12} {'(%)':<10} {'(ms)':<8} {'(ms)':<8} {'(ms)':<8} {'(ms)':<8}")
    print("-"*75)
    
    for stats in results:
        print(f"{stats['configuration']:<15} "
              f"{stats['throughput']:<12.1f} "
              f"{stats['success_rate']:<10.1f} "
              f"{stats['latency']['p50']:<8.1f} "
              f"{stats['latency']['p95']:<8.1f} "
              f"{stats['latency']['p99']:<8.1f} "
              f"{stats['latency']['p99.9']:<8.1f}")
    
    # Find best configurations
    best_throughput = max(results, key=lambda x: x['throughput'])
    best_latency = min(results, key=lambda x: x['latency']['p99'])
    
    print(f"\nBest throughput: {best_throughput['configuration']} with {best_throughput['throughput']:.1f} req/s")
    print(f"Best p99 latency: {best_latency['configuration']} with {best_latency['latency']['p99']:.1f} ms")
    
    # Output JSON results
    output = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'configuration': {
            'target_url': base_url,
            'total_requests': num_requests,
            'concurrency_levels': concurrency_levels
        },
        'results': results,
        'summary': {
            'best_throughput': {
                'configuration': best_throughput['configuration'],
                'value': best_throughput['throughput']
            },
            'best_p99_latency': {
                'configuration': best_latency['configuration'],
                'value': best_latency['latency']['p99']
            }
        }
    }
    
    # Write to stdout as JSON for collection
    print("\n\nJSON_OUTPUT_START")
    print(json.dumps(output, indent=2))
    print("JSON_OUTPUT_END")

if __name__ == "__main__":
    asyncio.run(main())