#!/bin/bash
# installer.sh - Complete setup for BBH-AI multi-agent framework
# Run as root: sudo ./installer.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
print_status() { echo -e "${BLUE}[*]${NC} $1"; }
print_success() { echo -e "${GREEN}[+]${NC} $1"; }
print_error() { echo -e "${RED}[!]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root (use sudo)."
    exit 1
fi

if [[ ! -f "config.yaml" ]]; then
    print_error "Please run this script from the project root directory (where config.yaml is located)."
    exit 1
fi

print_status "Checking package lists (skipping if updated in last 24h)..."
APT_CACHE_TIME=86400
LAST_UPDATE=$(stat -c %Y /var/lib/apt/periodic/update-success-stamp 2>/dev/null || echo 0)
NOW=$(date +%s)

if (( NOW - LAST_UPDATE > APT_CACHE_TIME )); then
    print_status "Updating package lists..."
    apt-get update -yqq && apt-get upgrade -yqq
else
    print_success "Package lists are current (updated within last 24h)."
fi

print_status "Installing system dependencies..."
apt-get install -yqq git curl wget make gcc libpcap-dev libssl-dev python3 python3-pip \
               python3-venv jq parallel nmap masscan dnsutils unzip docker.io redis-server
systemctl enable redis-server --now

if ! command -v go &> /dev/null; then
    print_status "Installing Go..."
    GO_VERSION="1.21.5"
    wget "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"
    tar -C /usr/local -xzf "go${GO_VERSION}.linux-amd64.tar.gz"
    rm "go${GO_VERSION}.linux-amd64.tar.gz"
    export PATH=$PATH:/usr/local/go/bin
    echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile
else
    print_success "Go already installed."
fi

export PATH=$PATH:~/go/bin
if ! grep -q '~/go/bin' ~/.bashrc; then
    echo 'export PATH=$PATH:~/go/bin' >> ~/.bashrc
fi

print_status "Installing/updating Go tools..."
go clean -modcache || true
tools=(
    "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
    "github.com/projectdiscovery/httpx/cmd/httpx@latest"
    "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
    "github.com/projectdiscovery/katana/cmd/katana@latest"
    "github.com/tomnomnom/assetfinder@latest"
    "github.com/tomnomnom/gf@latest"
    "github.com/lc/gau/v2/cmd/gau@latest"
    "github.com/hahwul/dalfox/v2@latest"
    "github.com/jaeles-project/gospider@latest"
    "github.com/owasp-amass/amass/v4/...@latest"
    "github.com/intigriti/misconfig-mapper/cmd/misconfig-mapper@latest"
    "github.com/ffuf/ffuf@latest"
)
for tool in "${tools[@]}"; do
    go install -v "$tool" &
done
wait
print_success "Go tools installed."

if ! command -v findomain &> /dev/null; then
    print_status "Installing findomain..."
    wget -q https://github.com/Findomain/Findomain/releases/download/9.0.0/findomain-linux.zip
    unzip -q findomain-linux.zip && chmod +x findomain && mv findomain /usr/local/bin/ && rm findomain-linux.zip
fi

if [[ ! -d /opt/Sublist3r ]]; then
    print_status "Installing Sublist3r..."
    git clone https://github.com/aboul3la/Sublist3r.git /opt/Sublist3r
    pip3 install -q -r /opt/Sublist3r/requirements.txt
    ln -sf /opt/Sublist3r/sublist3r.py /usr/local/bin/sublist3r
fi

if [[ ! -d /opt/waymore ]]; then
    print_status "Installing waymore..."
    git clone https://github.com/xnl-h4ck3r/waymore.git /opt/waymore
    cd /opt/waymore && pip3 install .
    ln -sf $(which waymore) /usr/local/bin/waymore || true
fi

if [[ ! -d /opt/NucleiFuzzer ]]; then
    print_status "Installing NucleiFuzzer..."
    git clone https://github.com/0xKayala/NucleiFuzzer.git /opt/NucleiFuzzer
    cd /opt/NucleiFuzzer && chmod +x install.sh && ./install.sh
    ln -sf /usr/local/bin/nf /usr/bin/nf 2>/dev/null || true
fi

print_status "Setting up gf patterns..."
mkdir -p ~/.gf
if [[ ! -d /tmp/gf ]]; then
    git clone https://github.com/tomnomnom/gf.git /tmp/gf
    cp /tmp/gf/examples/*.json ~/.gf/ 2>/dev/null || true
fi
if [[ ! -d /tmp/Gf-Patterns ]]; then
    git clone https://github.com/1ndianl33t/Gf-Patterns /tmp/Gf-Patterns
    cp /tmp/Gf-Patterns/*.json ~/.gf/ 2>/dev/null || true
fi
rm -rf /tmp/gf /tmp/Gf-Patterns

systemctl enable docker --now

if [[ -f sandbox/Dockerfile.sandbox ]]; then
    print_status "Building sandbox Docker image..."
    # Attempt to fix Docker DNS/IPv6 issues if pull fails
    if ! docker pull python:3.11-slim --quiet &>/dev/null; then
        print_status "Initial Docker pull failed. Attempting to configure DNS fallback..."
        mkdir -p /etc/docker
        echo '{"dns": ["8.8.8.8", "1.1.1.1"]}' > /etc/docker/daemon.json
        systemctl restart docker
    fi
    docker build --network=host -t bbh-sandbox -f sandbox/Dockerfile.sandbox .
else
    print_warning "sandbox/Dockerfile.sandbox not found. Skipping Docker image build."
fi

print_status "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt
else
    print_warning "requirements.txt not found. Skipping Python dependencies."
fi

print_success "Installation complete!"
print_status "Activate the virtual environment with: source venv/bin/activate"