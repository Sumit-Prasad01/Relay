# Relay Architecture & System Design Specification

Relay is a provider-agnostic, local-first autonomous AI coding agent designed to operate inside a developer's terminal. It understands codebases, plans and executes multi-step engineering tasks, runs shell commands under strict security controls, diagnoses and repairs failing tests, and persists state across sessions.

This document describes the complete system architecture, package structure, data contracts, security model, context engine, workflow graphs, and runtime execution loops of Relay.

---

## 1. High-Level Architecture Overview

Relay is structured into decoupled, independently testable layers. The core runtime is strictly provider-neutral: changing from a cloud frontier model (e.g., Anthropic Claude 3.5 Sonnet or OpenAI GPT-4o) to a high-speed inference engine (Groq) or a fully local model (Ollama) requires no changes to tools, permissions, context management, or workflow logic.

```mermaid
flowchart TD
    User([Developer / Terminal]) <--> CLI[CLI & Presentation Layer<br/>Relay/cli]
    
    subgraph Core Orchestration
        CLI --> AppCtx[App Bootstrap & Context<br/>Relay/app.py]
        AppCtx --> Runtime[Custom Agent Runtime<br/>Relay/agent]
        AppCtx --> Workflows[LangGraph Workflow Engine<br/>Relay/workflows]
    end

    subgraph Provider Abstraction
        Runtime <--> ProviderFactory[Provider Factory & Registry<br/>Relay/providers]
        Workflows <--> ProviderFactory
        ProviderFactory <--> OpenRouter[OpenRouter Adapter]
        ProviderFactory <--> Groq[Groq Adapter]
        ProviderFactory <--> Anthropic[Anthropic Adapter]
        ProviderFactory <--> OpenAI[OpenAI Adapter]
        ProviderFactory <--> Gemini[Google Gemini Adapter]
        ProviderFactory <--> Ollama[Local Ollama Adapter]
    end

    subgraph Security & Execution
        Runtime --> PermEngine[Permission Manager & Policy<br/>Relay/security]
        PermEngine --> ToolRegistry[Tool Registry & MCP Client<br/>Relay/tools]
        ToolRegistry --> Sandbox[OS Sandbox Runner<br/>Windows / Linux / macOS]
        ToolRegistry --> Snapshot[File Snapshots & Audit<br/>Relay/security/snapshots.py]
    end

    subgraph Context & Intelligence
        Runtime <--> ContextEngine[Context Engine & Compaction<br/>Relay/context]
        ContextEngine --> AST[Tree-sitter AST & BM25 Ranking]
        ContextEngine --> ProjectDisc[Project Discovery & Ignore Rules]
        ContextEngine --> Compactor[Autonomous Compactor Agent]
    end

    subgraph Persistence & Integrations
        Runtime --> Storage[SQLite Storage Engine<br/>WAL Mode & Schema Migrations]
        Workflows --> Storage
        Runtime --> Integrations[Skills & Lifecycle Hooks<br/>Relay/integrations]
    end
```

---

## 2. Package & Layer Decomposition

The codebase is organized into dedicated functional modules under `Relay/`:

| Package / Module | Responsibility | Key Classes & Functions |
| :--- | :--- | :--- |
| **`Relay.agent`** | Custom autonomous agent runtime, streaming turn loop, message conversions, safety stops, and retry policies. | `AgentRuntime`, `AgentLoop`, `AgentState`, `StopConditions`, `RetryPolicy`, `ErrorClassifier` |
| **`Relay.cli`** | Developer CLI commands, interactive REPL, Prompt Toolkit terminal handling, rich output rendering. | `app`, `commands.py`, `display.py`, `prompts.py` |
| **`Relay.config`** | Configuration schemas, YAML loading, OS keyring secret storage, environment variable overrides. | `ConfigLoader`, `AppConfig`, `SecretManager` |
| **`Relay.context`** | Project discovery, AST parsing, BM25 symbol ranking, token budgeting, and transcript compaction. | `ProjectDiscovery`, `ContextBuilder`, `Compactor`, `IgnoreEngine`, `CodeSearch` |
| **`Relay.integrations`** | Extensibility mechanisms: custom markdown skill discovery and lifecycle hook event dispatchers. | `SkillManager`, `HookDispatcher`, `LifecycleEvent` |
| **`Relay.providers`** | Provider-agnostic adapter interfaces, message normalization, capability registries, and vendor implementations. | `BaseProvider`, `LLMProvider`, `CapabilityRegistry`, `ProviderRegistry`, `create_provider` |
| **`Relay.security`** | 4-tier permission modes, shell command risk classification, sandbox execution, and filesystem snapshots. | `PermissionManager`, `CommandPolicy`, `SandboxRunner`, `FileSystemSnapshot`, `ApprovalRecord` |
| **`Relay.storage`** | Local SQLite persistence, WAL configuration, zero-dependency schema migration runner, and session stores. | `Database`, `SessionStore`, `EventStore`, `001_initial_schema.sql` |
| **`Relay.tools`** | Built-in file, terminal, git, search, diagnostics tools, tool registry, and MCP client integration. | `ToolRegistry`, `BaseTool`, `FileSystemTools`, `TerminalTool`, `MCPClient`, `PatchTool` |
| **`Relay.utils`** | Cross-platform utilities, unified exception hierarchy, structured logging, and path sanitization. | `RelayError`, `get_platform_name`, `sanitize_path`, `setup_logging` |
| **`Relay.workflows`** | LangGraph orchestration graphs, specialist subagents (`Analyst`, `Implementer`, etc.), and checkpointing. | `GraphFactory`, `WorkflowState`, `WorkflowCheckpointer`, `SubagentFactory` |

---

## 3. Provider Abstraction & Model Interchangeability

Relay enforces strict normalization: no provider-specific SDK types, headers, or error objects leak into the agent runtime or tools.

### 3.1 Supported Providers Matrix

| Provider | Adapter Class | Primary Models | Capabilities Supported | Authentication |
| :--- | :--- | :--- | :--- | :--- |
| **OpenRouter** | `OpenRouterProvider` | `anthropic/claude-3.5-sonnet`, `deepseek/deepseek-chat` | Streaming, Tool Calling, Structured Outputs | Bearer Token (`OPENROUTER_API_KEY`) |
| **Groq** | `GroqProvider` | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768` | Ultra-fast Streaming, Parallel Tool Calling | Bearer Token (`GROQ_API_KEY`) |
| **Anthropic** | `AnthropicProvider` | `claude-3-5-sonnet-20241022`, `claude-3-5-haiku` | Streaming, Tool Calling, System Prompt, Vision | Header `x-api-key` (`ANTHROPIC_API_KEY`) |
| **OpenAI** | `OpenAIProvider` | `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini` | Streaming, Parallel Tool Calls, Strict JSON | Bearer Token (`OPENAI_API_KEY`) |
| **Google Gemini** | `GeminiProvider` | `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash` | Streaming, Tool Calling, Large Context (1M+) | Query/Header (`GEMINI_API_KEY`) |
| **Ollama** | `OllamaProvider` | `qwen2.5-coder:latest`, `deepseek-coder-v2` | Local Streaming, Tool Calling, Offline Execution | None (Local `http://localhost:11434`) |

### 3.2 Universal Contract Data Model

```mermaid
classDiagram
    class ModelMessage {
        +str role
        +str content
        +List~ToolCall~ tool_calls
        +str tool_call_id
        +str name
    }
    class ToolCall {
        +str id
        +str name
        +str arguments
        +dict parsed_arguments()
    }
    class ModelRequest {
        +str model
        +List~ModelMessage~ messages
        +List~ToolDefinition~ tools
        +float temperature
        +int max_tokens
        +bool stream
    }
    class ModelResponse {
        +str content
        +List~ToolCall~ tool_calls
        +UsageInfo usage
        +str finish_reason
    }
    class ModelEvent {
        +str event_type
        +str text_delta
        +ToolCall tool_call_delta
        +UsageInfo usage
    }
    class ProviderHealth {
        +bool healthy
        +str provider
        +str message
        +List~str~ models
    }

    ModelRequest "1" *-- "many" ModelMessage
    ModelMessage "1" *-- "many" ToolCall
    ModelResponse "1" *-- "many" ToolCall
```

