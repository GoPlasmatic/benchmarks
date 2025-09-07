#!/usr/bin/env python3
"""
Investigate throughput degradation issue by monitoring performance over time.
This script identifies if there's a resource leak or connection exhaustion.
"""

import asyncio
import aiohttp
import time
import psutil
import os
from datetime import datetime
from typing import Dict, List, Tuple
import json
import subprocess

class DegradationInvestigator:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.metrics = []
        self.start_time = time.time()
        
    async def monitor_connections(self) -> Dict:
        """Monitor TCP connection states"""
        try:
            # Get connection stats using netstat
            result = subprocess.run(
                "netstat -an | grep -E 'tcp.*:3000' | awk '{print $6}' | sort | uniq -c",
                shell=True,
                capture_output=True,
                text=True
            )
            
            states = {}
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        count, state = parts
                        states[state] = int(count)
            
            # Also count total connections
            total_result = subprocess.run(
                "netstat -an | grep -c ':3000'",
                shell=True,
                capture_output=True,
                text=True
            )
            total = int(total_result.stdout.strip()) if total_result.stdout.strip() else 0
            
            return {
                'total': total,
                'states': states,
                'time_wait': states.get('TIME_WAIT', 0),
                'established': states.get('ESTABLISHED', 0),
                'close_wait': states.get('CLOSE_WAIT', 0),
                'fin_wait': states.get('FIN_WAIT1', 0) + states.get('FIN_WAIT2', 0)
            }
        except Exception as e:
            return {'error': str(e)}
    
    async def run_wave(self, wave_num: int, requests_per_wave: int = 1000, concurrency: int = 64) -> Dict:
        """Run a single wave of requests and measure performance"""
        
        print(f"\n=== Wave {wave_num} ===")
        print(f"Time since start: {time.time() - self.start_time:.1f}s")
        
        # Monitor connections before
        conn_before = await self.monitor_connections()
        print(f"Connections before: {conn_before}")
        
        # Prepare request
        url = f"{self.base_url}/transform/mt-to-mx"
        data = {
            "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
            "options": {"validation": False}
        }
        
        # Create NEW session for each wave (important!)
        connector = aiohttp.TCPConnector(
            limit=concurrency * 2,
            limit_per_host=concurrency * 2,
            force_close=False,  # Keep connections alive
            ttl_dns_cache=300,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        
        latencies = []
        errors = []
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Semaphore for concurrency control
            sem = asyncio.Semaphore(concurrency)
            
            async def make_request():
                async with sem:
                    start = time.perf_counter()
                    try:
                        async with session.post(url, json=data) as resp:
                            await resp.read()
                            latency = (time.perf_counter() - start) * 1000
                            return latency, resp.status == 200, None
                    except asyncio.TimeoutError:
                        return 0, False, 'timeout'
                    except Exception as e:
                        return 0, False, str(e)[:50]
            
            # Run requests
            start_time = time.perf_counter()
            tasks = [make_request() for _ in range(requests_per_wave)]
            results = await asyncio.gather(*tasks)
            duration = time.perf_counter() - start_time
        
        # Process results
        successful = 0
        for latency, success, error in results:
            if success:
                successful += 1
                latencies.append(latency)
            elif error:
                errors.append(error)
        
        throughput = successful / duration if duration > 0 else 0
        
        # Monitor connections after
        await asyncio.sleep(2)  # Let connections settle
        conn_after = await self.monitor_connections()
        print(f"Connections after: {conn_after}")
        
        # Calculate metrics
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0
        
        # Memory usage
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        result = {
            'wave': wave_num,
            'time_since_start': time.time() - self.start_time,
            'throughput': throughput,
            'successful': successful,
            'failed': requests_per_wave - successful,
            'avg_latency': avg_latency,
            'p99_latency': p99_latency,
            'memory_mb': memory_mb,
            'connections_before': conn_before,
            'connections_after': conn_after,
            'connection_growth': conn_after.get('total', 0) - conn_before.get('total', 0),
            'errors': errors[:10] if errors else []
        }
        
        print(f"Throughput: {throughput:.1f} req/s")
        print(f"Success rate: {successful}/{requests_per_wave} ({successful/requests_per_wave*100:.1f}%)")
        print(f"Avg latency: {avg_latency:.1f}ms, P99: {p99_latency:.1f}ms")
        print(f"Memory: {memory_mb:.1f} MB")
        print(f"Connection growth: {result['connection_growth']}")
        
        return result
    
    async def investigate_degradation(self, num_waves: int = 10):
        """Run multiple waves and analyze degradation pattern"""
        
        print("="*60)
        print("DEGRADATION INVESTIGATION")
        print("="*60)
        print(f"Running {num_waves} waves of 1000 requests each")
        print(f"Target: {self.base_url}")
        
        # Initial health check
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    if resp.status == 200:
                        health = await resp.json()
                        print(f"Server health: {health}")
        except Exception as e:
            print(f"Health check failed: {e}")
        
        # Run waves
        for i in range(1, num_waves + 1):
            result = await self.run_wave(i)
            self.metrics.append(result)
            
            # Cool down between waves
            if i < num_waves:
                print(f"\nCooling down for 5 seconds...")
                await asyncio.sleep(5)
        
        # Analyze results
        self.analyze_degradation()
    
    def analyze_degradation(self):
        """Analyze the degradation pattern"""
        
        print("\n" + "="*60)
        print("DEGRADATION ANALYSIS")
        print("="*60)
        
        if len(self.metrics) < 2:
            print("Not enough data to analyze")
            return
        
        # Extract throughput over time
        throughputs = [m['throughput'] for m in self.metrics]
        latencies = [m['p99_latency'] for m in self.metrics]
        memories = [m['memory_mb'] for m in self.metrics]
        
        # Calculate degradation
        first_throughput = throughputs[0]
        last_throughput = throughputs[-1]
        degradation_pct = (first_throughput - last_throughput) / first_throughput * 100
        
        print(f"\nThroughput degradation: {first_throughput:.1f} → {last_throughput:.1f} req/s "
              f"({degradation_pct:.1f}% decrease)")
        
        print(f"\nP99 Latency increase: {latencies[0]:.1f} → {latencies[-1]:.1f} ms "
              f"({(latencies[-1] - latencies[0]):.1f}ms increase)")
        
        print(f"\nMemory growth: {memories[0]:.1f} → {memories[-1]:.1f} MB "
              f"({(memories[-1] - memories[0]):.1f}MB increase)")
        
        # Check connection accumulation
        total_connections = []
        time_wait_connections = []
        
        for m in self.metrics:
            if 'connections_after' in m and 'total' in m['connections_after']:
                total_connections.append(m['connections_after']['total'])
                time_wait_connections.append(m['connections_after'].get('time_wait', 0))
        
        if total_connections:
            print(f"\nConnection accumulation: {total_connections[0]} → {total_connections[-1]} "
                  f"(+{total_connections[-1] - total_connections[0]} connections)")
            
            if time_wait_connections:
                print(f"TIME_WAIT accumulation: {time_wait_connections[0]} → {time_wait_connections[-1]} "
                      f"(+{time_wait_connections[-1] - time_wait_connections[0]} connections)")
        
        # Identify the issue
        print("\n" + "="*60)
        print("DIAGNOSIS")
        print("="*60)
        
        issues = []
        
        if degradation_pct > 20:
            issues.append("❌ Significant throughput degradation detected")
            
            # Check patterns
            if memories[-1] - memories[0] > 100:
                issues.append("  → Memory leak suspected (growing memory usage)")
            
            if total_connections and total_connections[-1] - total_connections[0] > 100:
                issues.append("  → Connection leak (connections not being closed)")
            
            if time_wait_connections and time_wait_connections[-1] > 1000:
                issues.append("  → TIME_WAIT accumulation (port exhaustion risk)")
            
            # Check if it's gradual or sudden
            mid_point = len(throughputs) // 2
            mid_throughput = throughputs[mid_point]
            
            if (first_throughput - mid_throughput) / first_throughput > 0.1:
                issues.append("  → Gradual degradation (accumulating resource issue)")
            else:
                issues.append("  → Sudden degradation (hitting a limit)")
        else:
            print("✅ No significant degradation detected")
        
        if issues:
            for issue in issues:
                print(issue)
            
            print("\n" + "="*60)
            print("RECOMMENDATIONS")
            print("="*60)
            
            if any("Memory leak" in i for i in issues):
                print("1. Server-side memory leak:")
                print("   - Check for unclosed resources in transformation code")
                print("   - Monitor server memory with: docker stats")
                print("   - Restart server periodically")
            
            if any("Connection leak" in i for i in issues):
                print("2. Connection management issue:")
                print("   - Server not closing connections properly")
                print("   - Client sessions not being reused correctly")
                print("   - Try using force_close=True in connector")
            
            if any("TIME_WAIT" in i for i in issues):
                print("3. TCP port exhaustion:")
                print("   - Reduce TIME_WAIT timeout: sysctl -w net.ipv4.tcp_fin_timeout=10")
                print("   - Enable TIME_WAIT reuse: sysctl -w net.ipv4.tcp_tw_reuse=1")
                print("   - Use connection pooling more efficiently")
            
            if any("Gradual degradation" in i for i in issues):
                print("4. Resource accumulation:")
                print("   - Server needs periodic garbage collection")
                print("   - Implement request/response streaming")
                print("   - Add resource cleanup between batches")
        
        # Save detailed results
        filename = f"degradation_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump({
                'summary': {
                    'degradation_pct': degradation_pct,
                    'first_throughput': first_throughput,
                    'last_throughput': last_throughput,
                    'issues': issues
                },
                'metrics': self.metrics
            }, f, indent=2)
        
        print(f"\nDetailed results saved to: {filename}")
        
        # Print wave-by-wave summary
        print("\n" + "="*60)
        print("WAVE-BY-WAVE SUMMARY")
        print("="*60)
        print(f"{'Wave':<6} {'Time':<8} {'Throughput':<12} {'P99 Latency':<12} {'Memory':<10} {'Connections':<12}")
        print(f"{'    ':<6} {'(s)':<8} {'(req/s)':<12} {'(ms)':<12} {'(MB)':<10} {'(total)':<12}")
        print("-"*70)
        
        for m in self.metrics:
            conn_total = m.get('connections_after', {}).get('total', 0)
            print(f"{m['wave']:<6} {m['time_since_start']:<8.1f} {m['throughput']:<12.1f} "
                  f"{m['p99_latency']:<12.1f} {m['memory_mb']:<10.1f} {conn_total:<12}")

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Investigate Performance Degradation')
    parser.add_argument('--base-url', default='http://localhost:3000',
                       help='Reframe API base URL')
    parser.add_argument('--waves', type=int, default=10,
                       help='Number of waves to run')
    
    args = parser.parse_args()
    
    investigator = DegradationInvestigator(args.base_url)
    await investigator.investigate_degradation(args.waves)

if __name__ == "__main__":
    asyncio.run(main())