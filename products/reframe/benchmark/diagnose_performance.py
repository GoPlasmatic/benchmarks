#!/usr/bin/env python3
"""
Diagnostic script to identify the real performance bottleneck.
Tests different aspects of the system to pinpoint the issue.
"""

import asyncio
import aiohttp
import time
import sys
import json
import socket
import psutil
from datetime import datetime
from typing import Dict, List, Tuple

class PerformanceDiagnostics:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.results = {}
        
    async def test_connection_limits(self):
        """Test how many concurrent connections can be established"""
        print("\n=== Testing Connection Limits ===")
        
        url = f"{self.base_url}/health"
        max_connections = 0
        
        # Try different connection limits
        for limit in [10, 50, 100, 200, 500, 1000]:
            try:
                connector = aiohttp.TCPConnector(
                    limit=limit,
                    limit_per_host=limit,
                    force_close=True
                )
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    tasks = []
                    for _ in range(limit):
                        tasks.append(session.get(url))
                    
                    start = time.perf_counter()
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    duration = time.perf_counter() - start
                    
                    successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
                    
                    # Close all responses
                    for r in responses:
                        if not isinstance(r, Exception):
                            r.close()
                    
                    print(f"  Limit {limit}: {successful}/{limit} successful in {duration:.2f}s")
                    
                    if successful == limit:
                        max_connections = limit
                    else:
                        break
                        
            except Exception as e:
                print(f"  Limit {limit}: Failed - {e}")
                break
        
        self.results['max_concurrent_connections'] = max_connections
        return max_connections
    
    async def test_request_latency(self):
        """Test individual request latency without concurrency"""
        print("\n=== Testing Single Request Latency ===")
        
        url = f"{self.base_url}/transform/mt-to-mx"
        
        # Get sample data
        data = {
            "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
            "options": {"validation": False}
        }
        
        latencies = []
        
        connector = aiohttp.TCPConnector(limit=1)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Warmup
            for _ in range(5):
                async with session.post(url, json=data) as resp:
                    await resp.read()
            
            # Test
            for i in range(20):
                start = time.perf_counter()
                try:
                    async with session.post(url, json=data) as resp:
                        await resp.read()
                        latency = (time.perf_counter() - start) * 1000
                        latencies.append(latency)
                        if i % 5 == 0:
                            print(f"  Request {i+1}: {latency:.1f}ms")
                except Exception as e:
                    print(f"  Request {i+1}: Failed - {e}")
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            
            print(f"\n  Results:")
            print(f"    Min: {min_latency:.1f}ms")
            print(f"    Avg: {avg_latency:.1f}ms")
            print(f"    Max: {max_latency:.1f}ms")
            
            self.results['single_request_latency'] = {
                'min': min_latency,
                'avg': avg_latency,
                'max': max_latency
            }
            
            return avg_latency
        return 0
    
    async def test_connection_reuse(self):
        """Test if connection keep-alive is working"""
        print("\n=== Testing Connection Reuse ===")
        
        url = f"{self.base_url}/health"
        
        # Test with connection reuse
        connector1 = aiohttp.TCPConnector(
            limit=1,
            force_close=False,
            enable_cleanup_closed=True
        )
        
        async with aiohttp.ClientSession(connector=connector1) as session:
            reuse_times = []
            for i in range(10):
                start = time.perf_counter()
                async with session.get(url) as resp:
                    await resp.read()
                    reuse_times.append((time.perf_counter() - start) * 1000)
        
        # Test without connection reuse
        connector2 = aiohttp.TCPConnector(
            limit=1,
            force_close=True
        )
        
        async with aiohttp.ClientSession(connector=connector2) as session:
            no_reuse_times = []
            for i in range(10):
                start = time.perf_counter()
                async with session.get(url) as resp:
                    await resp.read()
                    no_reuse_times.append((time.perf_counter() - start) * 1000)
        
        avg_reuse = sum(reuse_times) / len(reuse_times)
        avg_no_reuse = sum(no_reuse_times) / len(no_reuse_times)
        
        print(f"  With reuse: {avg_reuse:.1f}ms avg")
        print(f"  Without reuse: {avg_no_reuse:.1f}ms avg")
        print(f"  Improvement: {((avg_no_reuse - avg_reuse) / avg_no_reuse * 100):.1f}%")
        
        self.results['connection_reuse'] = {
            'with_reuse': avg_reuse,
            'without_reuse': avg_no_reuse,
            'improvement_percent': ((avg_no_reuse - avg_reuse) / avg_no_reuse * 100)
        }
    
    async def test_throughput_scaling(self):
        """Test how throughput scales with concurrency"""
        print("\n=== Testing Throughput Scaling ===")
        
        url = f"{self.base_url}/transform/mt-to-mx"
        data = {
            "message": "{1:F01BANKBEBBAXXX0237205215}{2:O103080907BANKFRPPAXXX02372052150809070917N}{3:{108:ILOVESEPA}}{4:\n:20:REF12345678901234\n:23B:CRED\n:32A:240101EUR1000,00\n:50K:/12345678901234567890\nJOHN DOE\n123 MAIN STREET\nANYTOWN\n:59:/98765432109876543210\nJANE SMITH\n456 PARK AVENUE\nOTHERCITY\n:71A:SHA\n-}",
            "options": {"validation": False}
        }
        
        results = []
        
        for concurrency in [1, 2, 4, 8, 16, 32, 64]:
            connector = aiohttp.TCPConnector(
                limit=concurrency * 2,
                limit_per_host=concurrency * 2
            )
            
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                num_requests = min(1000, concurrency * 20)
                
                async def make_request():
                    try:
                        async with session.post(url, json=data) as resp:
                            await resp.read()
                            return resp.status == 200
                    except:
                        return False
                
                start = time.perf_counter()
                
                # Use semaphore to control concurrency
                sem = asyncio.Semaphore(concurrency)
                
                async def bounded_request():
                    async with sem:
                        return await make_request()
                
                tasks = [bounded_request() for _ in range(num_requests)]
                responses = await asyncio.gather(*tasks)
                
                duration = time.perf_counter() - start
                successful = sum(1 for r in responses if r)
                throughput = successful / duration
                
                print(f"  Concurrency {concurrency:3}: {throughput:6.1f} req/s ({successful}/{num_requests} successful)")
                
                results.append({
                    'concurrency': concurrency,
                    'throughput': throughput,
                    'success_rate': successful / num_requests * 100
                })
        
        self.results['throughput_scaling'] = results
        
        # Find optimal concurrency
        best = max(results, key=lambda x: x['throughput'])
        print(f"\n  Best throughput: {best['throughput']:.1f} req/s at concurrency {best['concurrency']}")
        
        return best
    
    async def test_network_latency(self):
        """Test network round-trip time"""
        print("\n=== Testing Network Latency ===")
        
        # Parse hostname from URL
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
        hostname = parsed.hostname
        
        print(f"  Testing RTT to {hostname}...")
        
        # Use socket for TCP ping
        latencies = []
        for i in range(10):
            try:
                start = time.perf_counter()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((hostname, parsed.port or 80))
                sock.close()
                
                if result == 0:
                    latency = (time.perf_counter() - start) * 1000
                    latencies.append(latency)
                    if i % 3 == 0:
                        print(f"    RTT {i+1}: {latency:.2f}ms")
            except Exception as e:
                print(f"    RTT {i+1}: Failed - {e}")
        
        if latencies:
            avg_rtt = sum(latencies) / len(latencies)
            print(f"\n  Average RTT: {avg_rtt:.2f}ms")
            self.results['network_rtt'] = avg_rtt
            return avg_rtt
        return 0
    
    async def test_server_capacity(self):
        """Test server's actual processing capacity"""
        print("\n=== Testing Server Capacity ===")
        
        # First, check server configuration
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    if resp.status == 200:
                        health = await resp.json()
                        print(f"  Server status: {health}")
        except Exception as e:
            print(f"  Could not get server status: {e}")
        
        # Test with minimal payload to isolate server processing
        url = f"{self.base_url}/transform/mt-to-mx"
        minimal_data = {
            "message": "{1:F01BANKBEBBAXXX0237205215}{4::20:TEST-}",
            "options": {"validation": False}
        }
        
        connector = aiohttp.TCPConnector(limit=100)
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Burst test
            print("\n  Burst test (100 concurrent)...")
            
            tasks = []
            for _ in range(100):
                tasks.append(session.post(url, json=minimal_data))
            
            start = time.perf_counter()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.perf_counter() - start
            
            successful = 0
            for r in responses:
                if not isinstance(r, Exception):
                    if r.status == 200:
                        successful += 1
                    r.close()
            
            burst_throughput = successful / duration
            print(f"    Burst throughput: {burst_throughput:.1f} req/s")
            
            self.results['server_burst_capacity'] = burst_throughput
    
    def print_diagnosis(self):
        """Analyze results and provide diagnosis"""
        print("\n" + "="*60)
        print("DIAGNOSIS SUMMARY")
        print("="*60)
        
        issues = []
        
        # Check single request latency
        if 'single_request_latency' in self.results:
            avg_latency = self.results['single_request_latency']['avg']
            if avg_latency > 100:
                issues.append(f"❌ High base latency: {avg_latency:.1f}ms (should be <50ms)")
                issues.append("   → Server is slow or network latency is high")
            else:
                print(f"✅ Base latency OK: {avg_latency:.1f}ms")
        
        # Check connection limits
        if 'max_concurrent_connections' in self.results:
            max_conn = self.results['max_concurrent_connections']
            if max_conn < 100:
                issues.append(f"❌ Low connection limit: {max_conn}")
                issues.append("   → Server or network limiting connections")
            else:
                print(f"✅ Connection limit OK: {max_conn}+")
        
        # Check throughput scaling
        if 'throughput_scaling' in self.results:
            scaling = self.results['throughput_scaling']
            if len(scaling) > 1:
                # Check if throughput increases with concurrency
                early = scaling[0]['throughput']
                peak = max(s['throughput'] for s in scaling)
                
                if peak < early * 2:
                    issues.append(f"❌ Poor concurrency scaling: {peak:.1f} vs {early:.1f} req/s")
                    issues.append("   → Server not handling concurrent requests well")
                else:
                    print(f"✅ Concurrency scaling OK: {peak:.1f} req/s peak")
        
        # Check network RTT
        if 'network_rtt' in self.results:
            rtt = self.results['network_rtt']
            if rtt > 50:
                issues.append(f"❌ High network RTT: {rtt:.1f}ms")
                issues.append("   → Consider colocating client and server")
            else:
                print(f"✅ Network RTT OK: {rtt:.1f}ms")
        
        # Check server capacity
        if 'server_burst_capacity' in self.results:
            capacity = self.results['server_burst_capacity']
            if capacity < 500:
                issues.append(f"❌ Low server capacity: {capacity:.1f} req/s")
                issues.append("   → Server is the bottleneck, not the client")
            else:
                print(f"✅ Server capacity OK: {capacity:.1f} req/s")
        
        if issues:
            print("\n🔴 ISSUES FOUND:")
            for issue in issues:
                print(issue)
            
            print("\n📋 RECOMMENDATIONS:")
            
            # Specific recommendations based on issues
            if any("base latency" in i for i in issues):
                print("1. Check server processing time:")
                print("   - Profile the transformation code")
                print("   - Add server-side metrics")
                print("   - Consider caching repeated transformations")
            
            if any("connection limit" in i for i in issues):
                print("2. Increase connection limits:")
                print("   - Check server's max connections setting")
                print("   - Verify firewall/proxy settings")
                print("   - Check Azure NSG rules")
            
            if any("concurrency scaling" in i for i in issues):
                print("3. Improve server concurrency:")
                print("   - Increase worker threads/processes")
                print("   - Check for blocking I/O operations")
                print("   - Consider async processing")
            
            if any("network RTT" in i for i in issues):
                print("4. Reduce network latency:")
                print("   - Use same Azure region")
                print("   - Enable accelerated networking")
                print("   - Use private endpoints")
            
            if any("server capacity" in i for i in issues):
                print("5. Scale server resources:")
                print("   - Increase server VM size")
                print("   - Add more server instances")
                print("   - Optimize transformation algorithm")
        else:
            print("\n✅ No major issues found!")
            print("Performance should be good with proper configuration.")
        
        # Save detailed results
        results_file = f"diagnosis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\nDetailed results saved to: {results_file}")

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Performance Diagnostics')
    parser.add_argument('--base-url', default='http://localhost:3000',
                       help='Reframe API base URL')
    
    args = parser.parse_args()
    
    print("="*60)
    print("PERFORMANCE DIAGNOSTICS")
    print("="*60)
    print(f"Target: {args.base_url}")
    print(f"Time: {datetime.now().isoformat()}")
    
    diag = PerformanceDiagnostics(args.base_url)
    
    # Run all tests
    await diag.test_network_latency()
    await diag.test_single_request_latency()
    await diag.test_connection_reuse()
    await diag.test_connection_limits()
    await diag.test_throughput_scaling()
    await diag.test_server_capacity()
    
    # Print diagnosis
    diag.print_diagnosis()

if __name__ == "__main__":
    asyncio.run(main()