### 3.3 Provider Request/Response Flow

```mermaid
sequenceDiagram
    autonumber
    participant Runtime as Agent Runtime
    participant Adapter as Provider Adapter (e.g. AnthropicProvider)
    participant API as External Provider API (HTTP/SSE)

    Runtime->>Adapter: generate_stream(ModelRequest)
    Adapter->>Adapter: _convert_request(ModelRequest -> Vendor JSON Payload)
    Adapter->>API: POST /messages (stream=true)
    loop SSE Stream Processing
        API-->>Adapter: SSE Chunk (raw JSON)
        Adapter->>Adapter: Parse Vendor Delta -> ModelEvent(text_delta / tool_call_delta)
        Adapter-->>Runtime: Yield ModelEvent
    end
    API-->>Adapter: Final Frame (usage & finish_reason)
    Adapter-->>Runtime: Yield ModelEvent(event_type="turn_complete", usage=UsageInfo)
```

---

## 4. Custom Agent Runtime & Turn Lifecycle

The agent runtime in `Relay/agent` executes an autonomous loop cycling between model inference and tool resolution until completion criteria are met.

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> LoadingContext: User Prompt Received
    LoadingContext --> ModelGeneration: Context Assembled & Budgeted
    
    state ModelGeneration {
        [*] --> StreamingTokens
        StreamingTokens --> AccumulatingToolCalls: Tool Call Tokens Detected
        AccumulatingToolCalls --> ModelComplete: Finish Reason Received
    }

    ModelGeneration --> CheckingStopConditions: Model Completed Turn
    
    state CheckingStopConditions {
        [*] --> ValidateLimits
        ValidateLimits --> StopHalt: Max Iterations / Token Budget Exceeded
        ValidateLimits --> DispatchTools: Has Tool Calls
        ValidateLimits --> StopHalt: No Tool Calls (Finished)
    }

    CheckingStopConditions --> ExecutingTools: DispatchTools
    CheckingStopConditions --> TurnCompleted: StopHalt

    state ExecutingTools {
        [*] --> SecurityEvaluation
        SecurityEvaluation --> UserApprovalGate: Policy Requires Approval
        SecurityEvaluation --> SandboxExecution: Policy Pre-approved
        UserApprovalGate --> SandboxExecution: User Granted
        UserApprovalGate --> RejectionOutput: User Denied
        SandboxExecution --> RecordResult: Tool Returns Output
        RejectionOutput --> RecordResult: Return Rejection Error
    }

    ExecutingTools --> ModelGeneration: Tool Results Appended to Messages
    TurnCompleted --> PersistingState: Save Session & Messages to SQLite
    PersistingState --> Idle: Ready for Next User Input
