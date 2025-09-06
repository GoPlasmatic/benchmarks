#!/usr/bin/env python3
"""
Generate comprehensive benchmark comparison report from test results.
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pandas as pd
from jinja2 import Template

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reframe Benchmark Report - {{ timestamp }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .summary-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary-card h3 {
            margin-top: 0;
            color: #7f8c8d;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .summary-value {
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }
        .summary-unit {
            font-size: 14px;
            color: #7f8c8d;
        }
        table {
            width: 100%;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        th {
            background: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 500;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .best-value {
            background: #d4edda;
            font-weight: bold;
        }
        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .recommendations {
            background: #e8f4fd;
            border-left: 4px solid #3498db;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 30px;
        }
        .recommendations h3 {
            margin-top: 0;
            color: #2980b9;
        }
        .vm-comparison {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .vm-card {
            background: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .vm-card.best {
            border: 2px solid #27ae60;
            background: #eafaf1;
        }
        .metric-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            margin: 2px;
        }
        .metric-good {
            background: #d4edda;
            color: #155724;
        }
        .metric-warning {
            background: #fff3cd;
            color: #856404;
        }
        .metric-bad {
            background: #f8d7da;
            color: #721c24;
        }
        footer {
            text-align: center;
            color: #7f8c8d;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Reframe Performance Benchmark Report</h1>
        <p><strong>Generated:</strong> {{ timestamp }}</p>
        <p><strong>Total Tests:</strong> {{ total_tests }}</p>
        <p><strong>VM Configurations Tested:</strong> {{ vm_sizes|join(', ') }}</p>
    </div>

    <div class="summary-grid">
        <div class="summary-card">
            <h3>Best Throughput</h3>
            <div class="summary-value">{{ best_throughput.value|round(1) }}</div>
            <div class="summary-unit">requests/second</div>
            <div style="margin-top: 10px; color: #7f8c8d;">
                {{ best_throughput.config }}
            </div>
        </div>
        <div class="summary-card">
            <h3>Best P99 Latency</h3>
            <div class="summary-value">{{ best_latency.value|round(1) }}</div>
            <div class="summary-unit">milliseconds</div>
            <div style="margin-top: 10px; color: #7f8c8d;">
                {{ best_latency.config }}
            </div>
        </div>
        <div class="summary-card">
            <h3>Lowest CPU Usage</h3>
            <div class="summary-value">{{ best_cpu.value|round(1) }}</div>
            <div class="summary-unit">% average</div>
            <div style="margin-top: 10px; color: #7f8c8d;">
                {{ best_cpu.config }}
            </div>
        </div>
        <div class="summary-card">
            <h3>Best Overall</h3>
            <div class="summary-value">{{ best_overall.vm_size }}</div>
            <div class="summary-unit">VM Configuration</div>
            <div style="margin-top: 10px; color: #7f8c8d;">
                Score: {{ best_overall.score|round(2) }}
            </div>
        </div>
    </div>

    <div class="recommendations">
        <h3>📊 Key Findings & Recommendations</h3>
        <ul>
            {% for rec in recommendations %}
            <li>{{ rec }}</li>
            {% endfor %}
        </ul>
    </div>

    <h2>VM Size Comparison</h2>
    <div class="vm-comparison">
        {% for vm in vm_comparisons %}
        <div class="vm-card {% if vm.is_best %}best{% endif %}">
            <h3>{{ vm.name }}</h3>
            <p><strong>{{ vm.vcpus }} vCPUs</strong> / {{ vm.memory_gb }}GB RAM</p>
            <p>Avg Throughput: <strong>{{ vm.avg_throughput|round(1) }}</strong> req/s</p>
            <p>Avg P99: <strong>{{ vm.avg_p99|round(1) }}</strong> ms</p>
            <p>Avg CPU: <strong>{{ vm.avg_cpu|round(1) }}</strong>%</p>
            {% if vm.is_best %}
            <p style="color: #27ae60; font-weight: bold;">✓ Best Overall</p>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <h2>Detailed Test Results</h2>
    <table>
        <thead>
            <tr>
                <th>VM Size</th>
                <th>Threads</th>
                <th>Max Tasks</th>
                <th>Concurrent</th>
                <th>Throughput (req/s)</th>
                <th>Avg CPU (%)</th>
                <th>Peak CPU (%)</th>
                <th>Min Latency (ms)</th>
                <th>Avg Latency (ms)</th>
                <th>P95 Latency (ms)</th>
                <th>P99 Latency (ms)</th>
                <th>Max Latency (ms)</th>
            </tr>
        </thead>
        <tbody>
            {% for result in detailed_results %}
            <tr>
                <td>{{ result.vm_size }}</td>
                <td>{{ result.thread_count }}</td>
                <td>{{ result.max_concurrent_tasks }}</td>
                <td>{{ result.concurrent_requests }}</td>
                <td class="{% if result.is_best_throughput %}best-value{% endif %}">
                    {{ result.throughput|round(1) }}
                </td>
                <td>{{ result.avg_cpu|round(1) }}</td>
                <td>{{ result.peak_cpu|round(1) }}</td>
                <td>{{ result.min_latency|round(1) }}</td>
                <td>{{ result.avg_latency|round(1) }}</td>
                <td>{{ result.p95_latency|round(1) }}</td>
                <td class="{% if result.is_best_p99 %}best-value{% endif %}">
                    {{ result.p99_latency|round(1) }}
                </td>
                <td>{{ result.max_latency|round(1) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Performance by Configuration</h2>
    <div class="chart-container">
        <h3>Thread Count Impact</h3>
        <table>
            <thead>
                <tr>
                    <th>VM Size</th>
                    <th>Configuration</th>
                    <th>Avg Throughput</th>
                    <th>Avg P99 Latency</th>
                    <th>Efficiency Score</th>
                </tr>
            </thead>
            <tbody>
                {% for config in configuration_analysis %}
                <tr>
                    <td>{{ config.vm_size }}</td>
                    <td>{{ config.threads }} threads / {{ config.max_tasks }} tasks</td>
                    <td>{{ config.avg_throughput|round(1) }} req/s</td>
                    <td>{{ config.avg_p99|round(1) }} ms</td>
                    <td>
                        <span class="metric-badge {% if config.efficiency > 80 %}metric-good{% elif config.efficiency > 60 %}metric-warning{% else %}metric-bad{% endif %}">
                            {{ config.efficiency|round(1) }}%
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <h2>Cost-Performance Analysis</h2>
    <table>
        <thead>
            <tr>
                <th>VM Size</th>
                <th>Azure SKU</th>
                <th>Est. Cost/Hour</th>
                <th>Avg Throughput</th>
                <th>Cost per 1M Requests</th>
                <th>Value Score</th>
            </tr>
        </thead>
        <tbody>
            {% for vm in cost_analysis %}
            <tr>
                <td>{{ vm.name }}</td>
                <td>{{ vm.sku }}</td>
                <td>${{ vm.cost_per_hour|round(3) }}</td>
                <td>{{ vm.avg_throughput|round(1) }} req/s</td>
                <td>${{ vm.cost_per_million|round(2) }}</td>
                <td>
                    <span class="metric-badge {% if vm.value_score > 80 %}metric-good{% elif vm.value_score > 60 %}metric-warning{% else %}metric-bad{% endif %}">
                        {{ vm.value_score|round(1) }}
                    </span>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <footer>
        <p>Generated by Plasmatic Benchmark Suite | {{ timestamp }}</p>
    </footer>
</body>
</html>
"""

