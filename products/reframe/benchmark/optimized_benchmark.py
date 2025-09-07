#!/usr/bin/env python3
"""
Optimized benchmark script for Reframe with improved concurrency and connection management.
Fixes throughput degradation issues on Azure VMs.
"""

import asyncio
import aiohttp
import time
import sys
import json
import argparse
import psutil
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import signal

class CPUMonitor:
    """Lightweight CPU monitor with reduced overhead"""
    
    def __init__(self, interval: float = 2.0):  # Increased interval to reduce overhead
        self.interval = interval
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        self.monitor_thread = None
    
    def start(self):
        """Start monitoring CPU and memory usage"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop monitoring and return statistics"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        
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
        """Background thread to collect CPU/memory samples with reduced overhead"""
        # Use interval-based sampling to reduce overhead
        process = psutil.Process()
        
        while self.monitoring:
            try:
                # Use process-specific CPU instead of system-wide
                cpu_percent = process.cpu_percent(interval=self.interval)
                memory_info = process.memory_info()
                memory_percent = (memory_info.rss / psutil.virtual_memory().total) * 100
                
                if cpu_percent > 0:  # Filter out initial 0 values
                    self.cpu_samples.append(cpu_percent)
                    self.memory_samples.append(memory_percent)
                
            except Exception:
                break  # Silently exit on error

class RequestWorker:
    """Worker that continuously processes requests from a queue"""
    
    def __init__(self, worker_id: int, url: str, data: dict, stats: dict):
        self.worker_id = worker_id
        self.url = url
        self.data = data
        self.stats = stats
        self.session = None
        self.running = True
    
    async def start(self):
        """Start the worker with its own session and connection pool"""
        # Create dedicated session with optimized connection pool
        connector = aiohttp.TCPConnector(
            limit=50,  # Limit per worker
            limit_per_host=50,
            ttl_dns_cache=300,
            force_close=False,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=10,  # Total timeout per request
            connect=2,
            sock_read=5
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'Connection': 'keep-alive'}
        )
    
    async def process_request(self) -> Tuple[float, bool]:
        """Process a single request with the worker's session"""
        start = time.perf_counter()
        try:
            async with self.session.post(self.url, json=self.data) as resp:
                await resp.read()  # Use read() instead of text() for better performance
                latency_ms = (time.perf_counter() - start) * 1000
                return latency_ms, resp.status == 200
        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start) * 1000
            return latency_ms, False
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            return latency_ms, False
    
    async def stop(self):
        """Clean up the worker's resources"""
        self.running = False
        if self.session:
            await self.session.close()

async def get_sample_message(base_url: str) -> dict:
    """Get a sample MT103 message from the generator API"""
    connector = aiohttp.TCPConnector(limit=1)
    timeout = aiohttp.ClientTimeout(total=5)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        try:
            async with session.post(f"{base_url}/generate/sample",
                                    json={"message_type": "MT103", "config": {"scenario": "standard"}}) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {
                        "message": result.get("result", result.get("message", "")),
                        "options": {"validation": False}
                    }
        except Exception:
            pass
    
    # Fallback message
    return {
        "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
        "options": {"validation": False}
    }

async def check_server_health(base_url: str) -> bool:
    """Quick health check"""
    try:
        connector = aiohttp.TCPConnector(limit=1)
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(f"{base_url}/health") as resp:
                return resp.status == 200
    except Exception:
        return False