```

### 4.1 Safety Stop Conditions & Resource Guards

The runtime enforces deterministic guardrails configured via `StopConditions`:
1. **Iteration Limit**: Caps execution at `max_iterations` (default: 30) to prevent infinite reasoning loops.
2. **Tool Call Limit**: Restricts cumulative tool calls per user turn (default: 50).
3. **Timeout Limit**: Wall-clock timeout (default: 300 seconds) terminating unresponsive operations.
4. **Token Budget Limit**: Monitors prompt and completion tokens against user-configured spend ceilings.
5. **Cancellation Signal**: `asyncio.Event` listener enabling immediate, safe abort upon user `Ctrl+C`.

### 4.2 Error Classification & Exponential Backoff

The `ErrorClassifier` maps runtime exceptions into actionable recovery policies:
- **Rate Limit (`429`) / Server Overload (`503`, `529`)**: Triggers `RetryPolicy` with exponential backoff and jitter (`base_delay=1.0s`, `backoff_factor=2.0`, `max_retries=3`).
- **Context Length Exceeded**: Immediately activates the `Compactor` to condense message history.
- **Tool Execution Errors**: Captured and returned to the model as `role="tool"` error messages, giving the agent opportunity to self-diagnose and correct parameters.
- **Authentication Failure (`401`, `403`)**: Non-retryable; immediately surfaces clear instructions to re-enter credentials (`relay provider add <name>`).

---

## 5. Advanced Workflows & LangGraph Integration

For multi-stage or high-complexity software engineering tasks, Relay pairs the custom runtime with structured **LangGraph** workflow graphs (`Relay/workflows`).

### 5.1 Specialist Subagents

Relay provides specialized subagents with strictly bounded tool permissions:

| Subagent | Role | Permitted Tools | Forbidden Actions |
| :--- | :--- | :--- | :--- |
| **Analyst** | Architecture analysis & call-tree inspection | `read_file`, `list_directory`, `search_code`, `find_files` | No file modifications, no shell execution |
| **Implementer**| Code changes & feature creation | `read_file`, `write_file`, `edit_file`, `apply_patch`, `search_code` | No destructive commands, no git push |
| **Tester** | Test authoring & execution | `read_file`, `write_file`, `run_tests`, `get_diagnostics` | No arbitrary terminal execution |
| **Reviewer** | Diff verification & vulnerability scan | `read_file`, `search_code`, `git_diff` | Read-only; cannot alter workspace files |

### 5.2 Workflow Graphs

```mermaid
flowchart TD
    subgraph Plan and Execute Workflow
        P1[User Goal] --> P2[Planner Subagent]
        P2 --> P3{Review Plan}
        P3 -->|Approved| P4[Execution Subagent]
        P4 --> P5{Verification}
        P5 -->|Pass| P6[Completed]
        P5 -->|Fail| P2
    end

    subgraph Test and Repair Workflow
        T1[Test Failure Detected] --> T2[Tester: Diagnose Failure]
        T2 --> T3[Implementer: Targeted Patch]
        T3 --> T4[Tester: Run Tests]
        T4 -->|Pass| T5[Verified Fix]
        T4 -->|Fail & Iterations < Max| T2
        T4 -->|Fail & Iterations >= Max| T6[Halt & Escalate to User]
    end
```

### 5.3 Checkpointing & SQLite State Management

Every workflow node transition writes a checkpoint to the `workflow_runs` table:
- **Resumability**: Interrupted workflows can be resumed from the exact state of the last successful node.
- **Side-Effect Detection**: Prevents accidental re-execution of side-effecting operations (file edits or commands) when resuming a run.

---

## 6. Security Architecture & Sandbox Boundary

Security in Relay is governed by the `PermissionManager`, which evaluates every operation against workspace boundaries and command risk profiles.

```mermaid
flowchart TD
    ToolCall[Model Tool Call Request] --> ModeCheck{Active Permission Mode}

    ModeCheck -->|plan| PlanGate{Is Tool Read-Only?}
    PlanGate -->|Yes| AllowExec[Allow Execution]
    PlanGate -->|No| BlockPlan[Block: Plan mode permits reads only]

    ModeCheck -->|ask| AskGate{Risk Classification}
    AskGate -->|Read-Only| AllowExec
    AskGate -->|Mutation / Network / Destructive / Unknown| PromptUser[Prompt User Approval (y/n)]
    PromptUser -->|User Approved| AllowExec
    PromptUser -->|User Denied| BlockAsk[Return User Denial Error]

    ModeCheck -->|auto-edit| AutoGate{Is In-Workspace Edit?}
    AutoGate -->|Yes| AllowExec
    AutoGate -->|Terminal / Network / Destructive| PromptUser

    ModeCheck -->|full-auto| FullGate{Is Destructive or Credential?}
    FullGate -->|Destructive / Credential Sensitive| PromptUser
    FullGate -->|Standard Development Action| AllowExec

    AllowExec --> Sandbox[OS Sandbox Execution Boundary]
    Sandbox --> Snapshot[Record Filesystem Snapshot Hash]
