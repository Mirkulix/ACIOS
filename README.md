# AICOS - AI Company OS

**Run an entire company with AI agents.** AICOS is a framework that simulates a fully autonomous AI-powered company where specialized AI agents (CEO, CTO, CFO, Sales, Marketing, Developer, Support, Operations, HR) collaborate, communicate, and execute real business workflows -- all orchestrated by a central engine and powered by Claude (Anthropic).

---

## How It Works

```
                        ┌─────────────────────┐
                        │    Web Dashboard     │
                        │   (FastAPI + WS)     │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │    Orchestrator      │
                        │  (Task Routing,      │
                        │   Auto-Assignment,   │
                        │   Escalation)        │
                        └──────────┬──────────┘
                                   │
          ┌────────┬───────┬───────┼───────┬────────┬──────────┐
          ▼        ▼       ▼       ▼       ▼        ▼          ▼
       ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐  ┌──────┐
       │ CEO │ │ CTO │ │ CFO │ │Sales│ │ Dev │ │Mktg │  │ ...  │
       └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘  └──────┘
          │        │       │       │       │        │
          └────────┴───────┴───────┼───────┴────────┘
                                   │
                        ┌──────────▼──────────┐
                        │   Shared State      │
                        │  (Tasks, KPIs,      │
                        │   Messages, Memory) │
                        └─────────────────────┘
```

**One command starts everything** -- Orchestrator, all 9 agents, and the web dashboard run in a single unified process sharing memory. No file sync, no multi-process coordination.

---

## Features

### AI Agents (9 Roles)
| Agent | Role | Responsibility |
|-------|------|----------------|
| **CEO** | Strategy & Decisions | Sets priorities, approves proposals, resolves escalations |
| **CTO** | Technical Leadership | Architecture design, code review, sprint planning, security |
| **CFO** | Finance | Budgets, invoicing, MRR tracking, unit economics |
| **Sales** | Revenue | Lead qualification, proposals, pipeline management |
| **Marketing** | Growth | Content creation, campaigns, SEO, social media |
| **Developer** | Engineering | Code implementation, testing, deployment |
| **Support** | Customer Success | Ticket management, knowledge base, NPS tracking |
| **Operations** | Coordination | Project management, resource allocation, SLA monitoring |
| **HR** | Talent | Recruiting, onboarding, training management |

Each agent has its own system prompt, tool set, and model configuration. Agents communicate via an internal message bus and can escalate decisions to the CEO.

### Orchestrator
- **Auto-assignment** -- routes tasks to the best-matching agent based on keyword analysis and current workload
- **Concurrency control** -- semaphore-based parallel task execution with configurable limits
- **Retry with backoff** -- automatic retries on LLM failures with exponential backoff
- **Escalation chain** -- failed tasks escalate to the CEO after configurable retries
- **Backpressure** -- rejects new tasks when the queue exceeds capacity

### Tool Calling
Agents use the Anthropic Tool Calling API. Each role has specialized tools (e.g., `write_code`, `deploy`, `manage_budget`, `qualify_lead`) that execute against the shared state, CRM, and integrations.

### Workflows
10 pre-built multi-step workflows that chain agent actions:

| Workflow | Description |
|----------|-------------|
| `client_onboarding` | Lead qualification through contract signing |
| `project_delivery` | Architecture to deployment pipeline |
| `content_pipeline` | Content creation and publishing |
| `support_escalation` | Ticket handling with auto-escalation |
| `ai_solution_delivery` | Customer request to AI solution delivery |
| `cross_sell_pipeline` | Cross-selling between business units |
| `ki_feature_development` | AI feature development pipeline |
| `compliance_audit` | Compliance audit process |
| `trial_conversion` | SaaS trial-to-paid conversion |
| `partner_integration` | Partner API integration onboarding |

### Web Dashboard
Real-time monitoring UI built with FastAPI, WebSockets, and vanilla JS:
- Live agent status and activity feed
- Task management (create, view, track)
- KPI monitoring
- Workflow triggering
- Communication logs and reports
- Optional HTTP Basic Auth

### Persistence
- SQLite-backed storage for tasks and KPIs (survives restarts)
- In-memory shared state with observer pattern for real-time WebSocket push
- Communication logs saved as JSONL files

