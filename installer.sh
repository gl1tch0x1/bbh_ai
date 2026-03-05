#!/bin/bash
# installer.sh - Complete automated setup for BBH-AI multi-agent framework
# This script handles all dependencies, tools, and configurations automatically
# Run as root: sudo ./installer.sh

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
print_status() { echo -e "${BLUE}[*]${NC} $1"; }
print_success() { echo -e "${GREEN}[+]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[!]${NC} $1"; }

# Error handler
error_exit() {
    print_error "$1"
    exit 1
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error_exit "This script must be run as root (use sudo)."
fi

# Check if we're in the project directory
if [[ ! -f "config.yaml" ]] || [[ ! -f "requirements.txt" ]]; then
    error_exit "Please run this script from the BBH-AI project root directory (where config.yaml and requirements.txt are located)."
fi

print_status "BBH-AI Automated Installer Started"
print_status "=================================="

# Function to check command availability
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Go if not present
install_go() {
    if ! command_exists go; then
        print_status "Installing Go programming language..."
        local GO_VERSION="1.21.5"
        local GO_TAR="go${GO_VERSION}.linux-amd64.tar.gz"
        local GO_URL="https://go.dev/dl/${GO_TAR}"
        
        wget -q --show-progress "${GO_URL}" || error_exit "Failed to download Go"
        rm -rf /usr/local/go
        tar -C /usr/local -xzf "${GO_TAR}" || error_exit "Failed to extract Go"
        rm "${GO_TAR}"
        
        # Add Go to PATH
        export PATH=$PATH:/usr/local/go/bin
        echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile
        echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
        
        # Verify installation
        if ! /usr/local/go/bin/go version >/dev/null 2>&1; then
            error_exit "Go installation failed"
        fi
        print_success "Go ${GO_VERSION} installed successfully"
    else
        print_success "Go already installed: $(go version)"
    fi
}

# Function to update system packages
update_system() {
    print_status "Updating system packages..."
    local APT_CACHE_TIME=86400
    local LAST_UPDATE=$(stat -c %Y /var/lib/apt/periodic/update-success-stamp 2>/dev/null || echo 0)
    local NOW=$(date +%s)
    
    if (( NOW - LAST_UPDATE > APT_CACHE_TIME )); then
        apt-get update -yqq || error_exit "Failed to update package lists"
        apt-get upgrade -yqq || error_exit "Failed to upgrade packages"
        print_success "System packages updated"
    else
        print_success "Package lists are current (updated within last 24h)"
    fi
}

# Function to install system dependencies
install_system_deps() {
    print_status "Installing system dependencies..."
    local packages=(
        git curl wget make gcc libpcap-dev libssl-dev
        python3 python3-pip python3-venv python3-dev
        jq parallel nmap masscan dnsutils unzip
        docker.io redis-server postgresql postgresql-contrib
        build-essential libffi-dev libxml2-dev libxslt-dev
    )
    
    apt-get install -yqq "${packages[@]}" || error_exit "Failed to install system packages"
    
    # Enable and start services
    systemctl enable redis-server --now || print_warning "Failed to enable Redis"
    systemctl enable docker --now || print_warning "Failed to enable Docker"
    systemctl enable postgresql --now || print_warning "Failed to enable PostgreSQL"
    
    print_success "System dependencies installed"
}

# Function to install Go tools
install_go_tools() {
    print_status "Installing Go-based security tools..."
    
    # Set Go environment variables
    export PATH=$PATH:/usr/local/go/bin:~/go/bin
    export GOPROXY=direct
    export GOSUMDB=off
    export CGO_ENABLED=0
    
    # Create Go workspace
    mkdir -p ~/go/bin
    
    # Clean module cache to avoid conflicts
    go clean -modcache 2>/dev/null || true
    
    local tools=(
        "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
        "github.com/projectdiscovery/httpx/cmd/httpx@latest"
        "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
        "github.com/projectdiscovery/katana/cmd/katana@latest"
        "github.com/projectdiscovery/dnsx/cmd/dnsx@latest"
        "github.com/projectdiscovery/tlsx/cmd/tlsx@latest"
        "github.com/tomnomnom/assetfinder@latest"
        "github.com/tomnomnom/gf@latest"
        "github.com/lc/gau/v2/cmd/gau@latest"
        "github.com/hahwul/dalfox/v2@latest"
        "github.com/jaeles-project/gospider@latest"
        "github.com/ffuf/ffuf@latest"
        "github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest"
    )
    
    local failed_tools=()
    
    for tool in "${tools[@]}"; do
        print_status "Installing ${tool}..."
        if go install -v "${tool}" 2>&1; then
            print_success "${tool} installed"
        else
            print_warning "Failed to install ${tool}"
            failed_tools+=("${tool}")
        fi
    done
    
    if [[ ${#failed_tools[@]} -gt 0 ]]; then
        print_warning "Some Go tools failed to install: ${failed_tools[*]}"
        print_status "Continuing with remaining installations..."
    else
        print_success "All Go tools installed successfully"
    fi
}

# Function to install additional tools
install_additional_tools() {
    print_status "Installing additional security tools..."
    
    # Findomain
    if ! command_exists findomain; then
        print_status "Installing findomain..."
        wget -q https://github.com/Findomain/Findomain/releases/download/9.0.0/findomain-linux.zip || print_warning "Failed to download findomain"
        if [[ -f findomain-linux.zip ]]; then
            unzip -q findomain-linux.zip && chmod +x findomain && mv findomain /usr/local/bin/ && rm findomain-linux.zip
            print_success "findomain installed"
        fi
    else
        print_success "findomain already installed"
    fi
    
    # Sublist3r
    if [[ ! -d /opt/Sublist3r ]]; then
        print_status "Installing Sublist3r..."
        git clone https://github.com/aboul3la/Sublist3r.git /opt/Sublist3r || print_warning "Failed to clone Sublist3r"
        if [[ -d /opt/Sublist3r ]]; then
            cd /opt/Sublist3r && pip3 install -q -r requirements.txt || print_warning "Failed to install Sublist3r dependencies"
            ln -sf /opt/Sublist3r/sublist3r.py /usr/local/bin/sublist3r || print_warning "Failed to create symlink"
            print_success "Sublist3r installed"
        fi
    else
        print_success "Sublist3r already installed"
    fi
    
    # Waymore
    if [[ ! -d /opt/waymore ]]; then
        print_status "Installing waymore..."
        git clone https://github.com/xnl-h4ck3r/waymore.git /opt/waymore || print_warning "Failed to clone waymore"
        if [[ -d /opt/waymore ]]; then
            cd /opt/waymore && pip3 install . || print_warning "Failed to install waymore"
            print_success "waymore installed"
        fi
    else
        print_success "waymore already installed"
    fi
    
    # NucleiFuzzer
    if [[ ! -d /opt/NucleiFuzzer ]]; then
        print_status "Installing NucleiFuzzer..."
        git clone https://github.com/0xKayala/NucleiFuzzer.git /opt/NucleiFuzzer || print_warning "Failed to clone NucleiFuzzer"
        if [[ -d /opt/NucleiFuzzer ]]; then
            cd /opt/NucleiFuzzer && chmod +x install.sh && ./install.sh || print_warning "Failed to install NucleiFuzzer"
            print_success "NucleiFuzzer installed"
        fi
    else
        print_success "NucleiFuzzer already installed"
    fi
}

# Function to setup gf patterns
setup_gf_patterns() {
    print_status "Setting up gf patterns..."
    mkdir -p ~/.gf
    
    # Install gf patterns
    if [[ ! -d /tmp/gf ]]; then
        git clone https://github.com/tomnomnom/gf.git /tmp/gf || print_warning "Failed to clone gf"
        if [[ -d /tmp/gf ]]; then
            cp /tmp/gf/examples/*.json ~/.gf/ 2>/dev/null || true
        fi
    fi
    
    # Install additional patterns
    if [[ ! -d /tmp/Gf-Patterns ]]; then
        git clone https://github.com/1ndianl33t/Gf-Patterns /tmp/Gf-Patterns || print_warning "Failed to clone Gf-Patterns"
        if [[ -d /tmp/Gf-Patterns ]]; then
            cp /tmp/Gf-Patterns/*.json ~/.gf/ 2>/dev/null || true
        fi
    fi
    
    # Cleanup
    rm -rf /tmp/gf /tmp/Gf-Patterns
    print_success "gf patterns configured"
}

# Function to build Docker sandbox
build_docker_sandbox() {
    if [[ -f sandbox/Dockerfile.sandbox ]]; then
        print_status "Building BBH-AI sandbox Docker image..."
        
        # Configure Docker DNS if needed
        if ! docker pull python:3.11-slim --quiet >/dev/null 2>&1; then
            print_status "Configuring Docker DNS fallback..."
            mkdir -p /etc/docker
            cat > /etc/docker/daemon.json << DOCKER_EOF
{
  "dns": ["8.8.8.8", "1.1.1.1"],
  "insecure-registries": []
}
DOCKER_EOF
            systemctl restart docker || print_warning "Failed to restart Docker"
            sleep 5
        fi
        
        # Build the image
        if docker build --network=host -t bbh-ai-unified -f sandbox/Dockerfile.sandbox .; then
            print_success "Docker sandbox image built successfully"
        else
            print_warning "Docker build failed - you may need to run 'python rebuild_docker.py' manually"
        fi
    else
        print_warning "sandbox/Dockerfile.sandbox not found - skipping Docker build"
    fi
}

# Function to setup Python environment
setup_python_env() {
    print_status "Setting up Python virtual environment..."
    
    # Remove existing venv if it exists
    rm -rf venv
    
    # Create new virtual environment
    python3 -m venv venv || error_exit "Failed to create virtual environment"
    
    # Activate and upgrade pip
    source venv/bin/activate
    pip install --upgrade pip || print_warning "Failed to upgrade pip"
    
    # Install Python dependencies
    if [[ -f requirements.txt ]]; then
        pip install -r requirements.txt || error_exit "Failed to install Python dependencies"
        print_success "Python dependencies installed"
    else
        error_exit "requirements.txt not found"
    fi
    
    # Deactivate venv
    deactivate
}

# Function to create startup script
create_startup_script() {
    print_status "Creating startup convenience script..."
    
    cat > start_bbh_ai.sh << 'STARTUP_EOF'
#!/bin/bash
# BBH-AI Startup Script
# Run: ./start_bbh_ai.sh

set -e

echo "Starting BBH-AI..."

# Check if virtual environment exists
if [[ ! -d "venv" ]]; then
    echo "Virtual environment not found. Please run: sudo ./installer.sh"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Set Python path
export PYTHONPATH=$PWD:$PYTHONPATH

# Start Redis if not running
if ! pgrep redis-server > /dev/null; then
    echo "Starting Redis..."
    sudo systemctl start redis-server
fi

# Start PostgreSQL if not running
if ! pgrep postgres > /dev/null; then
    echo "Starting PostgreSQL..."
    sudo systemctl start postgresql
fi

echo "BBH-AI environment ready!"
echo "Run your commands with the virtual environment activated."
echo "Example: python main.py --help"
STARTUP_EOF
    
    chmod +x start_bbh_ai.sh
    print_success "Startup script created: ./start_bbh_ai.sh"
}

# Function to verify installation
verify_installation() {
    print_status "Verifying installation..."
    
    local missing_tools=()
    
    # Check critical tools
    local critical_tools=(go python3 pip3 docker redis-cli)
    for tool in "${critical_tools[@]}"; do
        if ! command_exists "$tool"; then
            missing_tools+=("$tool")
        fi
    done
    
    # Check Go tools
    local go_tools=(nuclei subfinder httpx katana dnsx)
    for tool in "${go_tools[@]}"; do
        if ! command_exists "$tool"; then
            missing_tools+=("$tool")
        fi
    done
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        print_warning "Some tools may not be available in PATH: ${missing_tools[*]}"
        print_status "You may need to restart your shell or run: source ~/.bashrc"
    else
        print_success "All critical tools verified"
    fi
}

# Main installation process
main() {
    print_status "Starting comprehensive BBH-AI installation..."
    
    update_system
    install_system_deps
    install_go
    install_go_tools
    install_additional_tools
    setup_gf_patterns
    build_docker_sandbox
    setup_python_env
    create_startup_script
    verify_installation
    
    print_success "BBH-AI installation completed successfully!"
    echo
    print_status "Next steps:"
    echo "  1. Restart your shell or run: source ~/.bashrc"
    echo "  2. Activate environment: source venv/bin/activate"
    echo "  3. Quick start: ./start_bbh_ai.sh"
    echo "  4. Run BBH-AI: python main.py --help"
    echo
    print_success "Happy hacking with BBH-AI! íº€"
}

# Run main function
main "$@"