def load_results(results_dir: Path) -> Dict:
    """Load all benchmark results from directory"""
    all_results = []
    vm_configs = {}
    
    # Find all result files
    for vm_dir in results_dir.glob('*'):
        if vm_dir.is_dir() and 'core' in vm_dir.name:
            vm_size = vm_dir.name
            
            # Load VM configuration
            config_file = Path(f'infrastructure/azure/vm-configs/{vm_size}.json')
            if config_file.exists():
                with open(config_file) as f:
                    vm_configs[vm_size] = json.load(f)
            
            # Load aggregated results
            for result_file in vm_dir.glob('aggregated_results_*.json'):
                with open(result_file) as f:
                    data = json.load(f)
                    for result in data.get('results', []):
                        result['vm_size'] = vm_size
                        all_results.append(result)
    
    return {
        'results': all_results,
        'vm_configs': vm_configs
    }

def analyze_results(data: Dict) -> Dict:
    """Analyze benchmark results and generate insights"""
    results = data['results']
    vm_configs = data['vm_configs']
    
    if not results:
        return {}
    
    # Find best configurations
    best_throughput = max(results, key=lambda x: x['performance']['throughput'])
    best_latency = min(results, key=lambda x: x['latency']['p99'])
    best_cpu = min(results, key=lambda x: x['resources']['avg_cpu'])
    
    # Calculate VM comparisons
    vm_comparisons = []
    for vm_size, config in vm_configs.items():
        vm_results = [r for r in results if r.get('vm_size') == vm_size]
        if vm_results:
            avg_throughput = sum(r['performance']['throughput'] for r in vm_results) / len(vm_results)
            avg_p99 = sum(r['latency']['p99'] for r in vm_results) / len(vm_results)
            avg_cpu = sum(r['resources']['avg_cpu'] for r in vm_results) / len(vm_results)
            
            # Calculate efficiency score (throughput per CPU %)
            efficiency = (avg_throughput / avg_cpu) if avg_cpu > 0 else 0
            
            vm_comparisons.append({
                'name': vm_size,
                'vcpus': config['vcpus'],
                'memory_gb': config['memory_gb'],
                'avg_throughput': avg_throughput,
                'avg_p99': avg_p99,
                'avg_cpu': avg_cpu,
                'efficiency': efficiency,
                'score': (avg_throughput / 1000) * (100 / avg_p99) * (100 / avg_cpu)
            })
    
    # Find best overall VM
    if vm_comparisons:
        best_overall = max(vm_comparisons, key=lambda x: x['score'])
        best_overall['is_best'] = True
    else:
        best_overall = {'vm_size': 'N/A', 'score': 0}
    
    # Generate recommendations
    recommendations = []
    
    # Throughput analysis
    if best_throughput['performance']['throughput'] > 5000:
        recommendations.append(f"Excellent throughput achieved: {best_throughput['performance']['throughput']:.0f} req/s with {best_throughput['config']['thread_count']} threads")
    
    # Latency analysis
    if best_latency['latency']['p99'] < 50:
        recommendations.append(f"Excellent P99 latency: {best_latency['latency']['p99']:.1f}ms achieved with {best_latency['config']['concurrent_requests']} concurrent requests")
    
    # CPU efficiency
    if vm_comparisons:
        most_efficient = max(vm_comparisons, key=lambda x: x['efficiency'])
        recommendations.append(f"Most CPU-efficient: {most_efficient['name']} with {most_efficient['efficiency']:.1f} req/s per CPU%")
    
    # Scaling analysis
    if len(vm_configs) >= 2:
        sorted_vms = sorted(vm_comparisons, key=lambda x: x['vcpus'])
        if len(sorted_vms) >= 2:
            scaling_factor = sorted_vms[-1]['avg_throughput'] / sorted_vms[0]['avg_throughput']
            cpu_factor = sorted_vms[-1]['vcpus'] / sorted_vms[0]['vcpus']
            scaling_efficiency = (scaling_factor / cpu_factor) * 100
            recommendations.append(f"Scaling efficiency: {scaling_efficiency:.0f}% when scaling from {sorted_vms[0]['vcpus']} to {sorted_vms[-1]['vcpus']} vCPUs")
    
    # Configuration analysis
    config_analysis = []
    for vm_size in vm_configs.keys():
        vm_results = [r for r in results if r.get('vm_size') == vm_size]
        configs = {}
        for r in vm_results:
            key = f"{r['config']['thread_count']}-{r['config']['max_concurrent_tasks']}"
            if key not in configs:
                configs[key] = []
            configs[key].append(r)
        
        for key, config_results in configs.items():
            threads, max_tasks = key.split('-')
            avg_throughput = sum(r['performance']['throughput'] for r in config_results) / len(config_results)
            avg_p99 = sum(r['latency']['p99'] for r in config_results) / len(config_results)
            avg_cpu = sum(r['resources']['avg_cpu'] for r in config_results) / len(config_results)
            
            config_analysis.append({
                'vm_size': vm_size,
                'threads': int(threads),
                'max_tasks': int(max_tasks),
                'avg_throughput': avg_throughput,
                'avg_p99': avg_p99,
                'efficiency': (avg_throughput / avg_cpu) if avg_cpu > 0 else 0
            })
    
    # Cost analysis (estimated Azure pricing)
    cost_per_hour = {
        '2-core': 0.016,   # Standard_B2s
        '4-core': 0.166,   # Standard_D4s_v3
        '8-core': 0.333,   # Standard_D8s_v3
        '16-core': 0.666   # Standard_D16s_v3
    }
    
    cost_analysis = []
    for vm in vm_comparisons:
        cost = cost_per_hour.get(vm['name'], 0)
        if cost > 0 and vm['avg_throughput'] > 0:
            cost_per_million = (cost / (vm['avg_throughput'] * 3600)) * 1000000
            value_score = (vm['avg_throughput'] / cost) / 10000  # Normalized score
            
            cost_analysis.append({
                'name': vm['name'],
                'sku': vm_configs[vm['name']]['azure_sku'],
                'cost_per_hour': cost,
                'avg_throughput': vm['avg_throughput'],
                'cost_per_million': cost_per_million,
                'value_score': min(100, value_score)
            })
    
    # Prepare detailed results table
    detailed_results = []
    for r in results:
        detailed_results.append({
            'vm_size': r.get('vm_size', 'unknown'),
            'thread_count': r['config']['thread_count'],
            'max_concurrent_tasks': r['config']['max_concurrent_tasks'],
            'concurrent_requests': r['config']['concurrent_requests'],
            'throughput': r['performance']['throughput'],
            'avg_cpu': r['resources']['avg_cpu'],
            'peak_cpu': r['resources']['peak_cpu'],
            'min_latency': r['latency']['min'],
            'avg_latency': r['latency']['avg'],
            'p95_latency': r['latency']['p95'],
            'p99_latency': r['latency']['p99'],
            'max_latency': r['latency']['max'],
            'is_best_throughput': r == best_throughput,
            'is_best_p99': r == best_latency
        })
    
    return {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_tests': len(results),
        'vm_sizes': list(vm_configs.keys()),
        'best_throughput': {
            'value': best_throughput['performance']['throughput'],
            'config': f"{best_throughput.get('vm_size', 'unknown')} - {best_throughput['config']['thread_count']} threads"
        },
        'best_latency': {
            'value': best_latency['latency']['p99'],
            'config': f"{best_latency.get('vm_size', 'unknown')} - {best_latency['config']['concurrent_requests']} concurrent"
        },
        'best_cpu': {
            'value': best_cpu['resources']['avg_cpu'],
            'config': f"{best_cpu.get('vm_size', 'unknown')} - {best_cpu['config']['thread_count']} threads"
        },
        'best_overall': best_overall,
        'recommendations': recommendations,
        'vm_comparisons': vm_comparisons,
        'configuration_analysis': config_analysis,
        'cost_analysis': cost_analysis,
        'detailed_results': detailed_results
    }

