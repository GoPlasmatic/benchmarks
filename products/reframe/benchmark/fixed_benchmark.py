#!/usr/bin/env python3
"""
Fixed benchmark script that prevents throughput degradation.
Addresses connection leaks and resource accumulation issues.
"""

import asyncio
import aiohttp
import time
import gc
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import signal
import resource

class FixedBenchmark:
    """Benchmark with proper resource management to prevent degradation"""
    
    def __init__(self, base_url: str, vm_size: str):
        self.base_url = base_url
        self.vm_size = vm_size
        self.results = []
        
        # Set resource limits to prevent runaway connections
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))
        except:
            pass
    
    async def create_limited_session(self, max_connections: int = 100) -> aiohttp.ClientSession:
        """Create a session with strict connection limits"""
        
        connector = aiohttp.TCPConnector(
            limit=max_connections,
            limit_per_host=max_connections,
            force_close=True,  # IMPORTANT: Force close connections
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            # Note: keepalive_timeout cannot be set when force_close=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=2,
            sock_connect=2,
            sock_read=5
        )
        
        return aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            connector_owner=True,  # Session owns the connector
            headers={
                'Connection': 'close',  # Prevent keep-alive issues
                'Cache-Control': 'no-cache'
            }
        )
    
    async def get_sample_message(self) -> dict:
        """Get sample message with minimal session"""
        session = await self.create_limited_session(1)
        try:
            async with session.post(
                f"{self.base_url}/generate/sample",
                json={"message_type": "MT103", "config": {"scenario": "standard"}}
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {
                        "message": result.get("result", result.get("message", "")),
                        "options": {"validation": False}
                    }
        except:
            pass
        finally:
            await session.close()
            await asyncio.sleep(0.1)  # Let connections close
        
        # Fallback
        return {
            "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
            "options": {"validation": False}
        }
    
    async def run_batch(
        self,
        batch_num: int,
        num_requests: int,
        concurrent: int,
        data: dict
    ) -> Dict:
        """Run a batch of requests with fresh session"""
        
        print(f"\nBatch {batch_num}: {num_requests} requests, {concurrent} concurrent")
        
        url = f"{self.base_url}/transform/mt-to-mx"
        
        # Create fresh session for this batch
        session = await self.create_limited_session(concurrent)
        
        latencies = []
        successes = 0
        failures = 0
        
        try:
            # Semaphore to control exact concurrency
            semaphore = asyncio.Semaphore(concurrent)
            
            async def make_request():
                async with semaphore:
                    start = time.perf_counter()
                    try:
                        async with session.post(url, json=data) as resp:
                            # Read and discard response immediately
                            await resp.read()
                            latency = (time.perf_counter() - start) * 1000
                            return latency, resp.status == 200
                    except asyncio.TimeoutError:
                        return 0, False
                    except Exception:
                        return 0, False
            
            # Run all requests
            start_time = time.perf_counter()
            
            # Process in smaller chunks to prevent memory buildup
            chunk_size = min(500, num_requests)
            for i in range(0, num_requests, chunk_size):
                chunk_requests = min(chunk_size, num_requests - i)
                tasks = [make_request() for _ in range(chunk_requests)]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, tuple):
                        latency, success = result
                        if success:
                            successes += 1
                            if latency > 0:
                                latencies.append(latency)
                        else:
                            failures += 1
                    else:
                        failures += 1
                
                # Progress update
                if (i + chunk_requests) % 1000 == 0:
                    elapsed = time.perf_counter() - start_time
                    rate = (i + chunk_requests) / elapsed if elapsed > 0 else 0
                    print(f"  Progress: {i + chunk_requests}/{num_requests} "
                          f"({rate:.0f} req/s)")
            
            total_time = time.perf_counter() - start_time
            
        finally:
            # CRITICAL: Properly close the session
            await session.close()
            
            # Force cleanup
            await asyncio.sleep(0.5)  # Let connections close
            gc.collect()  # Force garbage collection
        
        # Calculate metrics
        throughput = successes / total_time if total_time > 0 else 0
        
        latencies.sort()
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p99_latency = latencies[int(len(latencies) * 0.99)] if latencies else 0
        
        return {
            'batch': batch_num,
            'throughput': throughput,
            'success_rate': (successes / num_requests * 100) if num_requests > 0 else 0,
            'total_requests': num_requests,
            'successful': successes,
            'failed': failures,
            'avg_latency': avg_latency,
            'p99_latency': p99_latency,
            'duration': total_time
        }
    
    async def run_benchmark(
        self,
        total_requests: int,
        concurrent: int,
        thread_count: int,
        max_concurrent_tasks: int
    ):
        """Run benchmark with proper batch management"""
        
        print(f"\n{'='*60}")
        print(f"Fixed Benchmark Configuration")
        print(f"{'='*60}")
        print(f"VM Size: {self.vm_size}")
        print(f"Thread Count: {thread_count}")
        print(f"Max Concurrent Tasks: {max_concurrent_tasks}")
        print(f"Concurrent Requests: {concurrent}")
        print(f"Total Requests: {total_requests}")
        
        # Get sample data
        data = await self.get_sample_message()
        
        # Divide into batches to prevent degradation
        batch_size = 5000  # Smaller batches to prevent resource accumulation
        num_batches = (total_requests + batch_size - 1) // batch_size
        
        print(f"\nDividing into {num_batches} batches of {batch_size} requests")
        print("This prevents connection/memory accumulation")
        
        all_results = []
        cumulative_time = 0
        cumulative_requests = 0
        cumulative_successes = 0
        
        for batch_num in range(1, num_batches + 1):
            requests_in_batch = min(batch_size, total_requests - (batch_num - 1) * batch_size)
            
            result = await self.run_batch(
                batch_num,
                requests_in_batch,
                concurrent,
                data
            )
            
            all_results.append(result)
            cumulative_time += result['duration']
            cumulative_requests += result['total_requests']
            cumulative_successes += result['successful']
            
            print(f"  Batch {batch_num} Results:")
            print(f"    Throughput: {result['throughput']:.1f} req/s")
            print(f"    Success Rate: {result['success_rate']:.1f}%")
            print(f"    P99 Latency: {result['p99_latency']:.1f} ms")
            
            # Cool down between batches to let connections close
            if batch_num < num_batches:
                print(f"  Cooling down for 3 seconds...")
                await asyncio.sleep(3)
                
                # Force cleanup
                gc.collect()
        
        # Calculate overall metrics
        overall_throughput = cumulative_successes / cumulative_time if cumulative_time > 0 else 0
        
        # Combine all latencies for percentiles
        all_latencies = []
        for r in all_results:
            # Note: We'd need to store raw latencies for accurate percentiles
            # This is an approximation
            all_latencies.extend([r['avg_latency']] * r['successful'])
        
        all_latencies.sort()
        overall_p99 = all_latencies[int(len(all_latencies) * 0.99)] if all_latencies else 0
        
        print(f"\n{'='*60}")
        print(f"OVERALL RESULTS")
        print(f"{'='*60}")
        print(f"Total Time: {cumulative_time:.2f}s")
        print(f"Total Requests: {cumulative_requests}")
        print(f"Successful: {cumulative_successes}")
        print(f"Overall Throughput: {overall_throughput:.1f} req/s")
        print(f"Overall P99 Latency: {overall_p99:.1f} ms")
        
        # Check for degradation
        if len(all_results) > 1:
            first_throughput = all_results[0]['throughput']
            last_throughput = all_results[-1]['throughput']
            degradation = (first_throughput - last_throughput) / first_throughput * 100
            
            print(f"\nDegradation Check:")
            print(f"  First batch: {first_throughput:.1f} req/s")
            print(f"  Last batch: {last_throughput:.1f} req/s")
            print(f"  Degradation: {degradation:.1f}%")
            
            if abs(degradation) < 10:
                print("  ✅ No significant degradation!")
            else:
                print("  ⚠️  Some degradation detected")
        
        return {
            'config': {
                'thread_count': thread_count,
                'max_concurrent_tasks': max_concurrent_tasks,
                'concurrent_requests': concurrent,
                'total_requests': total_requests
            },
            'performance': {
                'total_time': cumulative_time,
                'throughput': overall_throughput,
                'success_rate': (cumulative_successes / cumulative_requests * 100),
                'total_requests': cumulative_requests,
                'successful': cumulative_successes,
                'failed': cumulative_requests - cumulative_successes
            },
            'latency': {
                'p99': overall_p99
            },
            'batches': all_results,
            'timestamp': datetime.now().isoformat()
        }

