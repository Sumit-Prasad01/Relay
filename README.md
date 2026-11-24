# Relay

A provider-agnostic, local-first, BYOK AI coding agent.

Relay operates directly in your terminal, understands your codebase, plans and executes engineering tasks, runs tools, executes tests, and reports changes with unified diffs and audit logs.

---

## Key Features

- **Provider-Agnostic & BYOK:** Works with **Groq**, **OpenAI**, **Anthropic Claude**, **Google Gemini**, **OpenRouter**, or local **Ollama** models.
- **Local-First & Private:** Source files, execution, database state, and credentials remain strictly on your local machine.
- **Robust Security & Permissions:** Strict permission boundaries with 4 modes (`plan`, `ask`, `auto-edit`, `full-auto`), path-traversal prevention, command classification, and pre-write snapshots with unified diff rollbacks.
- **Autonomous Agent Runtime:** Resilient agent execution loop with token budgeting, context compaction, retries with exponential backoff, and full streaming support.
- **Advanced Workflows:** Multi-step workflows including plan-and-execute, parallel specialist subagents, debug-and-repair, and automated code review with SQLite checkpointing.
- **Extensible:** Model Context Protocol (MCP) stdio client, `.agents/skills` discovery, and configurable lifecycle hooks.

---

## Installation & Setup

### Requirements
- Python 3.11 or newer
- Git

### Install via pip / editable
```bash
git clone https://github.com/your-username/relay.git
cd relay
pip install -e .
```

### Verify Environment
Run diagnostics to verify Python version, Keyring secure storage, Git, and SQLite:
```bash
relay doctor
```

---

## Quick Start

### 1. Configure Providers
Add credentials for any supported provider (secrets are stored securely in your OS keyring):
```bash
# Add Groq
relay provider add groq --model llama-3.3-70b-versatile --api-key <YOUR_KEY>

# Add Anthropic
relay provider add anthropic --model claude-3-5-sonnet-20241022 --api-key <YOUR_KEY>

# Add OpenAI
relay provider add openai --model gpt-4o --api-key <YOUR_KEY>

# Test provider connectivity
relay provider test groq
```

### 2. Initialize Workspace
```bash
relay init
```
This generates `.relay/` and an `AGENTS.md` project instruction template.

### 3. Run Tasks

#### Autonomous Execution (`ask`)
```bash
relay ask "Find all unused imports in the codebase and remove them"
```

#### Read-Only Planning (`plan`)
Inspects the repository and generates an execution plan without modifying any files:
```bash
relay plan "Refactor session database queries to use connection pooling"
```

#### Interactive Terminal Session
```bash
relay
```
In an interactive session, you can converse directly with the agent or use slash commands:
- `/help`: Display in-session command guide
- `/diff`: Show working tree unified git diff
- `/status`: Show active provider, model, permissions, and session tokens
- `/permissions [mode]`: Switch between `plan`, `ask`, `auto-edit`, or `full-auto`
- `/sessions`: List previous sessions
- `/export [format]`: Export session transcript to `markdown` or `json`
- `/clear`: Clear terminal display
- `/quit`: Exit interactive session

---

## Configuration & Architecture

Relay loads configuration from:
1. CLI flags (`--provider`, `--model`, `--workspace`)
2. Environment variables (`GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
3. Workspace configuration (`.relay/config.toml`)
4. Global user configuration (`~/.config/relay/config.toml`)

### Permission Modes
- **`plan`**: Read-only exploration. No file mutations or side-effect commands permitted.
- **`ask`** (Default): Reads allowed automatically; writes and external commands prompt for user approval.
- **`auto-edit`**: File writes and patches within the workspace root are automatically allowed; terminal commands still prompt.
- **`full-auto`**: Fully autonomous operation within workspace security constraints.

---

## Testing

Run the automated test suite with pytest:
```bash
pytest
```