### Company Templates
Pre-configured setups for different business types:
- `agency` -- Creative/digital agency
- `saas` -- SaaS product company
- `consulting` -- Consulting firm
- `dev_shop` -- Software development shop
- `marketing_agency` -- Marketing agency

---

## Quick Start

### Prerequisites
- Python 3.11+
- An [Anthropic API Key](https://console.anthropic.com/)

### Installation

```bash
# Clone the repository
git clone https://github.com/Mirkulix/ACIOS.git
cd ACIOS

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your Anthropic API key
# ANTHROPIC_API_KEY=sk-ant-...
```

### Run

```bash
# Start the entire company (Orchestrator + Agents + Dashboard)
python main.py

# Start without dashboard
python main.py --no-dashboard

# Use a custom config
python main.py --config config/company.yaml
```

The dashboard will be available at **http://localhost:8080**.

### CLI

```bash
# Install as CLI tool
pip install -e .

# Show company status
aicos status

# List all agents
aicos agents

# Submit a task
aicos task "Develop a landing page for our new product" --priority high

# List available workflows
aicos workflow list

# Run a workflow
aicos workflow run client_onboarding

# Initialize a new company config interactively
aicos init
```

### Docker

```bash
# Build and run with Docker Compose
docker compose up --build
```

---

## Project Structure

```
ACIOS/
├── main.py                  # Entry point -- boots everything in one process
├── aicos/
│   └── cli.py               # Typer-based CLI (aicos command)
├── agents/
│   ├── base.py              # BaseAgent class with LLM integration
│   ├── factory.py           # Agent factory
│   └── roles/               # Role-specific agent implementations
│       ├── ceo_agent.py
│       ├── cto_agent.py
│       ├── cfo_agent.py
│       ├── developer_agent.py
│       ├── sales_agent.py
│       ├── marketing_agent.py
│       ├── support_agent.py
│       ├── operations_agent.py
│       └── hr_agent.py
├── core/
│   ├── orchestrator.py      # Central controller (task routing, LLM calls)
│   ├── state.py             # SharedState singleton with observer pattern
│   ├── models.py            # Pydantic models (Task, KPI, Message, etc.)
│   ├── communication.py     # Inter-agent message bus
│   ├── memory.py            # Agent memory and knowledge store
│   ├── persistence.py       # SQLite persistence layer
│   ├── tools.py             # Tool definitions and executor
│   └── config_loader.py     # YAML config parser
├── dashboard/
│   ├── app.py               # FastAPI app with REST + WebSocket APIs
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS and JavaScript
├── workflows/
│   ├── engine.py            # Workflow execution engine
│   └── definitions/         # 10 YAML workflow definitions
├── integrations/
│   ├── manager.py           # Integration manager
│   ├── crm.py               # CRM integration (SQLite-backed)
│   └── email_integration.py # Email integration (SMTP/IMAP)
├── config/
│   ├── company.yaml         # Main company configuration
│   └── templates/           # Business type templates
├── tests/                   # pytest test suite
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Configuration

The company is configured via `config/company.yaml`. Key sections:

```yaml
company:
  name: "Your Company"
  type: "agency"              # agency | saas | consulting | dev_shop | custom

agents:
  ceo:
    enabled: true
    model: "claude-sonnet-4-5-20250929"
    system_prompt: "..."      # Role-specific instructions
    tools: [delegate_task, review_report, ...]

workflows:
  - client_onboarding
  - project_delivery

orchestration:
  max_concurrent_tasks: 15
  task_timeout_minutes: 30
  escalation_threshold: 3     # Escalate after N failures
  decision_mode: "autonomous" # autonomous | supervised | hybrid
```

---

## Tech Stack

- **LLM**: Claude (Anthropic) with Tool Calling API
- **Backend**: Python 3.11+, asyncio
- **Web**: FastAPI, Uvicorn, WebSockets, Jinja2
- **Storage**: SQLite (aiosqlite), JSON/JSONL logs
- **CLI**: Typer + Rich
- **Config**: YAML (PyYAML) + Pydantic validation
- **Container**: Docker + Docker Compose

---

## License

This project is proprietary. All rights reserved.