```

### 6.1 Four-Tier Permission Modes

1. **`plan` (Inspection Only)**: Read-only operations allowed (`read_file`, `search_code`, `list_directory`, `git_status`). Any mutation attempt is immediately blocked.
2. **`ask` (Default)**: Safe inspection runs automatically; file modifications and terminal commands require user interactive confirmation.
3. **`auto-edit` (Autonomous Coding)**: Files within the workspace boundary can be edited or written without prompting; external access, package installation, network calls, and destructive operations still require confirmation.
4. **`full-auto` (Opt-in Unattended)**: Executes non-destructive coding and test workflows without prompt; highly destructive commands (`rm -rf`, disk writes, credential access) remain gated.

### 6.2 Command Risk Classification (`CommandPolicy`)

The `CommandPolicy` engine classifies shell commands using lexical parsing rather than simplistic substring matching:
- **Read-Only**: `ls`, `dir`, `cat`, `head`, `tail`, `grep`, `rg`, `git status`, `git diff`, `git log`.
- **Workspace Mutation**: `pytest`, `python -m pytest`, code formatters (`black`, `ruff`, `prettier`).
- **Network Operations**: `curl`, `wget`, `npm install`, `pip install`, `git fetch`.
- **Destructive**: `rm`, `del`, `format`, `dropdb`, `git reset --hard`, `git push --force`.
- **Privileged**: `sudo`, `chmod`, `chown`, `systemctl`, `reg`.

### 6.3 Platform-Native Sandbox Runners

| OS | Sandbox Isolation Mechanism | Default Boundaries |
| :--- | :--- | :--- |
| **Windows** | Isolated Subprocess + Process Trees + VirtualEnv PATH Injection | Restricted working directory, inheritance of virtualenv `Scripts`, termination of child process trees via `taskkill /F /T`. |
| **Linux** | Bubblewrap (`bwrap`) Namespaces | Unshared network namespace (`--unshare-net`), read-only root mounts, isolated `/tmp`, restricted writable workspace. |
| **macOS** | Seatbelt Sandbox Profiles (`sandbox-exec`) | Fine-grained Seatbelt profiles blocking unrequested file writes and outbound network sockets. |

---

## 7. Context Engineering & Compaction Engine

Relay avoids indiscriminate context dumping by combining on-demand discovery, BM25 symbol ranking, and autonomous transcript compaction.

```mermaid
flowchart TD
    subgraph Context Assembly
        Discovery[Project Discovery: Manifests, Frameworks, AGENTS.md] --> BudgetManager[Token Budget Allocator]
        Search[Code Search & Tree-sitter AST] --> Ranker[BM25 Lexical & Symbol Ranker]
        Ranker --> BudgetManager
        BudgetManager --> FinalPrompt[Assembled System & User Context]
    end

    subgraph Dynamic Compaction
        FinalPrompt --> CheckPressure{Prompt > 85% Model Context Window?}
        CheckPressure -- No --> PassToModel[Dispatch to Model Adapter]
        CheckPressure -- Yes --> CompactorAgent[Autonomous Compactor Agent]
        CompactorAgent --> Extract[Extract Goal, Decisions, File Diffs, State]
        Extract --> SummaryBlock[Generate Structured ## Handoff Note]
        SummaryBlock --> Truncate[Preserve System + Summary + Recent Tail]
        Truncate --> PassToModel
    end
```

### 7.1 Dynamic Token Budgeting

For any model, Relay dynamically calculates token allocations:
- **System Instructions & Tool Definitions**: Fixed baseline (~2,500 tokens).
- **Project Discovery & `AGENTS.md`**: Up to 10% of total window.
- **Retrieved Code Snippets**: Up to 30% of total window (ranked by relevance score).
- **Conversation Transcript**: Dynamically managed; triggers compaction at **85%** capacity.
- **Completion Output Reserve**: Preserves 15% of the model's max output limit for generation.

### 7.2 Structured Compaction Handoff

When compaction triggers, history is summarized into a standardized schema:
```markdown
<summary>
## Goal
[Original user request and acceptance criteria]

## What Happened
[Architectural decisions, hypotheses tested, failed approaches eliminated]

## Files Modified
[Full list of paths created, edited, or deleted]

## Current State
[Passing tests, broken components, current error diagnostics]

## Next Step
[Immediate next action required to complete the task]
</summary>
```

---

## 8. Tool Architecture & Model Context Protocol (MCP)

### 8.1 Built-in Tool Suite

Relay includes 12 first-party engineering tools:

| Category | Tool Name | Description | Key Security Check |
| :--- | :--- | :--- | :--- |
| **Filesystem** | `read_file` | Reads file content with optional start/end line bounds. | Path must reside within workspace. |
| | `write_file` | Writes full file content with automatic parent directory creation. | Path must reside within workspace; mode gate. |
| | `edit_file` | Performs exact string replacements within a file. | Single or unique match verification. |
| | `list_directory` | Lists directory entries with recursive depth filtering. | Path traversal blocked. |
| **Patch** | `apply_patch` | Applies unified git-style diffs cleanly to local files. | Rejects out-of-workspace diff headers. |
| **Search** | `search_code` | BM25 and regex search across codebase files. | Honors `.gitignore` and `.relayignore`. |
| | `find_files` | Glob pattern search for file names across the repository. | Honors ignore rules. |
| **Terminal** | `run_terminal_command` | Executes shell commands in the sandbox runner. | Evaluated by `CommandPolicy`. |
| **Testing** | `run_tests` | Automatically discovers and runs project test suites. | Virtualenv discovery and exit-code reporting. |
| | `get_diagnostics` | Inspects test failures, tracebacks, and lint warnings. | Read-only. |
| **Git** | `git_status` | Returns active working tree status and branch info. | Read-only. |
| | `git_diff` | Computes unified git diffs against HEAD or index. | Read-only. |

### 8.2 Model Context Protocol (MCP) Client Integration

Relay acts as an MCP host via `Relay/tools/mcp`:
- **Stdio Transport**: Connects to external MCP servers running as child processes.
- **Dynamic Namespacing**: Discovered tools are namespaced (`mcp__<server_name>__<tool_name>`) to avoid collisions with built-in tools.
- **Unified Security Gating**: MCP tools are subject to the same `PermissionManager` policies as built-in tools.

---

## 9. Persistence & Storage Architecture

Relay uses a local, zero-dependency SQLite database stored in `.relay/relay.db` (or user cache dir).

### 9.1 Entity-Relationship Model

```mermaid
erDiagram
    sessions ||--o{ messages : contains
    sessions ||--o{ tool_calls : records
    sessions ||--o{ file_changes : tracks
    sessions ||--o{ approvals : logs
    sessions ||--o{ workflow_runs : checkpoints
    tool_calls ||--o| tool_results : generates

    sessions {
        string id PK
        string workspace
        string provider
        string model
        string title
        string created_at
        string updated_at
        string status
    }

    messages {
        string id PK
        string session_id FK
        integer sequence
        string role
        string content
        string raw_payload
        string created_at
    }

    tool_calls {
        string id PK
        string session_id FK
        string call_id
        string tool_name
        string arguments
        string status
        integer duration_ms
        string created_at
    }

    tool_results {
        string id PK
        string call_id FK
        string output
        integer exit_code
        string redaction_metadata
        string created_at
    }

    file_changes {
        string id PK
        string session_id FK
        string path
        string before_hash
        string after_hash
        string diff
        string created_at
    }

    approvals {
        string id PK
        string session_id FK
        string action
        string risk
        string decision
        string reason
        string user_scope
        string created_at
    }

    workflow_runs {
        string id PK
        string session_id FK
        string graph_id
        string status
        string checkpoint_ref
        string created_at
        string updated_at
    }

    events {
        string id PK
        string session_id
        string correlation_id
        string event_type
        string payload
        string created_at
    }
```

---

## 10. End-to-End Interaction Trace

```mermaid
sequenceDiagram
    autonumber
    actor User as Developer
    participant CLI as CLI App (app.py)
    participant Runtime as Agent Runtime (runtime.py)
    participant Context as Context Builder (builder.py)
    participant Provider as Provider Adapter (e.g. GroqProvider)
    participant Perm as Permission Engine (permissions.py)
    participant Tools as Tool Execution (tools/registry.py)
    participant DB as SQLite Storage (database.py)

    User->>CLI: relay ask "Fix division by zero in calculator.py"
    CLI->>Runtime: run_task(prompt, workspace)
    Runtime->>DB: create_session(id, workspace, provider, model)
    Runtime->>Context: assemble_context(prompt)
    Context-->>Runtime: Assembled ModelRequest with System & Manifests
    
    loop Turn Resolution Cycle
        Runtime->>Provider: generate_stream(ModelRequest)
        Provider-->>Runtime: Stream ModelEvents (Text & Tool Calls)
        alt Emitted Tool Call (e.g. edit_file)
            Runtime->>Perm: check_permission(tool_call, mode="ask")
            alt Requires User Approval
                Perm->>CLI: Request confirmation prompt
                CLI->>User: "Approve edit_file on calculator.py? [y/N]"
                User-->>CLI: "y"
                CLI-->>Perm: Decision: Approved
            end
            Perm->>Tools: execute_tool(tool_name, args)
            Tools->>Tools: Apply modification in Sandbox
            Tools-->>Runtime: ToolResult(output="Replacement successful")
            Runtime->>DB: record_tool_call & record_file_change
            Runtime->>Runtime: Append ToolResult to message history
        else Finished (finish_reason="stop")
            Runtime->>CLI: Stream final text summary
        end
    end

    Runtime->>DB: update_session_status("completed")
    Runtime-->>CLI: Task completed (unified diff available)
    CLI-->>User: Display summary banner and modified files
```

---

## 11. Architectural Decision Matrix

| Decision Area | Selected Approach | Alternatives Considered | Rational Architecture Trade-off |
| :--- | :--- | :--- | :--- |
| **Agent Runtime** | Custom Python Async Turn Loop | Heavy agent frameworks (CrewAI, AutoGen) | Total transparency over message serialization, zero unwanted abstractions, direct control over stop conditions and streaming. |
| **Workflow Engine**| LangGraph | Custom DAG runner | Standardized checkpointing, cyclic multi-agent graph flows, and robust state serialization. |
| **Persistence** | SQLite with WAL Mode | Flat JSONL files / Postgres | ACID compliance, zero external server dependencies, immediate indexed query performance, foreign key integrity. |
| **Secret Storage** | OS Keyring (`keyring` lib) | Plaintext `.env` files | High security standard across Windows Credential Locker, macOS Keychain, and Linux SecretService. |
| **Context Retrieval**| Tree-sitter AST + BM25 | External Vector DB (Chroma, Pinecone) | Lightweight, instantaneous startup, zero API embedding costs, exact symbol matches for codebases. |
| **Tool Execution** | In-process Registry + OS Sandbox | Container-only (Docker) | Instant execution without Docker overhead, while providing container modes when explicitly requested. |

---

## 12. Cross-Platform Boundary Matrix

| Capability | Windows (Win32) | macOS (Darwin) | Linux (GNU/Linux) |
| :--- | :--- | :--- | :--- |
| **Shell Runner** | PowerShell / `cmd.exe` / Git Bash | `/bin/zsh` or `/bin/bash` | `/bin/bash` or `/bin/sh` |
| **Process Tree Cleanup** | `taskkill /F /T /PID` | `os.killpg(pgid, SIGKILL)` | `os.killpg(pgid, SIGKILL)` |
| **Sandbox Isolation** | VirtualEnv PATH + Subprocess Quotas | Seatbelt (`sandbox-exec`) | Bubblewrap (`bwrap`) Namespaces |
| **Secure Keyring** | Windows Credential Manager | macOS Keychain | SecretService / DBus Keyring |
| **Path Handling** | Windows Long Paths (`\\?\`) & Normalized forward slashes | POSIX standard | POSIX standard |