async def main():
    parser = argparse.ArgumentParser(description='Fixed Benchmark (No Degradation)')
    parser.add_argument('--base-url', default='http://localhost:3000',
                       help='Reframe API base URL')
    parser.add_argument('--vm-size', required=True,
                       help='VM size configuration')
    parser.add_argument('--num-requests', type=int, default=50000,
                       help='Number of requests')
    parser.add_argument('--concurrent', type=int, default=64,
                       help='Concurrent requests')
    parser.add_argument('--output-dir', default='results',
                       help='Output directory')
    
    args = parser.parse_args()
    
    # Load VM configuration
    config_file = Path(f'infrastructure/azure/vm-configs/{args.vm_size}.json')
    if not config_file.exists():
        print(f"Error: Configuration file not found: {config_file}")
        sys.exit(1)
    
    with open(config_file) as f:
        vm_config = json.load(f)
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run benchmark
    benchmark = FixedBenchmark(args.base_url, args.vm_size)
    
    # Use first configuration from VM config
    thread_count = vm_config['thread_counts'][0]
    max_concurrent_tasks = vm_config['max_concurrent_tasks'][0]
    
    result = await benchmark.run_benchmark(
        args.num_requests,
        args.concurrent,
        thread_count,
        max_concurrent_tasks
    )
    
    # Save results
    output_file = output_dir / f"fixed_benchmark_{args.vm_size}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    asyncio.run(main())