# BBH-AI: Multi-Agent AI-Orchestrated Security Testing Engine

bbh-ai is an advanced bug bounty automation framework that uses multiple AI agents to plan, execute, and validate security tests. It integrates industry-standard tools, runs exploits in isolated Docker sandboxes, and generates comprehensive reports suitable for CI/CD pipelines.

## Features

- Multi-agent orchestration (Planner, Recon, Exploit, Reporter)
- LLM integration (OpenAI, Anthropic, Google, DeepSeek)
- Sandboxed execution of dangerous tools
- Technology stack detection (Wappalyzer)
- JavaScript parsing for endpoint discovery
- Structured attack surface preparation
- AI-assisted false positive reduction
- CI/CD ready with exit codes and webhook alerts
- Modular tool registry for easy extension

## Installation

1. **Clone the repository:**
   ```bash
   git clone git clone https://github.com/gl1tch0x1/bbh_ai.git
   cd bbh-ai

**Run the installer as root:**
```bash
sudo ./installer.sh
```
Activate the Python virtual environment:
```bash
source venv/bin/activate
```
Edit config.yaml to add your LLM API keys and adjust settings.

## **Usage**
```bash
python main.py --target example.com --mode deep
```
For CI mode (exit codes, no prompts):

```bash
python main.py --target https://github.com/org/repo.git --ci
```
## Output
Results are stored in runs/run_YYYYMMDD_HHMMSS/:

* report.md – Markdown summary

* findings.json – Structured JSON

* vulnerabilities.csv – CSV for spreadsheets

* telemetry.json – Performance logs

## Adding New Tools
* Create a new Python file in tools/wrappers/ following the existing pattern.

* Implement a class with name, input_schema, __init__, and run method.

* The tool will be automatically loaded by the registry.

* Architecture
See the detailed design document for full architecture description.

## Future Enhancements
We envision BBH‑Auto evolving into a comprehensive, community‑driven platform. The following enhancements are planned or open for contribution:

1. 🧠 Agent Capabilities:

      * Hierarchical Task Decomposition – Agents break down complex goals into sub‑tasks and coordinate.
      * Self‑Improvement Loop – Agents learn from past scans to refine strategies.
     * Multi‑Model Ensemble – Use multiple LLMs and vote on decisions to reduce bias.
    * Fine‑Tuned Security Models – Custom models trained on vulnerability data.


2. 🔧 Tool Integrations
    * Mobile App Testing – Add apkleaks, mobsf, objection for Android/iOS.
    * Cloud Security – Integrate prowler, scoutsuite for AWS/Azure/GCP.
    * GraphQL Testing – Tools like graphql-map, inql.
    * Blockchain/Smart Contracts – slither, mythril.
    * Network Level – nmap, masscan already present, but deeper integration with metasploit for exploitation.


3. 🧪 Advanced Validation
   * Dynamic Payload Mutation – Fuzz validated findings with variants.
   * Out‑of‑Band Detection – Integrate interactsh for blind vulnerabilities.
   * Time‑Based Detection – Detect race conditions, rate‑limiting issues.

4. 🚀 Performance & Scale
   * Distributed Scanning – Spread tasks across multiple sandbox containers.
   * Queue‑Based Architecture – Use Redis/Celery for job management.
   * Database Storage – Store findings in PostgreSQL/Elasticsearch for historical analysis.
   * Web Dashboard – Real‑time monitoring of scans via a React/Next.js UI.


***We welcome contributions! If you’d like to work on any of these items, please open an issue or pull request.***

Happy Hacking! 🎯