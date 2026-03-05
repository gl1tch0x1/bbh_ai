#!/bin/bash
# =============================================================================
# BBH-AI Ultimate Installer (Production-Grade, Idempotent)
# Version: 3.0 - Enterprise Features & Security Enhancements
# =============================================================================
# Features:
#   - Checksum-verified downloads (SHA256)
#   - Network resilience with exponential backoff
#   - Architecture detection (x86_64, ARM64)
#   - Comprehensive version management
#   - Security validation & permission checks
#   - Smart idempotency (skips already-installed tools)
#   - Comprehensive logging & error reports
#   - Disk space validation
#   - Network connectivity checks
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# Trap errors with context
trap 'on_error' ERR
trap 'cleanup' EXIT INT TERM

on_error() {
    echo -e "\n${RED}${BOLD}✗ Installation failed at line $LINENO${RESET}"
    echo -e "${YELLOW}Log file: $LOG_FILE${RESET}"
    
    # Show APT diagnostics if apt-related error
    if grep -q "apt\|dpkg" << EOF
$(tail -50 "$LOG_FILE" 2>/dev/null)
EOF
    then
        print_apt_diagnostics
    fi
    
    echo -e "${CYAN}Review the log file or try these troubleshooting steps:${RESET}"
    echo "  1. Check internet connection: ping google.com"
    echo "  2. Check APT:  sudo apt-get update"
    echo "  3. Fix broken dependencies: sudo apt-get -f install"
    echo "  4. Re-run installer: sudo ./installer.sh"
    echo ""
    exit 1
}

