# 🌐 Network Troubleshooting Guide for BBH-AI Docker Build

The Docker build requires internet connectivity to pull the base Python image and install tools. If you're experiencing network timeouts, follow this guide.

---

## 🔍 Quick Diagnostics

Run the enhanced build script which now includes diagnostics:

```bash
python rebuild_docker.py
```

It will automatically check:
1. ✓ Docker daemon status
2. ✓ DNS resolution for registry-1.docker.io
3. ✓ Network connectivity to Docker Hub
4. ✓ Ability to pull test images

---

## 🔴 Common Network Issues & Solutions

### Issue 1: DNS Resolution Timeout
**Error:** `dial tcp: lookup registry-1.docker.io on 192.168.30.2:53: read udp ... i/o timeout`

**Causes:**
- DNS server is unreachable or slow
- Firewall blocking DNS (port 53)
- Misconfigured /etc/resolv.conf

**Solutions:**

**Option A: Use Google DNS (Linux/Mac)**
```bash
# Temporary
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf > /dev/null

# Permanent (Linux)
sudo nano /etc/resolv.conf
# Add line: nameserver 8.8.8.8
```

**Option B: Configure Docker Daemon**
```bash
# Edit Docker daemon config
sudo nano /etc/docker/daemon.json
```

Add:
```json
{
  "dns": ["8.8.8.8", "8.8.4.4"],
  "insecure-registries": []
}
```

Then restart:
```bash
sudo systemctl restart docker
```

**Option C: Use Docker Desktop GUI (Mac/Windows)**
- Open Docker Desktop
- Settings → Resources → Network
- Enable DNS and set to `8.8.8.8`

---

### Issue 2: Connection Timeout (Network Unreachable)
**Error:** `dial tcp: i/o timeout` or connection refused

**Causes:**
- Firewall blocking outbound HTTPS (port 443)
- Proxy required but not configured
- Network interface issues

**Solutions:**

**Option A: Test Connectivity**
```bash
# Test DNS
nslookup registry-1.docker.io
dig registry-1.docker.io

# Test connection
curl -I https://registry-1.docker.io/v2/

# Test with timeout
timeout 5 bash -c 'cat < /dev/null > /dev/tcp/registry-1.docker.io/443'
```

**Option B: If Behind Proxy**
```bash
# Configure Docker to use proxy
sudo nano /etc/systemd/system/docker.service.d/http-proxy.conf
```

Create file with:
```ini
[Service]
Environment="HTTP_PROXY=http://proxy.company.com:8080"
Environment="HTTPS_PROXY=http://proxy.company.com:8080"
Environment="NO_PROXY=localhost,127.0.0.1"
```

Restart Docker:
```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

**Option C: Check Firewall**
```bash
# Linux firewall
sudo ufw status
sudo ufw allow out 443  # Allow outbound HTTPS

# Check iptables
sudo iptables -L -n
```

---

### Issue 3: Docker Hub Registry Unavailable
**Error:** `manifest not found` or `connection refused`

**Causes:**
- Docker Hub is down
- Regional blocking
- Rate limiting

**Solutions:**

**Option A: Use Docker Registry Mirror**
```bash
# Edit daemon.json
sudo nano /etc/docker/daemon.json
```

Add:
```json
{
  "registry-mirrors": [
    "https://mirror.aliyun.com",
    "https://hub-mirror.c.163.com",
    "https://ccr.ccs.tencentyun.com"
  ]
}
```

Then:
```bash
sudo systemctl restart docker
```

**Option B: Check Docker Hub Status**
```bash
# Visit: https://www.dockerstatus.com/
# Or check if Docker Hub is down
curl -s https://registry.hub.docker.com/v2/ -H "Authorization: Bearer temp"
```

---

## 🛠️ Advanced Troubleshooting

### Check Docker Daemon Logs
```bash
# Linux
journalctl -u docker -f

# Mac
log stream --predicate 'process == "dockerd"' --level debug

# Windows
Get-EventLog -LogName Application -Source Docker -Newest 20
```

### Test Docker Hub Connectivity
```bash
# Direct test
docker pull hello-world

# With timeout override
timeout 30 docker pull alpine:latest

# With verbose logging
docker -D pull python:3.11-slim
```

### Check Network Interfaces
```bash
# List interfaces
ip addr show
ifconfig

# Test routing
traceroute registry-1.docker.io
mtr registry-1.docker.io
```

---

## 📦 Offline Build Alternative

If network issues persist, consider these options:

### Option 1: Pre-Pull Base Image
On a machine with good connectivity:
```bash
docker pull python:3.11-slim
# Transfer the image
docker save python:3.11-slim > python-3.11-slim.tar
# Transfer to target machine
docker load < python-3.11-slim.tar
```

### Option 2: Use Local Registry
```bash
# Run local registry
docker run -d -p 5000:5000 registry:2

# Once base image is available locally
docker tag python:3.11-slim localhost:5000/python:3.11-slim
docker push localhost:5000/python:3.11-slim

# Update Dockerfile
FROM localhost:5000/python:3.11-slim
```

### Option 3: Build with Cached Layers
```bash
# First build caches layers even if it fails
python rebuild_docker.py

# After fixing network, retry - it will use cache
python rebuild_docker.py
```

---

## 📋 Verification Checklist

Before retrying the build:

- [ ] Can ping 8.8.8.8: `ping -c 1 8.8.8.8`
- [ ] DNS works: `nslookup registry-1.docker.io`
- [ ] Docker daemon running: `docker ps`
- [ ] Can pull test image: `docker pull alpine:latest`
- [ ] No proxy issues: `docker pull python:3.11-slim`
- [ ] Firewall allows 443: `timeout 5 curl https://registry-1.docker.io/v2/`

---

## 🚀 Retry the Build

Once issues are resolved:

```bash
# Run with diagnostics
python rebuild_docker.py

# Force rebuild without cache
docker build --no-cache -f sandbox/Dockerfile.sandbox -t bbh-ai-unified .

# Or with increased timeout
timeout 3600 docker build -f sandbox/Dockerfile.sandbox -t bbh-ai-unified .
```

---

## 📞 Getting Help

If issues persist:

1. **Check Docker Docs:** https://docs.docker.com/network/
2. **Check Docker Hub Status:** https://www.dockerstatus.com/
3. **See Docker Build Logs:** `docker buildx build --progress=plain ...`
4. **Report Issue:** Include output from:
   ```bash
   docker version
   docker info
   docker inspect <image>
   journalctl -u docker -n 50
   ```

---

## 🎯 Quick Reference

```bash
# Diagnostics
python rebuild_docker.py          # Run enhanced build with auto-diagnostics

# Network tests
ping 8.8.8.8                      # Test internet
nslookup registry-1.docker.io     # Test DNS
docker pull alpine:latest         # Test Docker Hub

# Docker daemon
sudo systemctl status docker      # Check status
sudo systemctl restart docker     # Restart daemon
journalctl -u docker -f           # View logs

# Configuration
sudo nano /etc/docker/daemon.json # Edit settings
docker --version                  # Show version
docker info                        # Show config
```