async def run_benchmark_test(
    base_url: str,
    num_requests: int,
    concurrent: int,
    thread_count: int,
    max_concurrent_tasks: int
) -> dict:
    """Run optimized benchmark test with worker pool and continuous request flow"""
    
    url = f"{base_url}/transform/mt-to-mx"
    
    print(f"\nConfiguration:")
    print(f"  Thread Count: {thread_count}")
    print(f"  Max Concurrent Tasks: {max_concurrent_tasks}")
    print(f"  Concurrent Workers: {concurrent}")
    print(f"  Total Requests: {num_requests}")
    
    # Get sample message
    data = await get_sample_message(base_url)
    
    # Start lightweight CPU monitoring
    monitor = CPUMonitor(interval=3.0)  # Less frequent monitoring
    monitor.start()
    
    # Statistics tracking
    stats = {
        'latencies': [],
        'successes': 0,
        'failures': 0,
        'lock': asyncio.Lock()
    }
    
    # Create worker pool
    num_workers = min(concurrent, 100)  # Cap workers at 100
    workers = []
    
    print(f"Creating {num_workers} workers...")
    for i in range(num_workers):
        worker = RequestWorker(i, url, data, stats)
        await worker.start()
        workers.append(worker)
    
    # Warmup phase
    print(f"Warming up with {num_workers * 2} requests...")
    warmup_tasks = []
    for worker in workers:
        for _ in range(2):
            warmup_tasks.append(worker.process_request())
    await asyncio.gather(*warmup_tasks, return_exceptions=True)
    
    print(f"Running {num_requests} requests...")
    start_time = time.perf_counter()
    last_report = start_time
    
    # Use semaphore to control concurrency
    semaphore = asyncio.Semaphore(concurrent)
    
    async def process_with_stats(worker: RequestWorker):
        """Process a request and update stats"""
        async with semaphore:
            latency, success = await worker.process_request()
            
            async with stats['lock']:
                stats['latencies'].append(latency)
                if success:
                    stats['successes'] += 1
                else:
                    stats['failures'] += 1
    
    # Create all tasks at once and let asyncio manage them
    tasks = []
    for i in range(num_requests):
        worker = workers[i % num_workers]  # Round-robin distribution
        tasks.append(process_with_stats(worker))
        
        # Process in chunks to avoid memory issues
        if (i + 1) % 1000 == 0:
            # Start processing current batch
            current_tasks = tasks[-1000:]
            
            # Non-blocking progress check
            completed = stats['successes'] + stats['failures']
            current_time = time.perf_counter()
            if current_time - last_report >= 2:  # Report every 2 seconds
                elapsed = current_time - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (num_requests - completed) / rate if rate > 0 else 0
                print(f"  Progress: {completed}/{num_requests} ({completed/num_requests*100:.1f}%) | "
                      f"Rate: {rate:.0f} req/s | ETA: {eta:.0f}s | "
                      f"Success: {stats['successes']}/{completed}")
                last_report = current_time
    
    # Process all remaining tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    
    total_time = time.perf_counter() - start_time
    print(f"\n  Completed: {num_requests} requests in {total_time:.2f}s")
    
    # Clean up workers
    cleanup_tasks = [worker.stop() for worker in workers]
    await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    # Stop CPU monitoring
    cpu_stats = monitor.stop()
    
    # Calculate statistics
    latencies = sorted(stats['latencies'])
    
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
            'concurrent_workers': num_workers,
            'total_requests': num_requests
        },
        'performance': {
            'total_time': total_time,
            'throughput': throughput,
            'success_rate': (stats['successes'] / num_requests * 100) if num_requests > 0 else 0,
            'total_requests': num_requests,
            'successful': stats['successes'],
            'failed': stats['failures']
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

async def main():
    parser = argparse.ArgumentParser(description='Optimized Reframe Benchmark')
    parser.add_argument('--base-url', default='http://localhost:3000', help='Reframe API base URL')
    parser.add_argument('--vm-size', required=True, help='VM size configuration (2-core, 4-core, etc)')
    parser.add_argument('--num-requests', type=int, default=100000, help='Number of requests per test')
    parser.add_argument('--concurrent-levels', default='64,128,256', help='Concurrent worker levels')
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
    
    print(f"Optimized Reframe Performance Benchmark")
    print(f"=======================================")
    print(f"VM Size: {args.vm_size}")
    print(f"VM SKU: {vm_config['azure_sku']}")
    print(f"vCPUs: {vm_config['vcpus']}")
    print(f"Memory: {vm_config['memory_gb']} GB")
    print(f"Thread Counts: {thread_counts}")
    print(f"Max Concurrent Tasks: {max_concurrent_tasks_list}")
    print(f"Concurrent Levels: {concurrent_levels}")
    print()
    
    # Check server status
    if not await check_server_health(args.base_url):
        print(f"Error: Server is not responding at {args.base_url}")
        sys.exit(1)
    print(f"Server is running at {args.base_url}\n")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run benchmark tests
    all_results = []
    test_number = 0
    total_tests = len(thread_counts) * len(max_concurrent_tasks_list) * len(concurrent_levels)
    
    for thread_count in thread_counts:
        for max_concurrent_tasks in max_concurrent_tasks_list:
            print(f"\nNote: Configure server with REFRAME_THREAD_COUNT={thread_count} "
                  f"REFRAME_MAX_CONCURRENT_TASKS={max_concurrent_tasks}")
            
            # Allow time for any server reconfiguration
            await asyncio.sleep(2)
            
            for concurrent in concurrent_levels:
                test_number += 1
                print(f"\n--- Test {test_number}/{total_tests} ---")
                
                try:
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
                    print(f"  Success Rate: {result['performance']['success_rate']:.1f}%")
                    print(f"  Avg CPU: {result['resources']['avg_cpu']:.1f}%")
                    print(f"  Peak CPU: {result['resources']['peak_cpu']:.1f}%")
                    print(f"  Latency (ms):")
                    print(f"    Min: {result['latency']['min']:.1f}")
                    print(f"    Avg: {result['latency']['avg']:.1f}")
                    print(f"    P95: {result['latency']['p95']:.1f}")
                    print(f"    P99: {result['latency']['p99']:.1f}")
                    print(f"    Max: {result['latency']['max']:.1f}")
                    
                except Exception as e:
                    print(f"Test failed: {e}")
                    continue
    
    # Save results
    output_file = output_dir / f"optimized_benchmark_{args.vm_size}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    print(f"{'Threads':<8} {'Max Tasks':<10} {'Workers':<10} {'Throughput':<12} {'Success':<10} {'P99 Latency':<12}")
    print(f"{'       ':<8} {'         ':<10} {'        ':<10} {'(req/s)':<12} {'(%)':<10} {'(ms)':<12}")
    print("-" * 72)
    
    for result in all_results:
        config = result['config']
        perf = result['performance']
        latency = result['latency']
        
        print(f"{config['thread_count']:<8} {config['max_concurrent_tasks']:<10} "
              f"{config['concurrent_workers']:<10} {perf['throughput']:<12.1f} "
              f"{perf['success_rate']:<10.1f} {latency['p99']:<12.1f}")
    
    if all_results:
        # Find best configuration
        best_throughput = max(all_results, key=lambda x: x['performance']['throughput'])
        best_latency = min(all_results, key=lambda x: x['latency']['p99'])
        
        print(f"\nBest Throughput: {best_throughput['performance']['throughput']:.1f} req/s")
        print(f"  Configuration: Threads={best_throughput['config']['thread_count']}, "
              f"Max Tasks={best_throughput['config']['max_concurrent_tasks']}, "
              f"Workers={best_throughput['config']['concurrent_workers']}")
        
        print(f"\nBest P99 Latency: {best_latency['latency']['p99']:.1f} ms")
        print(f"  Configuration: Threads={best_latency['config']['thread_count']}, "
              f"Max Tasks={best_latency['config']['max_concurrent_tasks']}, "
              f"Workers={best_latency['config']['concurrent_workers']}")

if __name__ == "__main__":
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    asyncio.run(main())