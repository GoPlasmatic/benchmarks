#!/usr/bin/env python3
"""
Enhanced benchmark script for Reframe with CPU monitoring and detailed metrics.
Adapted from simple_benchmark.py with additional metrics collection.
"""

import asyncio
import aiohttp
import time
import sys
import json
import argparse
import psutil
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class CPUMonitor:
    """Monitor CPU usage during benchmark execution"""
    
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        self.monitor_thread = None
    
    def start(self):
        """Start monitoring CPU and memory usage"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop monitoring and return statistics"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        
        if not self.cpu_samples:
            return {
                'avg_cpu': 0,
                'peak_cpu': 0,
                'avg_memory': 0,
                'peak_memory': 0
            }
        
        return {
            'avg_cpu': sum(self.cpu_samples) / len(self.cpu_samples),
            'peak_cpu': max(self.cpu_samples),
            'avg_memory': sum(self.memory_samples) / len(self.memory_samples),
            'peak_memory': max(self.memory_samples)
        }
    
    def _monitor_loop(self):
        """Background thread to collect CPU/memory samples"""
        while self.monitoring:
            try:
                cpu_percent = psutil.cpu_percent(interval=None)
                memory_percent = psutil.virtual_memory().percent
                
                self.cpu_samples.append(cpu_percent)
                self.memory_samples.append(memory_percent)
                
                time.sleep(self.interval)
            except Exception as e:
                print(f"Monitor error: {e}")
                break

async def make_request(session: aiohttp.ClientSession, url: str, data: dict) -> Tuple[float, bool]:
    """Make a single request and return latency in ms"""
    start = time.perf_counter()
    try:
        async with session.post(url, json=data) as resp:
            await resp.text()
            latency_ms = (time.perf_counter() - start) * 1000
            return latency_ms, resp.status == 200
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return latency_ms, False

async def get_sample_message(session: aiohttp.ClientSession, base_url: str) -> dict:
    """Get a sample MT103 message from the generator API"""
    try:
        async with session.post(f"{base_url}/generate/sample",
                                json={"message_type": "MT103", "config": {"scenario": "standard"}}) as resp:
            if resp.status == 200:
                result = await resp.json()
                return {
                    "message": result.get("result", result.get("message", "")),
                    "options": {"validation": False}
                }
    except Exception as e:
        print(f"Failed to get sample message: {e}")
    
    # Fallback message
    return {
        "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
        "options": {"validation": False}
    }

async def check_server_config(session: aiohttp.ClientSession, base_url: str) -> dict:
    """Check server configuration"""
    try:
        async with session.get(f"{base_url}/health") as resp:
            if resp.status == 200:
                health = await resp.json()
                return {
                    'status': 'running',
                    'engines': health.get('engines', 'unknown')
                }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}
    
    return {'status': 'unknown'}

async def run_benchmark_test(
    base_url: str,
    num_requests: int,
    concurrent: int,
    thread_count: int,
    max_concurrent_tasks: int
) -> dict:
    """Run a single benchmark test with specific configuration"""
    
    url = f"{base_url}/transform/mt-to-mx"
    
    # Configure server with environment variables (would be done at container level)
    print(f"\nConfiguration:")
    print(f"  Thread Count: {thread_count}")
    print(f"  Max Concurrent Tasks: {max_concurrent_tasks}")
    print(f"  Concurrent Requests: {concurrent}")
    print(f"  Total Requests: {num_requests}")
    
    # Start CPU monitoring
    monitor = CPUMonitor(interval=0.5)
    monitor.start()
    
    async with aiohttp.ClientSession() as session:
        # Get sample message
        data = await get_sample_message(session, base_url)
        
        # Warmup
        print(f"Warming up with 10 requests...")
        for _ in range(10):
            await make_request(session, url, data)
        
        print(f"Running {num_requests} requests with {concurrent} concurrent...")
        start_time = time.perf_counter()
        last_report = start_time
        
        latencies = []
        successes = 0
        failures = 0
        
        # Process requests in batches
        for i in range(0, num_requests, concurrent):
            batch_size = min(concurrent, num_requests - i)
            batch = [make_request(session, url, data) for _ in range(batch_size)]
            
            # Add timeout for batch
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*batch, return_exceptions=True),
                    timeout=30.0  # 30 second timeout per batch
                )
            except asyncio.TimeoutError:
                print(f"\n  WARNING: Batch timeout at {i}/{num_requests}")
                results = [(0, False)] * batch_size
            
            for result in results:
                if isinstance(result, Exception):
                    latencies.append(0)
                    failures += 1
                else:
                    latency, success = result
                    latencies.append(latency)
                    if success:
                        successes += 1
                    else:
                        failures += 1
            
            # Progress indicator - report every 500 requests or 5 seconds
            current_time = time.perf_counter()
            if (i + batch_size) % 500 == 0 or (current_time - last_report) >= 5:
                progress = (i + batch_size) / num_requests * 100
                elapsed = current_time - start_time
                rate = (i + batch_size) / elapsed if elapsed > 0 else 0
                eta = (num_requests - i - batch_size) / rate if rate > 0 else 0
                print(f"  Progress: {i + batch_size}/{num_requests} ({progress:.1f}%) | "
                      f"Rate: {rate:.0f} req/s | ETA: {eta:.0f}s | "
                      f"Success: {successes}/{i + batch_size}")
                last_report = current_time
        
        total_time = time.perf_counter() - start_time
        print(f"\n  Completed: {num_requests} requests in {total_time:.2f}s")
    
    # Stop CPU monitoring
    cpu_stats = monitor.stop()
    
    # Calculate statistics
    latencies.sort()
    
    def get_percentile(data: List[float], percentile: float) -> float:
        if not data:
            return 0
        index = int(len(data) * percentile / 100)
        if index >= len(data):
            index = len(data) - 1
        return data[index]
    
    throughput = num_requests / total_time if total_time > 0 else 0
    
    return {
        'config': {
            'thread_count': thread_count,
            'max_concurrent_tasks': max_concurrent_tasks,
            'concurrent_requests': concurrent,
            'total_requests': num_requests
        },
        'performance': {
            'total_time': total_time,
            'throughput': throughput,
            'success_rate': (successes / num_requests * 100) if num_requests > 0 else 0,
            'total_requests': num_requests,
            'successful': successes,
            'failed': failures
        },
        'latency': {
            'min': min(latencies) if latencies else 0,
            'avg': sum(latencies) / len(latencies) if latencies else 0,
            'p50': get_percentile(latencies, 50),
            'p95': get_percentile(latencies, 95),
            'p99': get_percentile(latencies, 99),
            'max': max(latencies) if latencies else 0
        },
        'resources': {
            'avg_cpu': cpu_stats['avg_cpu'],
            'peak_cpu': cpu_stats['peak_cpu'],
            'avg_memory': cpu_stats['avg_memory'],
            'peak_memory': cpu_stats['peak_memory']
        },
        'timestamp': datetime.now().isoformat()
    }

async def update_server_config(base_url: str, thread_count: int, max_concurrent_tasks: int):
    """Update server configuration via SSH (placeholder - would be done via container restart)"""
    # In real implementation, this would SSH to the VM and restart the container
    # with new environment variables
    print(f"Note: Server configuration update would be done via container restart")
    print(f"  REFRAME_THREAD_COUNT={thread_count}")
    print(f"  REFRAME_MAX_CONCURRENT_TASKS={max_concurrent_tasks}")

async def main():
    parser = argparse.ArgumentParser(description='Enhanced Reframe Benchmark')
    parser.add_argument('--base-url', default='http://localhost:3000', help='Reframe API base URL')
    parser.add_argument('--vm-size', required=True, help='VM size configuration (2-core, 4-core, etc)')
    parser.add_argument('--num-requests', type=int, default=100000, help='Number of requests per test')
    parser.add_argument('--concurrent-levels', default='64,256,512', help='Concurrent request levels')
    parser.add_argument('--output-dir', default='results', help='Output directory for results')
    
    args = parser.parse_args()
    
    # Parse concurrent levels
    concurrent_levels = [int(x) for x in args.concurrent_levels.split(',')]
    
    # Load VM configuration
    config_file = Path(f'infrastructure/azure/vm-configs/{args.vm_size}.json')
    if not config_file.exists():
        print(f"Error: Configuration file not found: {config_file}")
        sys.exit(1)
    
    with open(config_file) as f:
        vm_config = json.load(f)
    
    thread_counts = vm_config['thread_counts']
    max_concurrent_tasks_list = vm_config['max_concurrent_tasks']
    
    print(f"Enhanced Reframe Performance Benchmark")
    print(f"======================================")
    print(f"VM Size: {args.vm_size}")
    print(f"VM SKU: {vm_config['azure_sku']}")
    print(f"vCPUs: {vm_config['vcpus']}")
    print(f"Memory: {vm_config['memory_gb']} GB")
    print(f"Thread Counts: {thread_counts}")
    print(f"Max Concurrent Tasks: {max_concurrent_tasks_list}")
    print(f"Concurrent Levels: {concurrent_levels}")
    print()
    
    # Check server status
    async with aiohttp.ClientSession() as session:
        server_status = await check_server_config(session, args.base_url)
        if server_status['status'] != 'running':
            print(f"Error: Server is not running at {args.base_url}")
            print(f"Status: {server_status}")
            sys.exit(1)
        print(f"Server is running: {server_status['engines']}\n")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run benchmark tests
    all_results = []
    test_number = 0
    total_tests = len(thread_counts) * len(max_concurrent_tasks_list) * len(concurrent_levels)
    
    for thread_count in thread_counts:
        for max_concurrent_tasks in max_concurrent_tasks_list:
            # Update server configuration (would restart container with new env vars)
            await update_server_config(args.base_url, thread_count, max_concurrent_tasks)
            
            # Wait for server to stabilize
            await asyncio.sleep(5)
            
            for concurrent in concurrent_levels:
                test_number += 1
                print(f"\n--- Test {test_number}/{total_tests} ---")
                
                result = await run_benchmark_test(
                    args.base_url,
                    args.num_requests,
                    concurrent,
                    thread_count,
                    max_concurrent_tasks
                )
                
                all_results.append(result)
                
                # Print summary
                print(f"\nResults:")
                print(f"  Throughput: {result['performance']['throughput']:.1f} req/s")
                print(f"  Avg CPU: {result['resources']['avg_cpu']:.1f}%")
                print(f"  Peak CPU: {result['resources']['peak_cpu']:.1f}%")
                print(f"  Latency (ms):")
                print(f"    Min: {result['latency']['min']:.1f}")
                print(f"    Avg: {result['latency']['avg']:.1f}")
                print(f"    P95: {result['latency']['p95']:.1f}")
                print(f"    P99: {result['latency']['p99']:.1f}")
                print(f"    Max: {result['latency']['max']:.1f}")
    
    # Save results
    output_file = output_dir / f"benchmark_results_{args.vm_size}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'vm_config': vm_config,
            'test_parameters': {
                'num_requests': args.num_requests,
                'concurrent_levels': concurrent_levels
            },
            'results': all_results,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2)
    
    print(f"\n\nResults saved to: {output_file}")
    
    # Print summary table
    print("\n=== SUMMARY ===")
    print(f"{'Threads':<8} {'Max Tasks':<10} {'Concurrent':<12} {'Throughput':<12} {'Avg CPU':<10} {'P99 Latency':<12}")
    print(f"{'       ':<8} {'         ':<10} {'Requests':<12} {'(req/s)':<12} {'(%)':<10} {'(ms)':<12}")
    print("-" * 74)
    
    for result in all_results:
        config = result['config']
        perf = result['performance']
        latency = result['latency']
        resources = result['resources']
        
        print(f"{config['thread_count']:<8} {config['max_concurrent_tasks']:<10} "
              f"{config['concurrent_requests']:<12} {perf['throughput']:<12.1f} "
              f"{resources['avg_cpu']:<10.1f} {latency['p99']:<12.1f}")
    
    # Find best configuration
    best_throughput = max(all_results, key=lambda x: x['performance']['throughput'])
    best_latency = min(all_results, key=lambda x: x['latency']['p99'])
    
    print(f"\nBest Throughput: {best_throughput['performance']['throughput']:.1f} req/s")
    print(f"  Configuration: Threads={best_throughput['config']['thread_count']}, "
          f"Max Tasks={best_throughput['config']['max_concurrent_tasks']}, "
          f"Concurrent={best_throughput['config']['concurrent_requests']}")
    
    print(f"\nBest P99 Latency: {best_latency['latency']['p99']:.1f} ms")
    print(f"  Configuration: Threads={best_latency['config']['thread_count']}, "
          f"Max Tasks={best_latency['config']['max_concurrent_tasks']}, "
          f"Concurrent={best_latency['config']['concurrent_requests']}")

if __name__ == "__main__":
    asyncio.run(main())