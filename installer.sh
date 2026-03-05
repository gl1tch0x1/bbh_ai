#!/bin/bash
# installer.sh - Complete automated setup for BBH-AI multi-agent framework
# Run as root: sudo ./installer.sh

set -euo pipefail

# ----------------------------------------------------------------------
# Terminal capabilities and color setup
# ----------------------------------------------------------------------
USE_COLOR=true
USE_TPUT=true

# Check if stdout is a terminal
if [ ! -t 1 ]; then
    USE_COLOR=false
    USE_TPUT=false
fi

# Try to use tput for colors, fallback to ANSI codes
if $USE_TPUT && command -v tput >/dev/null 2>&1; then
    COLUMNS=$(tput cols)
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    COLUMNS=80
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    MAGENTA='\033[0;35m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
fi

# ----------------------------------------------------------------------
# Helper functions for beautiful output
# ----------------------------------------------------------------------

# Print a centered text inside a fancy box
print_banner() {
    local banner_text=(
        "██████╗ ██████╗ ██╗  ██╗       █████╗ ██╗"
        "██╔══██╗██╔══██╗██║  ██║      ██╔══██╗██║"
        "██████╔╝██████╔╝███████║█████╗███████║██║"
        "██╔══██╗██╔══██╗██╔══██║╚════╝██╔══██║██║"
        "██████╔╝██████╔╝██║  ██║      ██║  ██║██║"
        "╚═════╝ ╚═════╝ ╚═╝  ╚═╝      ╚═╝  ╚═╝╚═╝"
        "                                                     "
        "        Multi‑Agent AI Framework for Bug Bounty        "
        "              Automated Installation Wizard            "
    )
    local line
    local width=$COLUMNS
    local padding
    for line in "${banner_text[@]}"; do
        padding=$(( (width - ${#line}) / 2 ))
        printf "%*s" $padding ""
        echo -e "${CYAN}${BOLD}${line}${RESET}"
    done
    echo
}

# Print a section header with underline
print_section() {
    local msg="$1"
    local width=$COLUMNS
    local line=$(printf '%*s' "$width" | tr ' ' '=')
    echo -e "\n${BOLD}${MAGENTA}▶ $msg${RESET}"
    echo -e "${CYAN}${line}${RESET}"
}

# Print success message with checkmark
print_success() {
    echo -e " ${GREEN}✓${RESET} $1"
}

# Print info message with arrow
print_info() {
    echo -e " ${BLUE}→${RESET} $1"
}

# Print warning message with exclamation
print_warning() {
    echo -e " ${YELLOW}⚠${RESET} $1"
}

# Print error message and exit
error_exit() {
    echo -e "\n ${RED}✗${RESET} ${BOLD}Error:${RESET} $1"
    echo -e "   Please check the log file at /tmp/bbh_install.log for details.\n"
    exit 1
}

# ----------------------------------------------------------------------
# Spinner and progress bar functions
# ----------------------------------------------------------------------

# Show a spinner while a command runs in the background
# Usage: run_with_spinner "message" command [args...]
run_with_spinner() {
    local msg="$1"
    shift
    local -a cmd=("$@")
    local logfile="/tmp/bbh_install.log"
    local pid
    local delay=0.1
    local spinstr='|/-\'
    
    printf " ${BLUE}→${RESET} %s  " "$msg"
    
    # Run command with output redirected to logfile
    "${cmd[@]}" >> "$logfile" 2>&1 &
    pid=$!
    
    # Show spinner while waiting
    while kill -0 $pid 2>/dev/null; do
        local temp=${spinstr#?}
        printf "\b%s" "${spinstr:0:1}"
        spinstr=$temp${spinstr%"$temp"}
        sleep $delay
    done
    
    wait $pid
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        printf "\b${GREEN}✓${RESET}\n"
    else
        printf "\b${RED}✗${RESET}\n"
        echo -e "\nLast 20 lines of log:" >> /dev/stderr
        tail -20 "$logfile" > /dev/stderr
        error_exit "Command failed: ${cmd[*]}"
    fi
}

# Show a progress bar for a loop with known total
# Usage: progress_bar current total
progress_bar() {
    local current=$1
    local total=$2
    local width=$((COLUMNS - 20))
    local percentage=$((current * 100 / total))
    local completed=$((current * width / total))
    local remaining=$((width - completed))
    
    printf "\r ${BLUE}→${RESET} ["
    printf "%${completed}s" | tr ' ' '='
    printf "%${remaining}s" | tr ' ' ' '
    printf "] %3d%% (%d/%d)" "$percentage" "$current" "$total"
}

# ----------------------------------------------------------------------
# Prerequisite checks
# ----------------------------------------------------------------------
check_prerequisites() {
    print_section "Prerequisites"
    
    # Check root
    if [[ $EUID -ne 0 ]]; then
        error_exit "This script must be run as root (use sudo)."
    fi
    print_success "Running as root"
    
    # Check project directory
    if [[ ! -f "config.yaml" ]] || [[ ! -f "requirements.txt" ]]; then
        error_exit "Please run this script from the BBH-AI project root directory (where config.yaml and requirements.txt are located)."
    fi
    print_success "Project directory verified"
    
    # Internet connectivity check
    if ! ping -c1 google.com &>/dev/null; then
        print_warning "No internet connection detected. Some installations may fail."
    else
        print_success "Internet connectivity OK"
    fi
    
    # Disk space check (need at least 5GB free)
    local available=$(df / --output=avail -B1 | tail -1)
    if [[ $available -lt 5368709120 ]]; then  # 5GB in bytes
        print_warning "Less than 5GB free disk space. Installation may fail."
    else
        print_success "Sufficient disk space"
    fi
}

# ----------------------------------------------------------------------
# Main installation functions (enhanced with UI/UX)
# ----------------------------------------------------------------------

update_system() {
    print_section "System Update"
    run_with_spinner "Updating package lists..." apt-get update -yqq
    run_with_spinner "Upgrading packages..." apt-get upgrade -yqq
    print_success "System updated"
}

install_system_deps() {
    print_section "Installing System Dependencies"
    local packages=(
        git curl wget make gcc libpcap-dev libssl-dev
        python3 python3-pip python3-venv python3-dev
        jq parallel nmap masscan dnsutils unzip
        docker.io redis-server postgresql postgresql-contrib
        build-essential libffi-dev libxml2-dev libxslt-dev
    )
    
    print_info "Installing ${#packages[@]} packages..."
    run_with_spinner "Installing packages..." apt-get install -yqq "${packages[@]}"
    
    # Enable services
    systemctl enable redis-server --now &>/dev/null || print_warning "Redis enable failed"
    systemctl enable docker --now &>/dev/null || print_warning "Docker enable failed"
    systemctl enable postgresql --now &>/dev/null || print_warning "PostgreSQL enable failed"
    
    print_success "System dependencies installed"
}

install_go() {
    print_section "Go Installation"
    
    if command_exists go; then
        print_success "Go already installed: $(go version)"
        return
    fi
    
    local GO_VERSION="1.21.5"
    local GO_TAR="go${GO_VERSION}.linux-amd64.tar.gz"
    local GO_URL="https://go.dev/dl/${GO_TAR}"
    
    print_info "Downloading Go ${GO_VERSION}..."
    run_with_spinner "Downloading Go..." wget -q --show-progress "${GO_URL}" -O "/tmp/${GO_TAR}"
    
    print_info "Extracting Go..."
    run_with_spinner "Extracting..." tar -C /usr/local -xzf "/tmp/${GO_TAR}"
    
    # Add to PATH
    export PATH=$PATH:/usr/local/go/bin
    echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile
    echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
    
    rm "/tmp/${GO_TAR}"
    print_success "Go ${GO_VERSION} installed"
}

install_go_tools() {
    print_section "Installing Go Tools (this may take several minutes)"
    
    export PATH=$PATH:/usr/local/go/bin:~/go/bin
    export GOPROXY=direct
    export GOSUMDB=off
    export CGO_ENABLED=0
    
    mkdir -p ~/go/bin
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
    
    local total=${#tools[@]}
    local current=0
    local failed=()
    
    for tool in "${tools[@]}"; do
        current=$((current + 1))
        progress_bar $current $total
        printf " %s" "$(basename "${tool%%@*}")"
        
        if go install -v "${tool}" >> /tmp/bbh_install.log 2>&1; then
            :
        else
            failed+=("$tool")
        fi
    done
    echo  # newline after progress bar
    
    if [[ ${#failed[@]} -gt 0 ]]; then
        print_warning "${#failed[@]} Go tools failed to install"
    else
        print_success "All Go tools installed successfully"
    fi
}

install_additional_tools() {
    print_section "Installing Additional Tools"
    
    # Findomain
    if ! command_exists findomain; then
        run_with_spinner "Installing findomain..." bash -c "
            wget -q https://github.com/Findomain/Findomain/releases/download/9.0.0/findomain-linux.zip -O /tmp/findomain.zip
            unzip -q /tmp/findomain.zip -d /tmp
            chmod +x /tmp/findomain
            mv /tmp/findomain /usr/local/bin/
            rm /tmp/findomain.zip
        "
        print_success "findomain installed"
    else
        print_success "findomain already present"
    fi
    
    # Sublist3r
    if [[ ! -d /opt/Sublist3r ]]; then
        run_with_spinner "Installing Sublist3r..." bash -c "
            git clone --quiet https://github.com/aboul3la/Sublist3r.git /opt/Sublist3r
            cd /opt/Sublist3r && pip3 install -q -r requirements.txt
            ln -sf /opt/Sublist3r/sublist3r.py /usr/local/bin/sublist3r
        "
        print_success "Sublist3r installed"
    else
        print_success "Sublist3r already present"
    fi
    
    # Waymore
    if [[ ! -d /opt/waymore ]]; then
        run_with_spinner "Installing waymore..." bash -c "
            git clone --quiet https://github.com/xnl-h4ck3r/waymore.git /opt/waymore
            cd /opt/waymore && pip3 install . > /dev/null
        "
        print_success "waymore installed"
    else
        print_success "waymore already present"
    fi
    
    # NucleiFuzzer
    if [[ ! -d /opt/NucleiFuzzer ]]; then
        run_with_spinner "Installing NucleiFuzzer..." bash -c "
            git clone --quiet https://github.com/0xKayala/NucleiFuzzer.git /opt/NucleiFuzzer
            cd /opt/NucleiFuzzer && chmod +x install.sh && ./install.sh > /dev/null
        "
        print_success "NucleiFuzzer installed"
    else
        print_success "NucleiFuzzer already present"
    fi
}

setup_gf_patterns() {
    print_section "Configuring gf Patterns"
    
    mkdir -p ~/.gf
    
    # Clone patterns repositories
    run_with_spinner "Downloading gf patterns..." bash -c "
        git clone --quiet https://github.com/tomnomnom/gf.git /tmp/gf
        cp /tmp/gf/examples/*.json ~/.gf/ 2>/dev/null || true
        rm -rf /tmp/gf
    "
    
    run_with_spinner "Downloading additional patterns..." bash -c "
        git clone --quiet https://github.com/1ndianl33t/Gf-Patterns /tmp/Gf-Patterns
        cp /tmp/Gf-Patterns/*.json ~/.gf/ 2>/dev/null || true
        rm -rf /tmp/Gf-Patterns
    "
    
    print_success "gf patterns configured"
}

build_docker_sandbox() {
    if [[ ! -f sandbox/Dockerfile.sandbox ]]; then
        print_warning "sandbox/Dockerfile.sandbox not found - skipping Docker build"
        return
    fi
    
    print_section "Building Docker Sandbox"
    
    # Ensure Docker is running and configured
    run_with_spinner "Configuring Docker DNS..." bash -c "
        mkdir -p /etc/docker
        cat > /etc/docker/daemon.json << DOCKER_EOF
{
  \"dns\": [\"8.8.8.8\", \"1.1.1.1\"],
  \"insecure-registries\": []
}
DOCKER_EOF
        systemctl restart docker
        sleep 5
    "
    
    # Pull base image
    run_with_spinner "Pulling base image..." docker pull python:3.11-slim --quiet
    
    # Build image
    print_info "Building image bbh-ai-unified (this may take a while)..."
    if docker build --network=host -t bbh-ai-unified -f sandbox/Dockerfile.sandbox . >> /tmp/bbh_install.log 2>&1; then
        print_success "Docker sandbox image built successfully"
    else
        print_warning "Docker build failed - you may need to run 'python rebuild_docker.py' manually"
    fi
}

setup_python_env() {
    print_section "Python Environment Setup"
    
    # Remove existing venv if present
    if [[ -d venv ]]; then
        rm -rf venv
        print_info "Removed old virtual environment"
    fi
    
    run_with_spinner "Creating virtual environment..." python3 -m venv venv
    
    source venv/bin/activate
    run_with_spinner "Upgrading pip..." pip install --upgrade pip
    
    if [[ -f requirements.txt ]]; then
        run_with_spinner "Installing Python packages..." pip install -r requirements.txt
        print_success "Python dependencies installed"
    else
        error_exit "requirements.txt not found"
    fi
    
    deactivate
}

create_startup_script() {
    print_section "Creating Startup Script"
    
    cat > start_bbh_ai.sh << 'STARTUP_EOF'
#!/bin/bash
# BBH-AI Startup Script
# Run: ./start_bbh_ai.sh

set -e

echo -e "\033[1;36m▶ Starting BBH-AI...\033[0m"

# Check virtual environment
if [[ ! -d "venv" ]]; then
    echo -e "\033[1;31m✗ Virtual environment not found. Please run: sudo ./installer.sh\033[0m"
    exit 1
fi

# Activate environment
source venv/bin/activate
export PYTHONPATH=$PWD:$PYTHONPATH

# Start services
if ! pgrep redis-server > /dev/null; then
    echo -e "\033[1;33m⚠ Starting Redis...\033[0m"
    sudo systemctl start redis-server
fi

if ! pgrep postgres > /dev/null; then
    echo -e "\033[1;33m⚠ Starting PostgreSQL...\033[0m"
    sudo systemctl start postgresql
fi

echo -e "\033[1;32m✓ BBH-AI environment ready!\033[0m"
echo -e "Run your commands with the virtual environment activated."
echo -e "Example: python main.py --help"
STARTUP_EOF
    
    chmod +x start_bbh_ai.sh
    print_success "Created start_bbh_ai.sh"
}

verify_installation() {
    print_section "Verification"
    
    local missing=()
    
    # Check critical system tools
    for tool in go python3 pip3 docker redis-cli; do
        if ! command_exists "$tool"; then
            missing+=("$tool")
        fi
    done
    
    # Check common Go tools
    for tool in nuclei subfinder httpx katana dnsx; do
        if ! command_exists "$tool"; then
            missing+=("$tool")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        print_warning "Some tools are missing: ${missing[*]}"
        print_info "You may need to restart your shell or run: source ~/.bashrc"
    else
        print_success "All critical tools verified"
    fi
}

# ----------------------------------------------------------------------
# Main orchestration
# ----------------------------------------------------------------------
main() {
    # Clear screen for better presentation
    clear
    
    # Show banner
    print_banner
    
    # Start timer
    local start_time=$SECONDS
    
    # Trap Ctrl+C
    trap 'echo -e "\n\n${RED}Installation interrupted by user${RESET}"; exit 1' INT
    
    # Create log file
    touch /tmp/bbh_install.log
    echo "BBH-AI installation started at $(date)" > /tmp/bbh_install.log
    
    # Run steps
    check_prerequisites
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
    
    local elapsed=$((SECONDS - start_time))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))
    
    # Final summary
    echo
    print_section "Installation Complete"
    echo -e " ${GREEN}✓${RESET} BBH-AI has been successfully installed!"
    echo -e " ${GREEN}✓${RESET} Total time: ${minutes}m ${seconds}s"
    echo
    echo -e " ${BLUE}→${RESET} Next steps:"
    echo -e "  1. Restart your shell or run: ${BOLD}source ~/.bashrc${RESET}"
    echo -e "  2. Activate environment: ${BOLD}source venv/bin/activate${RESET}"
    echo -e "  3. Quick start: ${BOLD}./start_bbh_ai.sh${RESET}"
    echo -e "  4. Run BBH-AI: ${BOLD}python main.py --help${RESET}"
    echo
    echo -e " ${MAGENTA}Happy hacking with BBH-AI!${RESET}"
    echo
}

# Helper: command existence check
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Run main
main "$@"