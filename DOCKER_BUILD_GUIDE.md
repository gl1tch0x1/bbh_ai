# 🐳 BBH-AI Docker Build Guide

## Overview
This guide covers building the BBH-AI sandbox Docker image (`bbh-ai-unified`) and troubleshooting common issues.

---

## 🌐 Network Issues?

If you're experiencing timeouts or connection errors, see:
→ [NETWORK_TROUBLESHOOTING.md](NETWORK_TROUBLESHOOTING.md)

Key fixes:
- Use Google DNS: `8.8.8.8`
- Configure Docker daemon: `/etc/docker/daemon.json`
- Test connectivity: `ping 8.8.8.8 && docker pull hello-world`
- Run diagnostics: `python rebuild_docker.py` (now includes network checks!)

---

## 🔍 Quick Diagnostics

The new `rebuild_docker.py` script automatically checks:

### ❌ Go Module Timeout Error

**Symptom:**
```
error: github.com/projectdiscovery/urlfinder@v0.0.3: verifying module: 
Get "https://sum.golang.org/lookup/...": dial tcp: i/o timeout
```

**Root Cause:**
- Network timeout when Go tries to verify checksums from `sum.golang.org`
- Occurs when using `@latest` which forces re-verification

**✅ Solution (Already Applied):**
1. **Pinned versions** - Specific versions instead of `@latest` avoid re-verification
2. **GOSUMDB=off** - Bypasses checksum verification server
3. **Retry logic** - Automatic retries with 10-second delays
4. **Batch optimization** - Tools split into groups for isolation

The Dockerfile now includes:
```dockerfile
ENV GOPROXY=direct GOSUMDB=off CGO_ENABLED=0
RUN set -e; \
    for i in 1 2 3; do \
        go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@v3.0.0 ...
    done
```

### ❌ Build Timeout (Long-Running Builds)

**Symptom:**
```
Build context takes >30 minutes, Docker timeout
```

**Solutions:**
```bash
# For Docker Desktop, increase timeout in build command:
docker build \
  -f sandbox/Dockerfile.sandbox \
  -t bbh-ai-unified \
  --progress=plain \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  .

# Or use BuildKit with longer timeout
DOCKER_BUILDKIT=1 docker build \
  -f sandbox/Dockerfile.sandbox \
  -t bbh-ai-unified \
  .
```

### ❌ Out of Disk Space

**Symptom:**
```
ERROR: failed to solve: failed to compute cache key: 
failed to calculate checksum of ref type: insufficient space
```

**Solutions:**
```bash
# Clean up Docker images and build cache
docker system prune -a --volumes

# Build with limited cache
docker build --no-cache -f sandbox/Dockerfile.sandbox -t bbh-ai-unified .
```

### ❌ Network Connectivity Issues (Behind Proxy)

**Solution:**
```dockerfile
# Add to Dockerfile before Go installations:
RUN git config --global url."https://".insteadOf git://

# Pass proxy settings during build:
docker build \
  --build-arg HTTP_PROXY=http://proxy:8080 \
  --build-arg HTTPS_PROXY=https://proxy:8080 \
  -f sandbox/Dockerfile.sandbox \
  -t bbh-ai-unified \
  .
```

---

## Verification

After successful build, verify tools are installed:

```bash
# Start sandbox container
docker run --rm bbh-ai-unified bash -c "nuclei -version && dnsx -version && subfinder -version"

# Expected output:
# nuclei 3.0.0
# dnsx 1.1.6
# subfinder 2.6.3
```

---

## Development Workflow

### Rebuild with Cache
```bash
# Fast rebuild (uses cache layers)
python rebuild_docker.py
```

### Rebuild from Scratch
```bash
docker build --no-cache -f sandbox/Dockerfile.sandbox -t bbh-ai-unified .
```

### Debug Build Step-by-Step
```bash
# Add shell to Dockerfile for interactive debugging
docker run -it bbh-ai-unified bash

# Check Go tools
ls -la /root/go/bin/

# Verify Python tools
pip list
```

---

## Optimization Tips

1. **Cache Efficiency**: Keep heavy builds (apt, Go) before lighter ones
2. **Layer Size**: Remove `/var/lib/apt/lists/*` to reduce layer bloat
3. **Multi-Stage Build**: Consider separating builder and runtime stages for prod
4. **Alpine Base** (Optional): Use `python:3.11-alpine` for smaller images (trade-off: slower builds)

---

## Pinned Tool Versions

Current versions in Dockerfile:
- **nuclei** v3.0.0
- **dnsx** v1.1.6
- **tlsx** v1.1.6
- **subfinder** v2.6.3
- **puredns** v2.2.2
- **dsieve** v1.0.5
- **misconfig-mapper** v0.1.3
- **gotator** v1.3
- **interactsh-client** v1.1.4

Update versions in [sandbox/Dockerfile.sandbox](sandbox/Dockerfile.sandbox) as needed.

---

## See Also
- [README.md](README.md) - Main documentation
- [sandbox/Dockerfile.sandbox](sandbox/Dockerfile.sandbox) - Full Dockerfile
- [rebuild_docker.py](rebuild_docker.py) - Build automation script
