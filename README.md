[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-blue)](#)

# 🤖 BBH-AI: Autonomous AI Security Testing Platform

BBH-AI is an **enterprise-grade autonomous security testing platform** that combines AI reasoning with offensive security tools to autonomously discover, validate, and exploit vulnerabilities. Using Swarm Consensus Intelligence and Chain-of-Thought reasoning, BBH-AI operates like an expert penetration tester—but faster, deeper, and 24/7.

---

## 🎯 Key Capabilities

### 🧠 AI-Powered Threat Intelligence
- **Swarm Consensus**: Multiple LLM models (GPT-4, Claude 3.5, Gemini) reason together to reach high-confidence decisions
- **Chain-of-Thought Reasoning**: Explicit step-by-step attack planning, validation, and root cause analysis
- **Adaptive Exploitation**: AI generates context-aware payloads based on discovered vulnerabilities
- **CVSS v3.1 Scoring**: Automated severity calculation with zero hallucinations

### 🛡️ Industrial-Grade Reliability
- **Atomic Data Integrity**: Write-to-temp-then-rename ensures no data corruption even during crashes
- **Distributed Resilience**: Celery workers with idempotency locks and exponential backoff
- **Hardened Sandboxing**: Docker containers with `--cap-drop=ALL` restrict tool privileges
- **Local-First Architecture**: All scan data stored locally in structured JSON (no external DBs)

### 🚀 Comprehensive Coverage
- **50+ Integrated Tools**: Security tools spanning OSINT, reconnaissance, and vulnerability assessment
- **5-Phase Workflow**: Structured discovery → enrichment → web recon → exploitation → reporting
- **Multi-Agent Architecture**: Specialized agents for strategy, payload generation, and interpretation
- **Autonomous Healing**: Auto-healer compensates for tool failures and adapts scanning strategy

---

## 📋 Use Cases

| Use Case | Ideal For | Key Feature |
|----------|-----------|-------------|
| **Bug Bounty Automation** | Rapid target assessment at scale | CVSS scoring + PoC validation |
| **Continuous Security Testing** | Night/weekend scanning automation | 24/7 operation, no manual oversight |
| **Enterprise Pentesting** | Internal/external security posture | Distributed scanning across subnet ranges |
| **Compliance & Audits** | Security audit documentation | Atomic reporting, CVSS scores, root cause |
| **Vulnerability Research** | 0-day discovery & validation | AI-guided exploitation attempts |

---

## ⭐ Key Features

### Discovery & Reconnaissance
- ✅ **Passive OSINT**: Subdomain enumeration, WHOIS, DNS leaks, GitHub metadata
- ✅ **Active Probing**: Port scanning, service fingerprinting, tech stack detection
- ✅ **Web Analysis**: JavaScript auditing, API endpoint discovery, dependency analysis
- ✅ **Data Correlation**: Relationship mapping between hosts, IPs, and ASNs

### Vulnerability Assessment  
- ✅ **50+ Vulnerability Types**: SQLi, XSS, SSRF, RCE, authentication bypasses, misconfigurations
- ✅ **Automated PoC Generation**: Creates working exploits for validated vulnerabilities
- ✅ **Playwright-Based Validation**: Runs JavaScript-dependent exploits in headless browsers
- ✅ **Out-of-Band Testing**: Interactsh integration for blind vulnerability confirmation

### Reporting & Analytics
- ✅ **Multi-Format Output**: Markdown, JSON, HTML with interactive dashboards
- ✅ **Risk Metrics**: CVSS v3.1 scores, severity breakdown, trend analysis
- ✅ **Executive Summaries**: High-level findings for stakeholders
- ✅ **Evidence Artifacts**: Screenshots, HTTP requests, stack traces

---

## 🏗️ Scan Workflow

BBH-AI executes a rigorous 5-phase workflow enhanced by AI interpretation at every step:

```mermaid
graph TD
    A["<b>PHASE A: DISCOVERY</b><br/>Passive OSINT + Subdomain Enum<br/>---<br/>Tools: subfinder, gau, whois<br/>Output: Subdomains, IPs, DNS Records"] --> B["<b>PHASE B: ENRICHMENT</b><br/>Host Liveness + Port Scanning<br/>---<br/>Tools: dnsx, naabu, httpx<br/>Output: Live Hosts, Ports, Services"]
    B --> C["<b>PHASE C: WEB RECON</b><br/>JS Audit + Endpoint Discovery<br/>---<br/>Tools: katana, ffuf, jsluice<br/>Output: Endpoints, APIs, Tech Stack"]
    C --> D["<b>🤖 AI AGENT CONTROLLER</b><br/>Strategist | Architect | Interpreter"]
    D --> E["<b>PHASE D: EXPLOITATION</b><br/>Vuln Testing + PoC Validation<br/>---<br/>Tools: nuclei, sqlmap, ghauri<br/>Output: Validated Vulnerabilities"]
    E --> F["<b>PHASE E: REPORTING</b><br/>CVSS Scoring + Remediation<br/>---<br/>Output: Reports + CVSS Scores<br/>Formats: Markdown, JSON, HTML"]
    
    style A fill:#e1f5ff,stroke:#01579b,color:#000
    style B fill:#e1f5ff,stroke:#01579b,color:#000
    style C fill:#e1f5ff,stroke:#01579b,color:#000
    style D fill:#fff3e0,stroke:#e65100,color:#000,stroke-width:3px
    style E fill:#f3e5f5,stroke:#4a148c,color:#000
    style F fill:#e8f5e9,stroke:#1b5e20,color:#000
```

### Phase Execution Details

| Phase | Purpose | Key Tools | Output |
|-------|---------|-----------|--------|
| **A: Discovery** | Passive intelligence gathering | `subfinder`, `gau`, `whois`, `shodan` | Subdomains, IPs, DNS records |
| **B: Enrichment** | Host and port enumeration | `dnsx`, `puredns`, `naabu`, `httpx` | Live hosts, ports, services |
| **C: Web Recon** | Application analysis | `jsluice`, `katana`, `urless`, `ffuf` | Endpoints, APIs, tech stacks |
| **D: Exploitation** | Active vulnerability testing | `nuclei`, `sqlmap`, `ghauri`, `commix` | Validated vulnerabilities |
| **E: Reporting** | Analysis & documentation | `storage`, `validator`, `analyzer` | Reports + CVSS scores |

---

## 🤖 Agent Architecture

BBH-AI uses a trio of specialized AI agents that work collaboratively:

```mermaid
graph TD
    Master["<b>🎯 Agent Controller</b><br/>Master Orchestrator<br/>(Coordinates all agents)"]
    
    Master --> Strategist["<b>🕵️ Strategist</b><br/>Attack Planning<br/>---<br/>• Analyze targets<br/>• Map attack surface<br/>• Prioritize vectors"]
    Master --> Architect["<b>🛠️ Architect</b><br/>Payload Generation<br/>---<br/>• Create exploits<br/>• Generate payloads<br/>• Validate PoCs"]
    Master --> Interpreter["<b>🔬 Interpreter</b><br/>Vulnerability Analysis<br/>---<br/>• Explain findings<br/>• Calculate CVSS<br/>• Suggest remediation"]
    
    Strategist --> Consensus["<b>🧠 Consensus Logic</b><br/>Voting System<br/>---<br/>2/3 agents = CONFIRM<br/>3/3 agents = HIGH CONFIDENCE<br/>Disagreement = Review Required"]
    Architect --> Consensus
    Interpreter --> Consensus
    
    Consensus --> Memory["<b>💾 Memory Graph</b><br/>Knowledge Base<br/>---<br/>O(1) Lookup Performance<br/>Finding Deduplication<br/>Attack History Tracking"]
    
    style Master fill:#fff3e0,stroke:#e65100,color:#000,stroke-width:3px
    style Strategist fill:#e1f5ff,stroke:#01579b,color:#000
    style Architect fill:#e1f5ff,stroke:#01579b,color:#000
    style Interpreter fill:#e1f5ff,stroke:#01579b,color:#000
    style Consensus fill:#f3e5f5,stroke:#4a148c,color:#000
    style Memory fill:#e8f5e9,stroke:#1b5e20,color:#000
```

### Agent Specializations

| Agent | Role | LLM Models | Decision Logic |
|-------|------|-----------|---|
| **Strategist** | Attack planning | Claude 3.5 (primary) | Multi-agent voting |
| **Architect** | Payload generation | GPT-4o (primary) | Consensus on PoC validity |
| **Interpreter** | Analysis & scoring | Gemini Pro (primary) | Expert-level CVSS calculation |

---

## 🛠️ Tool Architecture

BBH-AI integrates **50+ security tools** organized in 9 categories:

```
tools/
├── api_leaks/           (5 tools)  - API secret discovery
├── cloud/               (3 tools)  - Cloud misconfiguration scanning
├── github/              (6 tools)  - GitHub reconnaissance
├── google_dorking/      (2 tools)  - Google search enumeration
├── hosts/               (8 tools)  - Port scanning & service detection
├── misconfig/           (3 tools)  - Misconfiguration detection
├── osint/               (7 tools)  - Open-source intelligence
├── subdomains/          (14 tools) - Subdomain enumeration
├── vuln/                (12 tools) - Vulnerability scanning & exploitation
└── web/                 (18 tools) - Web application testing
```

Each tool is wrapped with:
- ✅ Standardized input/output interfaces
- ✅ Timeout handling & crash recovery
- ✅ Telemetry & execution logging
- ✅ Category tagging for intelligent orchestration
- ✅ Configuration persistence (config.yaml)

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.11+**
- **Docker** (with Docker daemon running)
- **4GB RAM** (8GB+ recommended)
- **Linux/macOS/Windows with WSL2**

### Installation

#### Option 1: Automated (Recommended)
```bash
git clone https://github.com/gl1tch0x1/bbh_ai.git && cd bbh_ai

# Automated setup (handles Python, Go tools, Docker)
chmod +x installer.sh
sudo ./installer.sh
```

#### Option 2: Manual
```bash
# Clone repo
git clone https://github.com/gl1tch0x1/bbh_ai.git && cd bbh_ai

# Create Python environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python packages
pip install -r requirements.txt

# Build Docker image
python rebuild_docker.py

# Verify setup
python main.py --health
```

### Configuration

1. **Create `.env` file** with API keys:
   ```bash
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_API_KEY=AIza...
   DEEPSEEK_API_KEY=sk-...
   ```

2. **Review `config.yaml`** (defaults provided in `config.example.yaml`):
   ```yaml
   llm:
     default_model: "gpt-4o"
     consensus_mode: true
   
   scan:
     mode: "standard"                # quick, standard, deep, stealth
     timeout: 1800                   # seconds per tool
     max_concurrent_tools: 5
   
   sandbox:
     enabled: true                   # run tools inside Docker
     image: "bbh/sandbox:latest"     # sandbox image name
     cpu_limit: 1.0                  # CPU cores
     memory_limit: "1g"              # Memory allocation
     network: "none"                 # Network isolation
   
   tools:
     discovery:
       subfinder:
         enabled: true
     hosts:
       nmap:
         enabled: true
   
   reporting:
     formats: ["markdown", "json", "csv"]
   
   ci:
     enabled: false
   ```

3. **Verify system health**:
   ```bash
   python main.py --health
   ```

---

## 📊 Tool Matrix  

### Complete Tool Inventory (50+)

| Category | Count | Key Tools | Purpose |
|----------|-------|-----------|---------|
| **OSINT** | 7 | `gau`, `waymore`, `whois`, `shodan` | General intelligence |
| **Subdomains** | 14 | `subfinder`, `crt.sh`, `dnsx`, `puredns` | Enumeration |
| **Hosts** | 8 | `naabu`, `httpx`, `ipinfo`, `cdncheck` | Port scanning |
| **Web** | 18 | `katana`, `ffuf`, `jsluice`, `urless` | Web reconnaissance |
| **Vuln** | 12 | `nuclei`, `sqlmap`, `ghauri`, `commix` | Exploitation |
| **GitHub** | 6 | `trufflehog`, `gitleaks`, `gato` | Secret detection |
| **Cloud** | 3 | `cloud_enum`, `s3scanner` | Cloud misconfig |
| **API** | 5 | `swagger-spy`, `swaggerator` | API discovery |
| **Misconfig** | 3 | Various | Config analysis |

---

## 💻 Usage Examples

### Basic Scan
```bash
python main.py --target example.com
```

### Advanced: Deep Scan with Verbose Output
```bash
python main.py --target example.com \
  --mode deep \
  --verbose
```

### CI/CD Integration
```bash
python main.py --target example.com \
  --ci \
  --non-interactive
```

### Custom Configuration
```bash
python main.py --target example.com \
  --config custom-config.yaml \
  --verbose
```

### System Verification
```bash
python main.py --health                    # Health check
```

---

## 📈 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Scan Startup** | 2-5s | Docker container boot |
| **Phase A (Discovery)** | 5-15 min | Subdomain enumeration |
| **Phase B (Enrichment)** | 10-30 min | Port & service scanning |
| **Phase C (Web Recon)** | 5-20 min | Endpoint discovery |
| **Phase D (Exploitation)** | 15-60 min | Vuln testing |
| **Phase E (Reporting)** | 2-5 min | Report generation |
| **Total (Full Scan)** | 1-2 hours | For medium targets |
| **Concurrent Tools** | 5 (default) | Configurable |
| **Memory Usage** | 0.5-2 GB | Depends on target size |
| **Docker Image** | ~2 GB | bbh/sandbox |

---

## 📁 Project Structure

```
bbh-ai/
├── agent_controller.py          # AI agent orchestration
├── orchestrator.py               # Phase workflow manager
├── main.py                       # CLI entry point
├── health.py                     # Diagnostic tool
│
├── engine/
│   ├── analyzer.py              # Vulnerability analysis
│   ├── auto_healer.py           # Error recovery
│   ├── storage.py               # Atomic file operations
│   └── tci.py                   # Threat Confidence Index
│
├── sandbox/
│   ├── server.py                # FastAPI sandbox server
│   ├── client.py                # Docker manager
│   ├── Dockerfile.sandbox       # Container definition
│   └── primitives/              # Browser, terminal, proxy
│
├── tools/                        # 50+ security tool wrappers
│   ├── registry.py              # Tool discovery
│   ├── base.py                  # Base interface
│   └── wrappers/                # Tool implementations
│
├── tasks/                       # Celery distributed tasks
│   ├── phase_tasks.py
│   ├── recon_tasks.py
│   └── vuln_tasks.py
│
├── memory/
│   └── graph.py                 # Knowledge graph
│
├── telemetry/
│   └── logger.py                # Execution logging
│
├── reporting/
│   └── generator.py             # Report generation
│
├── validation/
│   └── validator.py             # Finding validation
│
├── ci/
│   └── notifier.py              # CI/CD integration
│
├── config.yaml                  # Configuration
├── config.example.yaml          # Config template
├── requirements.txt             # Dependencies
├── docker-compose.yml           # Docker setup
├── installer.sh                 # Installer
├── rebuild_docker.py            # Docker rebuild
├── README.md                    # Documentation
└── LICENSE                      # MIT License
```

---

## 🔐 Security & Privacy

- ✅ **Local-First**: All scan data stored in `runs/<run-id>/` directory
- ✅ **No External DBs**: No third-party persistence, no data exfiltration
- ✅ **Container Isolation**: Docker containers run with minimal privileges
- ✅ **Encrypted Configs**: API keys stored in `.env`, never in code
- ✅ **Audit Logs**: Complete execution telemetry in logs

---

## 🤝 Contributing

BBH-AI welcomes contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Pull request process
- Tool wrapper template

---

## 📄 License

BBH-AI is licensed under the MIT License. See [LICENSE](LICENSE) for details.

**⚠️ Disclaimer**: Unauthorized security testing is illegal. Use BBH-AI only on targets you own or have explicit permission to test. The developers assume no liability for misuse.

---

## 🙋 Support

- **Issues**: GitHub Issues for bug reports and feature requests
- **Documentation**: See repository documentation
- **Security**: Report vulnerabilities responsibly

---

**Built with ♥ by [gl1tch0x1](https://github.com/gl1tch0x1)** 🏹