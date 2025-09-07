#!/bin/bash

# Configure Reframe server for high-performance benchmarking
# This script optimizes the Node.js/Reframe server configuration

set -e

echo "========================================"
echo "Reframe Server Performance Configuration"
echo "========================================"

# Get VM size from argument
VM_SIZE="${1:-8-core}"

# Set configuration based on VM size
case "$VM_SIZE" in
    "2-core")
        THREAD_COUNT=4
        MAX_CONCURRENT_TASKS=16
        WORKER_POOL_SIZE=8
        UV_THREADPOOL_SIZE=16
        NODE_MAX_MEMORY=2048
        PM2_INSTANCES=2
        ;;
    "4-core")
        THREAD_COUNT=8
        MAX_CONCURRENT_TASKS=32
        WORKER_POOL_SIZE=16
        UV_THREADPOOL_SIZE=32
        NODE_MAX_MEMORY=4096
        PM2_INSTANCES=4
        ;;
    "8-core")
        THREAD_COUNT=16
        MAX_CONCURRENT_TASKS=64
        WORKER_POOL_SIZE=32
        UV_THREADPOOL_SIZE=64
        NODE_MAX_MEMORY=8192
        PM2_INSTANCES=8
        ;;
    "16-core")
        THREAD_COUNT=32
        MAX_CONCURRENT_TASKS=128
        WORKER_POOL_SIZE=64
        UV_THREADPOOL_SIZE=128
        NODE_MAX_MEMORY=16384
        PM2_INSTANCES=16
        ;;
    *)
        echo "Unknown VM size: $VM_SIZE"
        exit 1
        ;;
esac

echo "Configuration for $VM_SIZE VM:"
echo "  Thread Count: $THREAD_COUNT"
echo "  Max Concurrent Tasks: $MAX_CONCURRENT_TASKS"
echo "  Worker Pool Size: $WORKER_POOL_SIZE"
echo "  UV Thread Pool: $UV_THREADPOOL_SIZE"
echo "  Node Memory: $NODE_MAX_MEMORY MB"
echo "  PM2 Instances: $PM2_INSTANCES"
echo ""

# Create systemd service file for Reframe
create_systemd_service() {
    echo "Creating systemd service..."
    
    cat <<EOF | sudo tee /etc/systemd/system/reframe.service > /dev/null
[Unit]
Description=Reframe API Server
After=network.target

[Service]
Type=simple
User=reframe
WorkingDirectory=/opt/reframe
ExecStart=/usr/bin/node --max-old-space-size=$NODE_MAX_MEMORY server.js
Restart=always
RestartSec=10

# Environment variables
Environment="NODE_ENV=production"
Environment="REFRAME_THREAD_COUNT=$THREAD_COUNT"
Environment="REFRAME_MAX_CONCURRENT_TASKS=$MAX_CONCURRENT_TASKS"
Environment="REFRAME_WORKER_POOL_SIZE=$WORKER_POOL_SIZE"
Environment="UV_THREADPOOL_SIZE=$UV_THREADPOOL_SIZE"
Environment="NODE_OPTIONS=--max-old-space-size=$NODE_MAX_MEMORY"

# Performance settings
LimitNOFILE=1048576
LimitNPROC=32768
TasksMax=infinity

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    echo "✓ Systemd service created"
}

# Create PM2 ecosystem file for clustering
create_pm2_config() {
    echo "Creating PM2 ecosystem config..."
    
    cat <<EOF > /opt/reframe/ecosystem.config.js
module.exports = {
  apps: [{
    name: 'reframe-api',
    script: './server.js',
    instances: $PM2_INSTANCES,
    exec_mode: 'cluster',
    
    // Environment variables
    env: {
      NODE_ENV: 'production',
      REFRAME_THREAD_COUNT: '$THREAD_COUNT',
      REFRAME_MAX_CONCURRENT_TASKS: '$MAX_CONCURRENT_TASKS',
      REFRAME_WORKER_POOL_SIZE: '$WORKER_POOL_SIZE',
      UV_THREADPOOL_SIZE: '$UV_THREADPOOL_SIZE',
    },
    
    // Node.js arguments
    node_args: '--max-old-space-size=$NODE_MAX_MEMORY',
    
    // PM2 specific options
    max_memory_restart: '${NODE_MAX_MEMORY}M',
    min_uptime: '10s',
    max_restarts: 10,
    
    // Logging
    error_file: '/var/log/reframe/error.log',
    out_file: '/var/log/reframe/out.log',
    log_file: '/var/log/reframe/combined.log',
    time: true,
    
    // Advanced options
    kill_timeout: 5000,
    wait_ready: true,
    listen_timeout: 10000,
  }]
};
EOF
    
    echo "✓ PM2 ecosystem config created"
}

# Create Docker run script with optimizations
create_docker_script() {
    echo "Creating Docker run script..."
    
    cat <<EOF > /opt/reframe/run-docker.sh
#!/bin/bash

# Run Reframe in Docker with optimizations

docker run -d \\
  --name reframe-api \\
  --restart unless-stopped \\
  --network host \\
  --cpus="$((VM_SIZE))" \\
  --memory="${NODE_MAX_MEMORY}m" \\
  --ulimit nofile=1048576:1048576 \\
  --ulimit nproc=32768:32768 \\
  --sysctl net.core.somaxconn=65535 \\
  --sysctl net.ipv4.tcp_max_syn_backlog=65535 \\
  --sysctl net.ipv4.tcp_tw_reuse=1 \\
  -e NODE_ENV=production \\
  -e REFRAME_THREAD_COUNT=$THREAD_COUNT \\
  -e REFRAME_MAX_CONCURRENT_TASKS=$MAX_CONCURRENT_TASKS \\
  -e REFRAME_WORKER_POOL_SIZE=$WORKER_POOL_SIZE \\
  -e UV_THREADPOOL_SIZE=$UV_THREADPOOL_SIZE \\
  -e NODE_OPTIONS="--max-old-space-size=$NODE_MAX_MEMORY" \\
  reframe-api:latest
EOF
    
    chmod +x /opt/reframe/run-docker.sh
    echo "✓ Docker run script created"
}

