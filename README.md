# BBH-AI — Multi-Agent AI-Orchestrated Security Testing Engine

> **BBH-AI** is an advanced bug bounty automation framework powered by multi-agent AI. It chains security tools together intelligently, runs exploits in isolated Docker sandboxes, and generates structured reports ready for CI/CD pipelines.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![CrewAI](https://img.shields.io/badge/Powered%20by-CrewAI-orange)](https://crewai.com)

---

## ✨ Features

| Feature | Detail |
|---------|--------|
| 🤖 **Multi-Agent Orchestration** | Planner → Recon → Exploit → Reporter pipeline |
| 🧠 **LLM Flexibility** | OpenAI, Anthropic, Google Gemini, DeepSeek |
| 🔒 **Sandboxed Execution** | Dangerous tools run inside isolated Docker containers |
| 🛠️ **11 Integrated Tools** | subfinder, httpx, gau, katana, gospider, nuclei, dalfox, waymore, js_parser, tech_detect + more |
| 📄 **Multi-Format Reports** | Markdown, JSON, CSV with severity tables and PoC blocks |
| 🔁 **CI/CD Ready** | Exit codes (0/1/2), Slack notifications, GitHub Issue creation |
| 🔌 **Extensible** | Drop a new `.py` file in `tools/wrappers/` — registry auto-loads it |
| 🗺️ **Memory Graph** | In-session knowledge graph tracks asset relationships across agents |
| 🔑 **`.env` Support** | Store all API keys in `.env` — never hardcode credentials |

---

## 🏗️ Architecture

```mermaid
graph TB
    CLI["🖥️ main.py\n(CLI Entry Point)"]
    ENV["📄 .env\n(API Keys)"]
    CFG["⚙️ config.yaml\n(Settings)"]

    CLI --> ENV
    CLI --> CFG
    CLI --> ORCH

    subgraph ORCH["🎛️ Orchestrator"]
        direction TB
        VAL_ENV["validate_env()"]
        PREP["_prepare_target()"]
        RUN["agent_controller.run()"]
        REPORT["ReportGenerator"]
        NOTIFY["CINotifier"]
        TEL["Telemetry.save()"]
    end

    PREP --> TOOLS
    RUN --> AGENTS

    subgraph TOOLS["🧰 Tool Registry (Categorized)"]
        direction LR
        subgraph SUB["Subdomains"]
            SF["subfinder"]
        end
        subgraph HST["Hosts"]
            HX["httpx"]
        end
        subgraph OSN["OSINT"]
            GAU["gau"]
            WM["waymore"]
        end
        subgraph WEB["Web Analysis"]
            GS["gospider"]
            JS["js_parser"]
            KAT["katana"]
            TD["tech_detect"]
        end
        subgraph VLN["Vuln Checkers"]
            NC["nuclei"]
            DF["dalfox"]
        end
    end

    subgraph AGENTS["🤖 CrewAI Agent Pipeline"]
        direction LR
        PL["🧭 Planner\n(gpt-4)"]
        RC["🔍 Recon\n(gpt-3.5-turbo)"]
        EX["💥 Exploit\n(gpt-4)"]
        RP["📝 Reporter\n(gpt-4)"]
        PL --> RC --> EX --> RP
    end

    subgraph SANDBOX["🐳 Docker Sandbox"]
        direction TB
        SC["SandboxClient"]
        SV["FastAPI Server\n(:8000)"]
        SC --> SV
    end

    TOOLS --> SANDBOX
    AGENTS --> VALID

    subgraph VALID["✅ Validation"]
        VL["Validator\n(normalise + deduplicate)"]
        MG["MemoryGraph\n(in-session knowledge)"]
    end

    VALID --> REPORT
    REPORT --> OUT

    subgraph OUT["📦 Output — runs/run_YYYYMMDD_HHMMSS/"]
        direction LR
        MD["report.md"]
        JS2["report.json"]
        CSV["report.csv"]
        TJ["telemetry.json"]
    end

    REPORT --> NOTIFY
    NOTIFY --> SLACK["💬 Slack Webhook"]
    NOTIFY --> GH["🐙 GitHub Issues"]
```

---

## 🔄 Scan Workflow

```mermaid
sequenceDiagram
    actor User
    participant CLI as main.py
    participant Orch as Orchestrator
    participant Tools as ToolRegistry
    participant Crew as CrewAI Agents
    participant Sandbox as Docker Sandbox
    participant Report as ReportGenerator
    participant CI as CINotifier

    User->>CLI: python main.py --target example.com --mode deep
    CLI->>CLI: Load .env → expand config.yaml vars
    CLI->>Orch: Orchestrator(config)
    Orch->>Orch: _validate_env() [Docker + API key checks]

    Note over Orch,Tools: Attack Surface Preparation
    Orch->>Tools: subfinder.run(domain)
    Tools-->>Orch: {subdomains: [...]}
    Orch->>Tools: httpx.run(host_list)
    Tools-->>Orch: {results: [live hosts + tech stack]}
    Orch->>Tools: gau.run(domain)
    Tools-->>Orch: {urls: [...]}
    Orch->>Tools: js_parser.run(js_url) × N
    Tools-->>Orch: {endpoints: [...]}
    Orch->>Tools: tech_detect.run(url)
    Tools-->>Orch: {technologies: [...]}

    Note over Orch,Crew: AI Agent Pipeline (CrewAI Sequential)
    Orch->>Crew: crew.kickoff(attack_surface)
    Crew->>Crew: Planner → creates testing plan
    Crew->>Crew: Recon Agent → enriches attack surface
    Crew->>Sandbox: Tool calls via SandboxClient
    Sandbox-->>Crew: Isolated tool results
    Crew->>Crew: Exploit Agent → validates vulnerabilities
    Crew->>Crew: Reporter Agent → assigns severity + PoC

    Note over Orch,Report: Post-Processing
    Orch->>Orch: Validator.validate() + deduplicate()
    Orch->>Report: generate(findings) → .md / .json / .csv
    Orch->>CI: notify(payload) if CI mode
    CI->>CI: POST Slack webhook
    CI->>CI: POST GitHub Issues API
    Orch->>Orch: telemetry.save()

    Report-->>User: runs/run_YYYYMMDD_HHMMSS/
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/gl1tch0x1/bbh_ai.git
cd bbh-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Install Security Tools

```bash
# Run the installer (Linux/macOS)
chmod +x installer.sh && sudo ./installer.sh

# Or install manually
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/lc/gau/v2/cmd/gau@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
go install -v github.com/jaeles-project/gospider@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/hahwul/dalfox/v2@latest
pip install waymore
```

### 3. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` with your real credentials:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
DEEPSEEK_API_KEY=sk-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
GITHUB_TOKEN=ghp_...
```

> ⚠️ **Never commit `.env`** — it is already in `.gitignore`.

### 4. Review `config.yaml`

```bash
cp config.yaml config.yaml.bak   # optional backup
nano config.yaml                  # adjust scan mode, threads, etc.
```

---

## 🖥️ Usage

```bash
# Standard deep scan
python main.py --target example.com --mode deep

# Update BBH-AI from GitHub
python main.py --update

# Quick scan with debug output
python main.py --target example.com --mode quick --verbose

# CI mode — exits with code 0 (clean), 1 (critical), 2 (high)
python main.py --target example.com --ci

# Stealth mode (slower, lower rate-limit)
python main.py --target example.com --mode stealth
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--target` | *(required)* | Domain or URL to scan |
| `--config` | `config.yaml` | Path to config file |
| `--mode` | from config | `quick` / `deep` / `stealth` |
| `--ci` | `false` | CI mode: structured exit codes + notifications |
| `--verbose` | `false` | Enable DEBUG-level logging |
| `--update`, `-u` | `false` | Auto-update from GitHub + update dependencies |

---

## 📦 Output

All results are saved to `runs/run_YYYYMMDD_HHMMSS/`:

```
runs/
└── run_20260302_201835/
    ├── report.md          ← Human-readable Markdown summary
    ├── report.json        ← Machine-readable structured data
    ├── report.csv         ← Spreadsheet-compatible export
    ├── telemetry.json     ← Tool timing, errors, agent logs
    └── subs_for_httpx.txt ← Intermediate recon data
```

### Exit Codes (CI mode)

| Code | Meaning |
|------|---------|
| `0` | No findings, or only medium/low severity |
| `1` | At least one **critical** finding |
| `2` | At least one **high** finding (no critical) |
| `130` | Interrupted by user (Ctrl+C) |
| `3` | Unexpected fatal error |

---

## 🧰 Tool Reference

| Tool | Category | Description |
|------|----------|-------------|
| `subfinder` | recon | Passive subdomain enumeration |
| `httpx` | recon | HTTP probing, tech detection, status codes |
| `gau` | recon | Fetch known URLs from AlienVault, Wayback, etc. |
| `katana` | recon | Active web crawler with JS parsing |
| `gospider` | recon | Spider + sitemap/robots.txt discovery |
| `waymore` | recon | Extended Wayback Machine URL collector |
| `js_parser` | recon | Extracts endpoints from JavaScript files |
| `tech_detect` | recon | Technology fingerprinting via Wappalyzer |
| `nuclei` | exploit/recon | Template-based vulnerability scanner |
| `dalfox` | exploit | XSS parameter scanner |

---

## ➕ Adding New Tools

1. Create `tools/wrappers/mytool.py` following this template:

```python
class MytoolTool:
    name = "mytool"
    categories = ["recon"]           # determines which agents receive this tool
    input_schema = {"target": str}

    def __init__(self, config, workspace, telemetry):
        self.config = config
        self.workspace = workspace
        self.telemetry = telemetry
        self._timeout = (config or {}).get('scan', {}).get('timeout', 60)

    def run(self, target: str) -> dict:
        # ... your implementation ...
        return {"results": [...]}
```

2. **That's it** — `ToolRegistry` auto-discovers and loads it on next run.

---

## 🔧 Configuration Reference

```yaml
# config.yaml
llm:
  default_model: "gpt-4"    # Fallback model if agent doesn't specify one
  temperature: 0.2

scan:
  mode: "deep"              # quick (fast) / deep (thorough) / stealth (slow+quiet)
  threads: 50               # Parallel slots (future)
  rate_limit: 10            # Max tool invocations per second
  timeout: 60               # Seconds per tool subprocess call
  js_file_limit: 20         # Max JS files parsed per scan

sandbox:
  enabled: true             # Set false to run tools directly (no Docker)
  image: "bb-sandbox"       # Docker image name
  network: "none"           # none=fully isolated | bridge=internet access
  memory_limit: "2g"
  cpu_limit: 1.0
  ephemeral: true           # Destroy container after each use

ci:
  enabled: false
  exit_codes: true          # Use structured exit codes for pipeline gates
  slack_webhook: "${SLACK_WEBHOOK_URL}"
  github_token: "${GITHUB_TOKEN}"
  github_repo: "org/repo"   # For auto-opening GitHub Issues
```

---

## 🗺️ Module Map

```mermaid
graph LR
    main["main.py"] --> orch["orchestrator.py"]
    orch --> ac["agent_controller.py"]
    orch --> rg["reporting/generator.py"]
    orch --> tel["telemetry/logger.py"]
    orch --> val["validation/validator.py"]
    orch --> cin["ci/notifier.py"]
    ac --> mg["memory/graph.py"]
    ac --> tr["tools/registry.py"]
    tr --> sw["tools/wrappers/*.py\n(11 tools)"]
    sw --> sc["sandbox/client.py"]
    sc --> ss["sandbox/server.py\n(FastAPI inside Docker)"]
```

---

## 🔮 Roadmap

| Area | Planned Enhancement |
|------|---------------------|
| 🧠 **Agents** | Hierarchical task decomposition; self-improvement loop |
| 📱 **Mobile** | `apkleaks`, `mobsf`, `objection` for Android/iOS |
| ☁️ **Cloud** | `prowler`, `scoutsuite` for AWS/Azure/GCP |
| 🔗 **GraphQL** | `graphql-map`, `inql` |
| ⛓️ **Blockchain** | `slither`, `mythril` for smart contracts |
| 📡 **Out-of-Band** | `interactsh` integration for blind vulnerabilities |
| 🌐 **Dashboard** | Real-time React/Next.js scan monitoring UI |
| 🗄️ **Storage** | PostgreSQL/Elasticsearch for historical scan data |
| 🚀 **Scale** | Redis/Celery queue-based distributed scanning |

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repo and create a feature branch
2. Follow the existing tool wrapper pattern
3. Add `categories`, `FileNotFoundError` handling, and config-driven `timeout`
4. Open a PR — we'll review and merge

---

## ⚠️ Legal Disclaimer

> BBH-AI is intended **only for authorized security testing**. Never scan targets you do not own or have explicit written permission to test. Misuse may violate computer fraud laws. The authors accept no liability for unauthorized or illegal use.

---

*Happy Hacking! 🎯 — Built by [gl1tch0x1](https://github.com/gl1tch0x1)*