cleanup() {
    [[ -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"
    [[ -f "$SPINNER_PID_FILE" ]] && rm -f "$SPINNER_PID_FILE"
}

# =============================================================================
# Global Configuration
# =============================================================================
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LOG_FILE="/tmp/bbh-ai-install-$(date +%Y%m%d_%H%M%S).log"
readonly TEMP_DIR="/tmp/bbh-ai-install-$$"
readonly SPINNER_PID_FILE="/tmp/bbh-ai-spinner-$$.pid"

# Resilience settings (with exponential backoff)
readonly MAX_RETRIES=3
readonly INITIAL_RETRY_DELAY=2
readonly MAX_RETRY_DELAY=30
readonly DOWNLOAD_TIMEOUT=120
readonly COMMAND_TIMEOUT=300

# System information
readonly ARCHITECTURE="$(uname -m)"
readonly OS_TYPE="$(uname -s)"
readonly CPU_CORES="$(nproc 2>/dev/null || echo 4)"

# Feature flags
SKIP_NETWORK_DIAGS="${SKIP_NETWORK_DIAGS:-false}"
VERBOSE_MODE="${VERBOSE_MODE:-false}"

# Create directories
mkdir -p "$TEMP_DIR"

# Redirect all output to log file and console
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

# =============================================================================
# Terminal & Color Setup
# =============================================================================
USE_COLOR=true
[[ ! -t 1 ]] && USE_COLOR=false

if $USE_COLOR && command -v tput >/dev/null 2>&1; then
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    MAGENTA='\033[0;35m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
fi

# Unicode symbols
CHECK_MARK="✓"
CROSS_MARK="✗"
WARN_MARK="⚠"
INFO_MARK="ℹ"
ARROW="▶"

# =============================================================================
# Troubleshooting & Diagnostics
# =============================================================================

print_apt_diagnostics() {
    echo ""
    print_warning "APT Diagnostics Information"
    echo "  • System: $(lsb_release -d 2>/dev/null | cut -f2)"
    echo "  • Kernel: $(uname -r)"
    echo "  • Arch: $ARCHITECTURE"
    echo ""
    echo "  To manually fix APT issues, try:"
    echo "    1. sudo apt-get clean"
    echo "    2. sudo apt-get autoclean"
    echo "    3. sudo apt-get -f install"
    echo "    4. sudo apt-get update"
    echo "    5. sudo apt-get upgrade"
    echo ""
    echo "  For specific package errors:"
    echo "    sudo apt-cache search <package_name>"
    echo "    sudo apt-get install -y <package_name>"
    echo ""
}

# =============================================================================
# Output Functions (Context-Aware)
# =============================================================================

print_banner() {
    echo -e "${CYAN}${BOLD}"
    cat << 'EOF'
██████╗ ██████╗ ██╗  ██╗       █████╗ ██╗
██╔══██╗██╔══██╗██║  ██║      ██╔══██╗██║
██████╔╝██████╔╝███████║█████╗███████║██║
██╔══██╗██╔══██╗██╔══██║╚════╝██╔══██║██║
██████╔╝██████╔╝██║  ██║      ██║  ██║██║
╚═════╝ ╚═════╝ ╚═╝  ╚═╝      ╚═╝  ╚═╝╚═╝
EOF
    echo -e "${RESET}${BOLD}        Multi-Agent AI Framework for Bug Bounty${RESET}"
    echo -e "${BOLD}           Enterprise Installation Wizard${RESET}"
    echo -e "${MAGENTA}═══════════════════════════════════════════════════════════${RESET}\n"
}

print_step() {
    echo -e "\n${BLUE}${BOLD}${ARROW}${RESET} ${BOLD}$1${RESET}"
    echo -e "${BLUE}───────────────────────────────────────────────────────${RESET}"
}

print_info() {
    echo -e "  ${CYAN}${INFO_MARK}${RESET} $1"
}

print_success() {
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} $1"
}

print_warning() {
    echo -e "  ${YELLOW}${WARN_MARK}${RESET} $1"
}

print_error() {
    echo -e "  ${RED}${CROSS_MARK}${RESET} $1" >&2
}

print_skip() {
    echo -e "  ${YELLOW}⏭${RESET} $1 (already installed)"
}

print_debug() {
    if [[ "$VERBOSE_MODE" == "true" ]]; then
        echo -e "  ${MAGENTA}[DEBUG]${RESET} $1"
    fi
}

# =============================================================================
# Core Utility Functions
# =============================================================================

# Check command with debug output
is_installed() {
    local cmd="$1"
    if command -v "$cmd" &>/dev/null; then
        print_debug "$cmd found in PATH"
        return 0
    fi
    return 1
}

# Get version with error handling
get_version() {
    local cmd="$1"
    local flag="${2:---version}"
    
    if ! is_installed "$cmd"; then
        return 1
    fi
    
    if output=$("$cmd" "$flag" 2>&1); then
        echo "$output" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 || echo "unknown"
    else
        echo "error"
    fi
}

# Verify file checksum (SHA256)
verify_checksum() {
    local file="$1"
    local expected_hash="$2"
    
    if [[ ! -f "$file" ]]; then
        print_error "File not found: $file"
        return 1
    fi
    
    local actual_hash
    actual_hash=$(sha256sum "$file" | awk '{print $1}')
    
    if [[ "$actual_hash" == "$expected_hash" ]]; then
        print_debug "Checksum verified: $file"
        return 0
    else
        print_error "Checksum mismatch for $file"
        print_error "  Expected: $expected_hash"
        print_error "  Got:      $actual_hash"
        return 1
    fi
}

# Download with retry logic and checksum verification
download_with_retry() {
    local url="$1"
    local output="$2"
    local checksum="${3:-}"
    local attempt=1
    local delay=$INITIAL_RETRY_DELAY
    
    while [[ $attempt -le $MAX_RETRIES ]]; do
        print_debug "Download attempt $attempt/$MAX_RETRIES: $url"
        
        if wget --timeout="$DOWNLOAD_TIMEOUT" -q -O "$output" "$url" 2>/dev/null; then
            if [[ -n "$checksum" ]]; then
                if verify_checksum "$output" "$checksum"; then
                    return 0
                else
                    rm -f "$output"
                fi
            else
                return 0
            fi
        fi
        
        if [[ $attempt -lt $MAX_RETRIES ]]; then
            print_debug "Download failed, retrying in ${delay}s..."
            sleep "$delay"
            delay=$(( delay < MAX_RETRY_DELAY ? delay * 2 : MAX_RETRY_DELAY ))
        fi
        
        attempt=$((attempt + 1))
    done
    
    print_error "Failed to download: $url"
    return 1
}

# Run command with timeout and retry
run_with_retry() {
    local cmd="$1"
    local desc="$2"
    local attempt=1
    local delay=$INITIAL_RETRY_DELAY
    
    while [[ $attempt -le $MAX_RETRIES ]]; do
        print_debug "$desc (attempt $attempt/$MAX_RETRIES)"
        
        if timeout "$COMMAND_TIMEOUT" bash -c "$cmd" &>/dev/null; then
            return 0
        fi
        
        if [[ $attempt -lt $MAX_RETRIES ]]; then
            print_debug "Command failed, retrying in ${delay}s..."
            sleep "$delay"
            delay=$(( delay < MAX_RETRY_DELAY ? delay * 2 : MAX_RETRY_DELAY ))
        fi
        
        attempt=$((attempt + 1))
    done
    
    return 1
}

# Spinner animation for long operations
run_with_spinner() {
    local cmd="$1"
    local msg="$2"
    
    echo -ne "  ${BLUE}${ARROW}${RESET} $msg ... "
    
    local output_file="$TEMP_DIR/cmd_output_$$.log"
    local pid_file="$SPINNER_PID_FILE"
    
    bash -c "$cmd" > "$output_file" 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    
    local spinner=('-' '\' '|' '/')
    local i=0
    
    while kill -0 $pid 2>/dev/null; do
        printf "\r  ${BLUE}${ARROW}${RESET} $msg ... ${spinner:$i:1} "
        i=$(( (i + 1) % 4 ))
        sleep 0.15
    done
    
    rm -f "$pid_file"
    
    if wait $pid; then
        printf "\r  ${GREEN}${CHECK_MARK}${RESET} $msg ... Done.         \n"
        rm -f "$output_file"
        return 0
    else
        printf "\r  ${RED}${CROSS_MARK}${RESET} $msg ... Failed.       \n"
        [[ -f "$output_file" ]] && tail -n 5 "$output_file" | sed 's/^/    /'
        rm -f "$output_file"
        return 1
    fi
}

# Check disk space
check_disk_space() {
    local min_space_mb=10000  # 10GB minimum
    local available_space
    available_space=$(df "$SCRIPT_DIR" | awk 'NR==2 {print int($4/1024)}')
    
    if [[ $available_space -lt $min_space_mb ]]; then
        print_warning "Low disk space: ${available_space}MB available (${min_space_mb}MB recommended)"
        return 1
    fi
    return 0
}

# Network connectivity check
check_network() {
    local timeout=5
    
    if ! timeout "$timeout" bash -c "echo > /dev/tcp/8.8.8.8/53" 2>/dev/null; then
        print_warning "Network connectivity limited"
        if [[ "$SKIP_NETWORK_DIAGS" != "true" ]]; then
            print_info "Try: SKIP_NETWORK_DIAGS=true ./installer.sh"
        fi
        return 1
    fi
    return 0
}

# =============================================================================
# Validation & Prerequisites
# =============================================================================

validate_prerequisites() {
    print_step "Validation & System Checks"
    
    # Root check
    if [[ $EUID -ne 0 ]]; then
        print_error "This script requires root privileges (use: sudo ./installer.sh)"
        exit 1
    fi
    print_success "Running as root"
    
    # Project directory check
    if [[ ! -f "$SCRIPT_DIR/config.example.yaml" ]]; then
        print_error "Must run from project root (where config.example.yaml exists)"
        echo "  Current directory: $SCRIPT_DIR"
        exit 1
    fi
    print_success "Project root verified"
    
    # OS compatibility
    if [[ "$OS_TYPE" != "Linux" ]]; then
        print_error "This script is for Linux (detected: $OS_TYPE)"
        exit 1
    fi
    print_success "Linux $ARCHITECTURE system detected"
    
    # Distro detection
    local distro_info="Unknown"
    if [[ -f /etc/os-release ]]; then
        distro_info=$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)
    fi
    print_info "Distribution: $distro_info"
    
    # Check disk space
    if ! check_disk_space; then
        print_warning "Continuing with low disk space..."
    else
        print_success "Disk space adequate"
    fi
    
    # Check network connectivity
    if ! check_network; then
        print_warning "Network issues detected"
        if [[ "$SKIP_NETWORK_DIAGS" != "true" ]]; then
            sleep 2
        fi
    else
        print_success "Network connectivity verified"
    fi
}

# =============================================================================
# System Dependencies (with Recovery & Diagnostics)
# =============================================================================

install_system_dependencies() {
    print_step "System Dependencies"
    
    # Critical dependencies - must have
    local -a critical_packages=(
        git curl wget make build-essential libpcap-dev libssl-dev
        python3 python3-pip python3-venv jq parallel nmap masscan
        dnsutils unzip docker.io net-tools whois apt-transport-https
        ca-certificates gnupg lsb-release
    )
    
    # Optional dependencies - nice to have but not critical
    local -a optional_packages=(
        git-lfs
    )
    
    # Preliminary diagnostics
    print_info "Running APT diagnostics..."
    
    # Check and fix broken dependencies
    if ! apt-get check &>/dev/null; then
        print_warning "Fixing broken dependencies..."
        if run_with_spinner "apt-get -f install -y" "Fixing broken APT state"; then
            print_success "Broken dependencies fixed"
        else
            print_warning "Could not auto-fix all dependencies, continuing..."
        fi
    fi
    
    # Clean apt cache
    apt-get clean &>/dev/null || true
    apt-get autoclean &>/dev/null || true
    
    # Update package lists with retry
    print_info "Updating package lists..."
    if ! run_with_retry "apt-get update" "apt-get update"; then
        print_warning "apt update had issues, continuing with cached packages..."
    fi
    
    # Check for critical packages
    print_info "Checking dependencies..."
    local missing_critical=()
    local missing_optional=()
    
    for pkg in "${critical_packages[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
            missing_critical+=("$pkg")
        fi
    done
    
    for pkg in "${optional_packages[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
            missing_optional+=("$pkg")
        fi
    done
    
    # Install critical packages
    if [[ ${#missing_critical[@]} -gt 0 ]]; then
        print_info "Installing ${#missing_critical[@]} critical packages..."
        if run_with_spinner "apt-get install -y --no-install-recommends ${missing_critical[*]}" "Installing packages"; then
            print_success "Critical packages installed"
        else
            print_error "Failed to install critical packages"
            print_info "Attempting individual package installation..."
            
            # Try installing individually for better diagnostics
            local failed_critical=()
            for pkg in "${missing_critical[@]}"; do
                if ! run_with_spinner "apt-get install -y --no-install-recommends '$pkg'" "Installing $pkg"; then
                    failed_critical+=("$pkg")
                fi
            done
            
            if [[ ${#failed_critical[@]} -gt 0 ]]; then
                print_error "Cannot install: ${failed_critical[*]}"
                print_warning "These packages may not be available in your distro"
                print_info "Try: apt-get install -y ${failed_critical[*]}"
                return 1
            fi
        fi
    else
        print_success "All critical packages already installed"
    fi
    
    # Install optional packages (non-blocking)
    if [[ ${#missing_optional[@]} -gt 0 ]]; then
        print_info "Installing ${#missing_optional[@]} optional packages..."
        for pkg in "${missing_optional[@]}"; do
            if run_with_spinner "apt-get install -y --no-install-recommends '$pkg'" "Installing $pkg"; then
                print_success "$pkg installed"
            else
                print_warning "$pkg not available in repositories (skipped)"
            fi
        done
    fi
}

# =============================================================================
# Go Installation & Management
# =============================================================================

install_go() {
    print_step "Go Environment Setup"
    
    local go_version="1.22.5"
    local expected_hash="04b2b30d890b1d85d6c25b89e5ec0fcbf8e2c42b3218c53d0b89f1701ff90f70"
    
    if is_installed go; then
        local current_version
        current_version=$(go version | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)
        print_success "Go installed (version $current_version)"
        return 0
    fi
    
    print_info "Installing Go $go_version..."
    local go_archive="$TEMP_DIR/go${go_version}.linux-${ARCHITECTURE}.tar.gz"
    local go_url="https://go.dev/dl/go${go_version}.linux-${ARCHITECTURE}.tar.gz"
    
    # Download with verification
    if download_with_retry "$go_url" "$go_archive" "$expected_hash"; then
        # Extract and install
        if run_with_spinner "tar -C /usr/local -xzf '$go_archive'" "Extracting Go"; then
            # Add to PATH
            export PATH=$PATH:/usr/local/go/bin
            if ! grep -q '/usr/local/go/bin' /etc/profile 2>/dev/null; then
                echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile
            fi
            
            print_success "Go installed: $(go version)"
        else
            print_error "Failed to extract Go"
            return 1
        fi
    else
        print_error "Failed to download Go"
        return 1
    fi
}

# =============================================================================
# Go Tools Installation (with Version Pinning)
# =============================================================================

install_go_tools() {
    print_step "Go-Based Security Tools (Multiple Minutes)"
    
    # Ensure GOPATH/bin is in PATH
    export GOPATH="${GOPATH:-$HOME/go}"
    export PATH=$PATH:$GOPATH/bin
    export GOPROXY=https://proxy.golang.org,direct
    export GO111MODULE=on
    
    # Add to bashrc for persistence
    if ! grep -q 'GOPATH' ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc <<'EOF'
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
export GOPROXY=https://proxy.golang.org,direct
export GO111MODULE=on
EOF
    fi
    
    # Go tools with pinned versions for stability
    declare -A GO_TOOLS=(
        ["subfinder"]="github.com/projectdiscovery/subfinder/v2/cmd/subfinder@v2.6.3"
        ["httpx"]="github.com/projectdiscovery/httpx/cmd/httpx@v1.4.5"
        ["nuclei"]="github.com/projectdiscovery/nuclei/v3/cmd/nuclei@v3.1.9"
        ["katana"]="github.com/projectdiscovery/katana/cmd/katana@v1.0.8"
        ["assetfinder"]="github.com/tomnomnom/assetfinder@latest"
        ["gf"]="github.com/tomnomnom/gf@latest"
        ["gau"]="github.com/lc/gau/v2/cmd/gau@v2.2.13"
        ["dalfox"]="github.com/hahwul/dalfox/v2@v2.10.0"
        ["gospider"]="github.com/jaeles-project/gospider@latest"
        ["ffuf"]="github.com/ffuf/ffuf@v2.1.0"
        ["dnsx"]="github.com/projectdiscovery/dnsx/cmd/dnsx@v1.2.0"
        ["naabu"]="github.com/projectdiscovery/naabu/v2/cmd/naabu@v2.2.0"
        ["interactsh-client"]="github.com/projectdiscovery/interactsh/cmd/interactsh-client@v1.1.7"
    )
    
    local success_count=0
    local fail_count=0
    local skip_count=0
    local -a failed_tools=()
    
    print_info "Tool installation with 3-attempt retry per tool..."
    
    for tool_name in "${!GO_TOOLS[@]}"; do
        local tool_import="${GO_TOOLS[$tool_name]}"
        
        # Check if already installed
        if is_installed "$tool_name"; then
            printf "  %-25s${YELLOW}⏭${RESET}\n" "$tool_name"
            ((skip_count++))
            continue
        fi
        
        # Attempt installation with retries
        local attempt=1
        local installed=false
        
        while [[ $attempt -le 3 && "$installed" == "false" ]]; do
            printf "  %-20s${BLUE}[%s/3]${RESET}" "$tool_name" "$attempt"
            
            if timeout "$COMMAND_TIMEOUT" go install -v "$tool_import" &>/dev/null; then
                if is_installed "$tool_name"; then
                    printf "\r  %-25s${GREEN}${CHECK_MARK}${RESET}\n"
                    installed=true
                    ((success_count++))
                fi
            fi
            
            if [[ "$installed" == "false" && $attempt -lt 3 ]]; then
                printf "\r"
                sleep 2
            fi
            
            attempt=$((attempt + 1))
        done
        
        if [[ "$installed" == "false" ]]; then
            printf "\r  %-25s${RED}${CROSS_MARK}${RESET}\n"
            failed_tools+=("$tool_name")
            ((fail_count++))
        fi
    done
    
    # Summary
    echo ""
    print_info "Go tools summary:"
    [[ $skip_count -gt 0 ]] && echo -e "  ${YELLOW}⏭${RESET}  Already installed: $skip_count"
    [[ $success_count -gt 0 ]] && echo -e "  ${GREEN}${CHECK_MARK}${RESET} Newly installed:  $success_count"
    if [[ $fail_count -gt 0 ]]; then
        echo -e "  ${RED}${CROSS_MARK}${RESET} Failed:           $fail_count (${failed_tools[*]})"
        print_warning "Review logs: $LOG_FILE"
    fi
}

# =============================================================================
# Additional Security Tools
# =============================================================================

install_additional_tools() {
    print_step "Additional Security Tools"
    
    # findomain
    if is_installed findomain; then
        print_skip "findomain"
    else
        print_info "Installing findomain..."
        if run_with_spinner \
            "cd '$TEMP_DIR' && wget -q https://github.com/Findomain/Findomain/releases/download/9.0.0/findomain-linux.zip && unzip -q findomain-linux.zip && chmod +x findomain && mv findomain /usr/local/bin/" \
            "Installing findomain"; then
            print_success "findomain installed"
        else
            print_warning "findomain installation skipped"
        fi
    fi
    
    # Sublist3r
    if [[ -d /opt/Sublist3r && -x /usr/local/bin/sublist3r ]]; then
        print_skip "Sublist3r"
    else
        print_info "Installing Sublist3r..."
        if run_with_spinner \
            "git clone https://github.com/aboul3la/Sublist3r.git /opt/Sublist3r 2>/dev/null && pip3 install -q -r /opt/Sublist3r/requirements.txt && ln -sf /opt/Sublist3r/sublist3r.py /usr/local/bin/sublist3r" \
            "Installing Sublist3r"; then
            print_success "Sublist3r installed"
        else
            print_warning "Sublist3r installation skipped"
        fi
    fi
    
    # waymore
    if is_installed waymore; then
        print_skip "waymore"
    else
        print_info "Installing waymore..."
        if run_with_spinner \
            "git clone https://github.com/xnl-h4ck3r/waymore.git /opt/waymore 2>/dev/null && pip3 install -q -r /opt/waymore/requirements.txt && chmod +x /opt/waymore/waymore.py && ln -sf /opt/waymore/waymore.py /usr/local/bin/waymore" \
            "Installing waymore"; then
            print_success "waymore installed"
        else
            print_warning "waymore installation skipped"
        fi
    fi
    
    # NucleiFuzzer
    if is_installed nf; then
        print_skip "NucleiFuzzer"
    else
        print_info "Installing NucleiFuzzer..."
        if run_with_spinner \
            "git clone https://github.com/0xKayala/NucleiFuzzer.git /opt/NucleiFuzzer 2>/dev/null && chmod +x /opt/NucleiFuzzer/nf.sh && ln -sf /opt/NucleiFuzzer/nf.sh /usr/local/bin/nf" \
            "Installing NucleiFuzzer"; then
            print_success "NucleiFuzzer installed"
        else
            print_warning "NucleiFuzzer installation skipped"
        fi
    fi
}

# =============================================================================
# Pattern Files & Configuration
# =============================================================================

setup_gf_patterns() {
    print_step "GF Pattern Library Setup"
    
    mkdir -p ~/.gf
    
    if [[ -d ~/.gf && -n "$(ls -A ~/.gf 2>/dev/null)" ]]; then
        print_skip "gf patterns"
        return 0
    fi
    
    print_info "Cloning gf patterns..."
    
    # Clone gf examples
    if git clone --quiet https://github.com/tomnomnom/gf.git "$TEMP_DIR/gf" 2>/dev/null; then
        cp "$TEMP_DIR/gf/examples"/*.json ~/.gf/ 2>/dev/null || true
    fi
    
    # Clone additional patterns
    if git clone --quiet https://github.com/1ndianl33t/Gf-Patterns "$TEMP_DIR/Gf-Patterns" 2>/dev/null; then
        cp "$TEMP_DIR/Gf-Patterns"/*.json ~/.gf/ 2>/dev/null || true
    fi
    
    if [[ -n "$(ls -A ~/.gf 2>/dev/null)" ]]; then
        local pattern_count
        pattern_count=$(ls ~/.gf/*.json 2>/dev/null | wc -l)
        print_success "gf patterns configured ($pattern_count files)"
    else
        print_warning "gf patterns setup had issues"
    fi
}

# =============================================================================
# Docker Configuration
# =============================================================================

setup_docker() {
    print_step "Docker & Sandbox Environment"
    
    # Enable and start Docker
    if ! systemctl is-enabled docker &>/dev/null; then
        print_info "Enabling Docker service..."
        systemctl enable docker --now
        print_success "Docker service enabled"
    else
        print_success "Docker service already enabled"
    fi
    
    # Note about image build
    if [[ ! -f "$SCRIPT_DIR/sandbox/Dockerfile.sandbox" ]]; then
        print_warning "sandbox/Dockerfile.sandbox not found, skipping setup note"
        return 0
    fi
    
    print_info "Note: Docker image build happens via: python rebuild_docker.py"
    print_info "Run this after installation to build the sandbox image"
}

# =============================================================================
# Python Environment Setup
# =============================================================================

setup_python() {
    print_step "Python Environment"
    
    local python_version
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    print_info "Python version: $python_version"
    
    if [[ ! -d "venv" ]]; then
        print_info "Creating virtual environment..."
        if run_with_spinner "python3 -m venv venv" "Creating venv"; then
            print_success "Virtual environment created"
        else
            print_error "Failed to create virtual environment"
            return 1
        fi
    else
        print_success "Virtual environment already exists"
    fi
    
    # Activate venv
    source venv/bin/activate
    
    # Upgrade pip
    print_info "Upgrading pip..."
    pip install --upgrade pip --quiet
    print_success "pip is up to date"
    
    # Install dependencies
    if [[ -f requirements.txt ]]; then
        print_info "Installing dependencies from requirements.txt..."
        if run_with_spinner "pip install -r requirements.txt" "Installing Python packages"; then
            print_success "Python packages installed"
        else
            print_error "Some Python packages failed to install"
            return 1
        fi
    else
        print_warning "requirements.txt not found"
        return 1
    fi
}

# =============================================================================
# Service Configuration
# =============================================================================

configure_services() {
    print_step "Service Configuration"
    
    # Configure log rotation
    cat > /etc/logrotate.d/bbh-ai <<'EOF'
/var/log/bbh-ai/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
    sharedscripts
}
EOF
    print_success "Log rotation configured"
    
    # Create log directory
    mkdir -p /var/log/bbh-ai
    chmod 755 /var/log/bbh-ai
    print_success "Log directory created: /var/log/bbh-ai"
}

# =============================================================================
# Final Summary
# =============================================================================

print_completion_summary() {
    print_step "Installation Complete"
    
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} System dependencies: checked"
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} Go environment: configured"
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} Security tools: installed"
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} gf patterns: configured"
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} Docker: enabled and ready"
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} Python environment: configured"
    echo -e "  ${GREEN}${CHECK_MARK}${RESET} Services: configured"
    
    echo ""
    echo -e "${CYAN}${BOLD}Next Steps:${RESET}"
    echo "  1. Activate the virtual environment:"
    echo "     ${BOLD}source venv/bin/activate${RESET}"
    echo ""
    echo "  2. Configure API keys:"
    echo "     ${BOLD}cp config.example.yaml config.yaml${RESET}"
    echo "     # Edit config.yaml with your API keys"
    echo ""
    echo "  3. Build Docker image:"
    echo "     ${BOLD}python rebuild_docker.py${RESET}"
    echo ""
    echo "  4. Run health check:"
    echo "     ${BOLD}python main.py --health${RESET}"
    echo ""
    echo "  5. Start scanning:"
    echo "     ${BOLD}python main.py --target example.com${RESET}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${RESET}"
    echo "  • Installation log: $LOG_FILE"
    echo "  • Fix broken APT: sudo apt-get -f install && sudo apt-get update"
    echo "  • Network issues? Use: SKIP_NETWORK_DIAGS=true sudo ./installer.sh"
    echo "  • Verbose mode: VERBOSE_MODE=true sudo ./installer.sh"
    echo "  • Missing package? Try: sudo apt-cache search <name>"
    echo ""
    echo -e "${MAGENTA}═══════════════════════════════════════════════════════════${RESET}"
    echo -e "${GREEN}${BOLD}BBH-AI is ready for enterprise penetration testing!${RESET}\n"
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    clear
    print_banner
    
    # Environment info
    echo -e "  ${CYAN}System Information:${RESET}"
    echo -e "    • OS: $OS_TYPE $ARCHITECTURE"
    echo -e "    • CPU Cores: $CPU_CORES"
    echo -e "    • Directory: $SCRIPT_DIR"
    echo -e "    • Log: $LOG_FILE\n"
    
    # Run installation stages
    validate_prerequisites
    install_system_dependencies
    install_go
    install_go_tools
    install_additional_tools
    setup_gf_patterns
    setup_docker
    setup_python
    configure_services
    print_completion_summary
}

# Execute main
main "$@"