# Create NGINX load balancer configuration
create_nginx_config() {
    echo "Creating NGINX load balancer config..."
    
    # Generate upstream servers for PM2 instances
    UPSTREAMS=""
    for i in $(seq 0 $((PM2_INSTANCES - 1))); do
        PORT=$((3000 + i))
        UPSTREAMS="$UPSTREAMS    server 127.0.0.1:$PORT max_fails=3 fail_timeout=30s;\n"
    done
    
    cat <<EOF | sudo tee /etc/nginx/sites-available/reframe > /dev/null
upstream reframe_backend {
    least_conn;
$UPSTREAMS
    keepalive 256;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}

server {
    listen 80 default_server reuseport;
    listen [::]:80 default_server reuseport;
    
    server_name _;
    
    # Increase buffer sizes
    client_body_buffer_size 10M;
    client_max_body_size 10M;
    
    # Timeouts
    client_body_timeout 60s;
    client_header_timeout 60s;
    send_timeout 60s;
    
    # Keep-alive
    keepalive_timeout 65s;
    keepalive_requests 1000;
    
    # Proxy settings
    location / {
        proxy_pass http://reframe_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        
        # Timeouts
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffering
        proxy_buffering off;
        proxy_request_buffering off;
        
        # Keep-alive
        proxy_socket_keepalive on;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://reframe_backend/health;
        access_log off;
    }
}
EOF
    
    sudo ln -sf /etc/nginx/sites-available/reframe /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    
    echo "✓ NGINX load balancer configured"
}

# Apply Node.js specific optimizations
optimize_nodejs() {
    echo "Applying Node.js optimizations..."
    
    # Create Node.js optimization script
    cat <<EOF > /opt/reframe/optimize.js
// Node.js performance optimizations
const cluster = require('cluster');
const os = require('os');

// Increase default limits
require('events').EventEmitter.defaultMaxListeners = 100;

// Enable HTTP keep-alive globally
const http = require('http');
http.globalAgent.keepAlive = true;
http.globalAgent.keepAliveMsecs = 60000;
http.globalAgent.maxSockets = Infinity;
http.globalAgent.maxFreeSockets = 256;

// Optimize garbage collection
if (global.gc) {
  // Run GC periodically if exposed
  setInterval(() => {
    global.gc();
  }, 60000);
}

// Export optimization function
module.exports = function optimizeServer(server) {
  // Set server timeouts
  server.timeout = 60000;
  server.keepAliveTimeout = 65000;
  server.headersTimeout = 66000;
  
  // Increase max connections
  server.maxConnections = 10000;
  
  // Enable TCP no delay
  server.on('connection', (socket) => {
    socket.setNoDelay(true);
    socket.setKeepAlive(true, 60000);
  });
  
  return server;
};
EOF
    
    echo "✓ Node.js optimizations created"
}

# Check current Reframe server status
check_server_status() {
    echo ""
    echo "Checking server status..."
    
    # Check if running with systemd
    if systemctl is-active --quiet reframe; then
        echo "✓ Reframe is running (systemd)"
        systemctl status reframe --no-pager | head -10
    # Check if running with PM2
    elif pm2 list | grep -q reframe; then
        echo "✓ Reframe is running (PM2)"
        pm2 show reframe-api
    # Check if running with Docker
    elif docker ps | grep -q reframe; then
        echo "✓ Reframe is running (Docker)"
        docker stats --no-stream reframe-api
    else
        echo "⚠ Reframe is not running"
    fi
}

# Main execution
main() {
    echo "Starting Reframe server configuration..."
    
    # Create directories
    sudo mkdir -p /opt/reframe /var/log/reframe
    
    # Create configurations
    create_systemd_service
    create_pm2_config
    create_docker_script
    optimize_nodejs
    
    # Install and configure NGINX if available
    if command -v nginx &> /dev/null; then
        create_nginx_config
    else
        echo "⚠ NGINX not installed. Skipping load balancer setup."
        echo "  Install with: sudo apt-get install nginx"
    fi
    
    # Check current status
    check_server_status
    
    echo ""
    echo "========================================"
    echo "✅ Configuration Complete!"
    echo "========================================"
    echo ""
    echo "To start Reframe with optimizations:"
    echo ""
    echo "Option 1 - PM2 (Recommended for production):"
    echo "  cd /opt/reframe"
    echo "  pm2 start ecosystem.config.js"
    echo "  pm2 save"
    echo "  pm2 startup"
    echo ""
    echo "Option 2 - Systemd:"
    echo "  sudo systemctl start reframe"
    echo "  sudo systemctl enable reframe"
    echo ""
    echo "Option 3 - Docker:"
    echo "  /opt/reframe/run-docker.sh"
    echo ""
    echo "To verify performance:"
    echo "  curl http://localhost/health"
    echo "  python3 products/reframe/benchmark/diagnose_performance.py"
}

# Run main function
main