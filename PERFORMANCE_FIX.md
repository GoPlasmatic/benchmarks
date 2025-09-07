# Performance Fix Implementation Guide

## Problem Summary
The benchmark was experiencing severe throughput degradation on Azure VMs:
- Throughput dropping from 637 req/s to 82 req/s
- P99 latency increasing from 301ms to 4732ms
- Performance inconsistent between runs

## Root Causes Identified

### 1. **Sequential Batch Processing**
- Original code processed requests in blocking batches
- Single slow request blocked entire batch (convoy effect)

### 2. **Connection Pool Exhaustion**
- Single ClientSession for 100,000+ requests
- Default connection limit of 100 insufficient
- TCP connection state accumulation

### 3. **Missing System Optimizations**
- Default kernel settings too conservative
- File descriptor limits too low
- Network stack not optimized for high concurrency

### 4. **CPU Monitoring Overhead**
- Continuous CPU polling adding overhead
- System-wide CPU monitoring expensive on multi-core VMs

## Solutions Implemented

### 1. Optimized Benchmark Script (`optimized_benchmark.py`)

**Key improvements:**
- **Worker Pool Architecture**: Multiple workers with dedicated connection pools
- **Continuous Request Flow**: Semaphore-based concurrency without blocking
- **Optimized Connections**: Proper timeout and keep-alive settings
- **Reduced Monitoring**: Less frequent, process-specific monitoring

### 2. System Tuning Script (`tune_azure_vm.sh`)

**Optimizations applied:**
- Increased file descriptors to 1M+
- Network stack tuning (somaxconn, TCP buffers)
- CPU governor set to performance mode
- Disk I/O optimizations for SSDs
- Network interface optimizations (TSO/GSO/GRO)

### 3. Docker Deployment (`docker-compose.yml`)

**Container optimizations:**
- Resource limits and reservations
- Sysctls for network performance
- Ulimit configurations
- Health checks and dependencies

### 4. Master Orchestrator (`run_benchmark.py`)

**Features:**
- Automatic test matrix generation
- System optimization application
- Result analysis and recommendations
- Performance assessment

## Usage Instructions

### Quick Start (Azure VM)

1. **SSH to your Azure VM:**
```bash
ssh user@your-azure-vm-ip
```

2. **Clone the repository:**
```bash
git clone <repo-url>
cd benchmarks
```

3. **Apply system optimizations:**
```bash
sudo bash infrastructure/scripts/tune_azure_vm.sh 8-core benchmark
```

4. **Install Python dependencies:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install aiohttp psutil tabulate
```

5. **Run optimized benchmark:**
```bash
python3 run_benchmark.py \
  --vm-size 8-core \
  --base-url http://reframe-server:3000 \
  --output-dir results
```

### Docker Deployment

1. **Set environment variables:**
```bash
export ACR_REGISTRY=yourregistry.azurecr.io
export VM_SIZE=8-core
export NUM_REQUESTS=100000
export CONCURRENT_LEVELS=64,128,256,512
```

2. **Start services:**
```bash
cd infrastructure/docker
docker-compose up -d
```

3. **View logs:**
```bash
docker-compose logs -f benchmark
```

### Manual Benchmark Run

```bash
# Direct execution with specific configuration
REFRAME_THREAD_COUNT=8 \
REFRAME_MAX_CONCURRENT_TASKS=32 \
python3 products/reframe/benchmark/optimized_benchmark.py \
  --base-url http://localhost:3000 \
  --vm-size 8-core \
  --num-requests 100000 \
  --concurrent-levels 256
```

## Expected Performance

### After Optimizations (8-core Azure VM)

| Configuration | Throughput | P99 Latency |
|--------------|------------|-------------|
| 4 threads / 32 tasks / 128 concurrent | ~2500 req/s | ~85 ms |
| 8 threads / 32 tasks / 256 concurrent | ~3500 req/s | ~95 ms |
| 8 threads / 64 tasks / 256 concurrent | ~4000 req/s | ~110 ms |

### Performance Metrics to Monitor

1. **Throughput**: Should remain stable across runs
2. **P99 Latency**: Should stay below 150ms under load
3. **CPU Usage**: Should be 60-80% (not maxed out)
4. **Connection Count**: Monitor with `netstat -an | grep ESTABLISHED | wc -l`

## Troubleshooting

### Issue: Low throughput despite optimizations

**Check:**
1. Accelerated networking enabled: `lspci | grep Mellanox`
2. System limits applied: `ulimit -n` (should show 1048576)
3. Network connectivity: `ping -c 10 reframe-server`
4. Server health: `curl http://reframe-server:3000/health`

### Issue: High latency spikes

**Check:**
1. CPU throttling: `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`
2. Memory pressure: `free -h`
3. Disk I/O: `iotop`
4. Network saturation: `iftop`

### Issue: Connection errors

**Check:**
1. Port exhaustion: `netstat -an | grep TIME_WAIT | wc -l`
2. Connection limit: `sysctl net.core.somaxconn`
3. File descriptors: `cat /proc/sys/fs/file-nr`

## Monitoring Commands

```bash
# Real-time performance
htop

# Network connections
watch -n 1 'netstat -an | grep ESTABLISHED | wc -l'

# TCP statistics
watch -n 1 'ss -s'

# Network traffic
iftop -i eth0

# Disk I/O
iotop

# System statistics
vmstat 1
```

## Recommended Azure VM Configuration

### For Production Benchmarks

- **VM Size**: Standard_D8s_v5 or larger
- **Accelerated Networking**: Enabled
- **Premium SSD**: For OS and data
- **Proximity Placement Group**: For multi-VM setups
- **Availability Zone**: Same zone for all VMs

### Network Security Group Rules

```bash
# Allow benchmark traffic
Inbound: TCP 3000 (Reframe API)
Outbound: All traffic allowed
```

## Next Steps

1. **Validate Fix**: Run benchmark multiple times to ensure consistent performance
2. **Scale Testing**: Test with larger VM sizes (16-core, 32-core)
3. **Multi-Region**: Test across different Azure regions
4. **Load Balancing**: Implement Azure Load Balancer for multiple Reframe instances
5. **Monitoring**: Set up Azure Monitor for continuous performance tracking

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Azure VM logs: `sudo journalctl -xe`
3. Analyze benchmark output files in `results/` directory
4. Contact the team with performance reports