def generate_html_report(analysis: Dict, output_file: Path):
    """Generate HTML report from analysis"""
    template = Template(HTML_TEMPLATE)
    html_content = template.render(**analysis)
    
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"Report generated: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Generate benchmark comparison report')
    parser.add_argument('--results-dir', required=True, help='Directory containing benchmark results')
    parser.add_argument('--output-file', required=True, help='Output HTML file path')
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return 1
    
    # Load and analyze results
    print("Loading benchmark results...")
    data = load_results(results_dir)
    
    if not data.get('results'):
        print("Warning: No results found in directory")
        # Generate empty report
        analysis = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_tests': 0,
            'vm_sizes': [],
            'best_throughput': {'value': 0, 'config': 'N/A'},
            'best_latency': {'value': 0, 'config': 'N/A'},
            'best_cpu': {'value': 0, 'config': 'N/A'},
            'best_overall': {'vm_size': 'N/A', 'score': 0},
            'recommendations': ['No benchmark data available'],
            'vm_comparisons': [],
            'configuration_analysis': [],
            'cost_analysis': [],
            'detailed_results': []
        }
    else:
        print(f"Analyzing {len(data['results'])} test results...")
        analysis = analyze_results(data)
    
    # Generate report
    output_file = Path(args.output_file)
    generate_html_report(analysis, output_file)
    
    return 0

if __name__ == "__main__":
    exit(main())