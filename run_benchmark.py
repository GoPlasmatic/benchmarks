#!/usr/bin/env python3
"""
Master benchmark runner that orchestrates the entire benchmarking process
with automatic performance tuning and result analysis.
"""

import asyncio
import subprocess
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import argparse

class BenchmarkOrchestrator:
    """Orchestrates benchmark execution with performance optimizations"""
    
    def __init__(self, vm_size: str, base_url: str, output_dir: str = "results"):
        self.vm_size = vm_size
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load VM configuration
        self.vm_config = self._load_vm_config()
        
        # Benchmark configurations to test
        self.test_matrix = self._generate_test_matrix()
        
    def _load_vm_config(self) -> dict:
        """Load VM configuration from JSON file"""
        config_file = Path(f"infrastructure/azure/vm-configs/{self.vm_size}.json")
        if not config_file.exists():
            raise ValueError(f"Configuration not found for VM size: {self.vm_size}")
        
        with open(config_file) as f:
            return json.load(f)
    
    def _generate_test_matrix(self) -> List[Dict]:
        """Generate test matrix based on VM configuration"""
        matrix = []
        
        # Optimized configurations based on VM size
        if self.vm_size == "2-core":
            configurations = [
                {"threads": 2, "max_tasks": 8, "concurrent": 32},
                {"threads": 2, "max_tasks": 16, "concurrent": 64},
                {"threads": 4, "max_tasks": 8, "concurrent": 32},
            ]
        elif self.vm_size == "4-core":
            configurations = [
                {"threads": 4, "max_tasks": 16, "concurrent": 64},
                {"threads": 4, "max_tasks": 32, "concurrent": 128},
                {"threads": 8, "max_tasks": 16, "concurrent": 64},
            ]
        elif self.vm_size == "8-core":
            configurations = [
                {"threads": 4, "max_tasks": 32, "concurrent": 128},
                {"threads": 8, "max_tasks": 32, "concurrent": 256},
                {"threads": 8, "max_tasks": 64, "concurrent": 256},
                {"threads": 16, "max_tasks": 32, "concurrent": 128},
            ]
        elif self.vm_size == "16-core":
            configurations = [
                {"threads": 8, "max_tasks": 64, "concurrent": 256},
                {"threads": 16, "max_tasks": 64, "concurrent": 512},
                {"threads": 16, "max_tasks": 128, "concurrent": 512},
                {"threads": 32, "max_tasks": 64, "concurrent": 256},
            ]
        else:
            # Default configurations
            configurations = []
            for threads in self.vm_config['thread_counts']:
                for max_tasks in self.vm_config['max_concurrent_tasks']:
                    for concurrent in [64, 128, 256]:
                        configurations.append({
                            "threads": threads,
                            "max_tasks": max_tasks,
                            "concurrent": concurrent
                        })
        
        return configurations
    
    def apply_system_optimizations(self):
        """Apply system-level optimizations for benchmarking"""
        print("Applying system optimizations...")
        
        optimizations = [
            # File descriptor limits
            "sudo sysctl -w fs.file-max=2097152",
            "sudo sysctl -w fs.nr_open=2097152",
            
            # Network stack optimizations
            "sudo sysctl -w net.core.somaxconn=65535",
            "sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65535",
            "sudo sysctl -w net.core.netdev_max_backlog=65535",
            "sudo sysctl -w net.ipv4.tcp_tw_reuse=1",
            "sudo sysctl -w net.ipv4.tcp_fin_timeout=15",
            "sudo sysctl -w net.ipv4.ip_local_port_range='1024 65535'",
            
            # TCP buffer sizes
            "sudo sysctl -w net.core.rmem_max=134217728",
            "sudo sysctl -w net.core.wmem_max=134217728",
            "sudo sysctl -w net.ipv4.tcp_rmem='4096 262144 134217728'",
            "sudo sysctl -w net.ipv4.tcp_wmem='4096 262144 134217728'",
            
            # Connection tracking
            "sudo sysctl -w net.netfilter.nf_conntrack_max=1000000",
            
            # CPU frequency scaling (performance mode)
            "sudo cpupower frequency-set -g performance 2>/dev/null || true",
        ]
        
        for cmd in optimizations:
            try:
                subprocess.run(cmd, shell=True, check=False, capture_output=True)
            except Exception:
                pass  # Some optimizations might not be available
        
        # Set ulimits for current session
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_NOFILE, (1048576, 1048576))
        except Exception:
            pass
        
        print("System optimizations applied.")
    
    async def run_single_benchmark(self, config: Dict, test_num: int, total_tests: int) -> Dict:
        """Run a single benchmark configuration"""
        print(f"\n{'='*60}")
        print(f"Test {test_num}/{total_tests}")
        print(f"Configuration: Threads={config['threads']}, "
              f"MaxTasks={config['max_tasks']}, Concurrent={config['concurrent']}")
        print(f"{'='*60}")
        
        # Prepare environment variables
        env = os.environ.copy()
        env.update({
            'REFRAME_THREAD_COUNT': str(config['threads']),
            'REFRAME_MAX_CONCURRENT_TASKS': str(config['max_tasks']),
            'UV_THREADPOOL_SIZE': str(config['threads'] * 4),
        })
        
        # Build command
        cmd = [
            sys.executable,
            "products/reframe/benchmark/optimized_benchmark.py",
            "--base-url", self.base_url,
            "--vm-size", self.vm_size,
            "--num-requests", "50000",  # Start with smaller batch
            "--concurrent-levels", str(config['concurrent']),
            "--output-dir", str(self.output_dir)
        ]
        
        # Run benchmark
        start_time = datetime.now()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                print(f"Benchmark failed: {stderr.decode()}")
                return None
            
            # Parse output for results
            output = stdout.decode()
            
            # Extract key metrics from output
            throughput = self._extract_metric(output, "Throughput:", "req/s")
            p99_latency = self._extract_metric(output, "P99:", "ms")
            avg_cpu = self._extract_metric(output, "Avg CPU:", "%")
            
            result = {
                'config': config,
                'throughput': throughput,
                'p99_latency': p99_latency,
                'avg_cpu': avg_cpu,
                'duration': (datetime.now() - start_time).total_seconds(),
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"\nResult: Throughput={throughput:.1f} req/s, "
                  f"P99={p99_latency:.1f} ms, CPU={avg_cpu:.1f}%")
            
            return result
            
        except Exception as e:
            print(f"Error running benchmark: {e}")
            return None
    
    def _extract_metric(self, output: str, marker: str, unit: str) -> float:
        """Extract a metric value from benchmark output"""
        try:
            lines = output.split('\n')
            for line in lines:
                if marker in line:
                    # Extract number before unit
                    parts = line.split(marker)[1].strip().split()
                    if parts:
                        value = parts[0].replace(unit, '').strip()
                        return float(value)
        except Exception:
            pass
        return 0.0
    
    async def run_benchmark_suite(self):
        """Run complete benchmark suite with all configurations"""
        print(f"\nStarting Benchmark Suite for {self.vm_size}")
        print(f"VM: {self.vm_config['azure_sku']}")
        print(f"vCPUs: {self.vm_config['vcpus']}, Memory: {self.vm_config['memory_gb']} GB")
        
        # Apply system optimizations
        self.apply_system_optimizations()
        
        # Run warmup
        print("\nRunning warmup phase...")
        await self._run_warmup()
        
        # Run benchmarks
        results = []
        test_num = 0
        total_tests = len(self.test_matrix)
        
        for config in self.test_matrix:
            test_num += 1
            result = await self.run_single_benchmark(config, test_num, total_tests)
            
            if result:
                results.append(result)
            
            # Cool down between tests
            if test_num < total_tests:
                print("\nCooling down for 15 seconds...")
                await asyncio.sleep(15)
        
        # Save and analyze results
        self._save_results(results)
        self._analyze_results(results)
        
        return results
    
    async def _run_warmup(self):
        """Run warmup requests to stabilize the system"""
        warmup_config = {
            'threads': self.vm_config['thread_counts'][0],
            'max_tasks': self.vm_config['max_concurrent_tasks'][0],
            'concurrent': 32
        }
        
        env = os.environ.copy()
        env.update({
            'REFRAME_THREAD_COUNT': str(warmup_config['threads']),
            'REFRAME_MAX_CONCURRENT_TASKS': str(warmup_config['max_tasks']),
        })
        
        cmd = [
            sys.executable,
            "products/reframe/benchmark/optimized_benchmark.py",
            "--base-url", self.base_url,
            "--vm-size", self.vm_size,
            "--num-requests", "1000",
            "--concurrent-levels", "32",
            "--output-dir", str(self.output_dir / "warmup")
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await process.communicate()
        print("Warmup completed.")
    
    def _save_results(self, results: List[Dict]):
        """Save benchmark results to JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f"benchmark_results_{self.vm_size}_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump({
                'vm_config': self.vm_config,
                'test_matrix': self.test_matrix,
                'results': results,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")
    
    def _analyze_results(self, results: List[Dict]):
        """Analyze and print summary of results"""
        if not results:
            print("\nNo valid results to analyze.")
            return
        
        print("\n" + "="*80)
        print("BENCHMARK RESULTS SUMMARY")
        print("="*80)
        
        # Sort by throughput
        results_by_throughput = sorted(results, key=lambda x: x['throughput'], reverse=True)
        
        print("\nTop 3 Configurations by Throughput:")
        print(f"{'Rank':<5} {'Threads':<8} {'MaxTasks':<10} {'Concurrent':<12} "
              f"{'Throughput':<15} {'P99 Latency':<12} {'CPU %':<8}")
        print("-"*80)
        
        for i, result in enumerate(results_by_throughput[:3], 1):
            config = result['config']
            print(f"{i:<5} {config['threads']:<8} {config['max_tasks']:<10} "
                  f"{config['concurrent']:<12} {result['throughput']:<15.1f} "
                  f"{result['p99_latency']:<12.1f} {result['avg_cpu']:<8.1f}")
        
        # Best latency
        best_latency = min(results, key=lambda x: x['p99_latency'])
        print(f"\nBest P99 Latency: {best_latency['p99_latency']:.1f} ms")
        print(f"  Configuration: Threads={best_latency['config']['threads']}, "
              f"MaxTasks={best_latency['config']['max_tasks']}, "
              f"Concurrent={best_latency['config']['concurrent']}")
        print(f"  Throughput: {best_latency['throughput']:.1f} req/s")
        
        # Recommendations
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)
        
        optimal = results_by_throughput[0]
        print(f"\nOptimal Configuration for {self.vm_size}:")
        print(f"  REFRAME_THREAD_COUNT={optimal['config']['threads']}")
        print(f"  REFRAME_MAX_CONCURRENT_TASKS={optimal['config']['max_tasks']}")
        print(f"  Concurrent Requests: {optimal['config']['concurrent']}")
        print(f"  Expected Throughput: {optimal['throughput']:.1f} req/s")
        print(f"  Expected P99 Latency: {optimal['p99_latency']:.1f} ms")
        
        # Performance assessment
        if optimal['throughput'] < 1000:
            print("\n⚠️  Performance is below expected. Consider:")
            print("  - Checking network connectivity between VMs")
            print("  - Verifying Reframe server configuration")
            print("  - Increasing VM size or using premium SSD")
        elif optimal['throughput'] < 3000:
            print("\n✓ Performance is acceptable but can be improved. Consider:")
            print("  - Using accelerated networking on Azure VMs")
            print("  - Implementing connection pooling in Reframe")
        else:
            print("\n✅ Excellent performance achieved!")

async def main():
    parser = argparse.ArgumentParser(description='Master Benchmark Orchestrator')
    parser.add_argument('--vm-size', required=True, 
                       choices=['2-core', '4-core', '8-core', '16-core'],
                       help='VM size configuration')
    parser.add_argument('--base-url', default='http://localhost:3000',
                       help='Reframe API base URL')
    parser.add_argument('--output-dir', default='results',
                       help='Output directory for results')
    parser.add_argument('--docker', action='store_true',
                       help='Run benchmarks in Docker containers')
    
    args = parser.parse_args()
    
    if args.docker:
        print("Docker mode: Ensure docker-compose is configured properly")
        # Could add docker-compose orchestration here
    
    orchestrator = BenchmarkOrchestrator(
        vm_size=args.vm_size,
        base_url=args.base_url,
        output_dir=args.output_dir
    )
    
    results = await orchestrator.run_benchmark_suite()
    
    # Return exit code based on results
    if results and any(r['throughput'] > 100 for r in results):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())