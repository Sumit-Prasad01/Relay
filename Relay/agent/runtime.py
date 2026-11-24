"""Agent runtime orchestrator managing session lifecycle, permissions, and execution (Section 7.1)."""

import subprocess
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from Relay.agent.events import AgentEvent
from Relay.agent.loop import AgentLoop
from Relay.agent.messages import deserialize_from_storage
from Relay.agent.state import AgentState
from Relay.app import AppContext, create_app_context
from Relay.context.builder import ContextBuilder
from Relay.context.tokenizer import TokenBudget
from Relay.providers.factory import create_provider
from Relay.security.permissions import PermissionManager
from Relay.security.snapshots import SnapshotManager
from Relay.tools.registry import create_default_registry


class AgentRuntime:
    """Coordinates session lifecycle, tool registries, permission manager, and agent execution."""

    def __init__(
        self,
        app_context: Optional[AppContext] = None,
        workspace_root: Optional[Path] = None,
        permission_manager: Optional[PermissionManager] = None,
    ):
        self.app_context = app_context or create_app_context(workspace_root=workspace_root)
        self.workspace_root = self.app_context.workspace_root
        self.config = self.app_context.config

        # 1. Security and permissions
        self.permission_manager = permission_manager or PermissionManager(
            mode=self.config.permission_mode,
            workspace_root=self.workspace_root,
        )

        # 2. Tool registry
        self.tool_registry = create_default_registry(permission_manager=self.permission_manager)

        # 3. Context builder
        budget = TokenBudget(max_context_tokens=self.config.agent.max_context_tokens)
        self.context_builder = ContextBuilder(workspace_root=self.workspace_root, budget=budget)

        # 4. Snapshots
        self.snapshots = SnapshotManager(workspace_root=self.workspace_root)

        # 5. Base system prompt
        prompts_dir = Path(__file__).parent / "prompts"
        sys_path = prompts_dir / "system.md"
        if sys_path.is_file():
            self.base_system_prompt = sys_path.read_text(encoding="utf-8")
        else:
            self.base_system_prompt = "You are Relay, an autonomous AI software engineering agent."

    def create_session(
        self,
        title: str = "New session",
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AgentState:
        """Create a new persistent conversation session."""
        selected_provider = provider or self.config.default_provider
        p_cfg = self.config.providers.get(selected_provider)
        selected_model = model or (p_cfg.model if p_cfg and p_cfg.model else self.config.default_model)

        session_id = self.app_context.session_store.create_session(
            workspace=self.workspace_root,
            provider=selected_provider,
            model=selected_model,
            title=title,
        )

        self.app_context.event_store.record_event(
            event_type="session_started",
            payload={
                "provider": selected_provider,
                "model": selected_model,
                "title": title,
                "workspace": str(self.workspace_root),
            },
            session_id=session_id,
        )

        return AgentState(
            session_id=session_id,
            workspace_root=self.workspace_root,
            provider_name=selected_provider,
            model_name=selected_model,
        )

    def resume_session(self, session_id: str) -> AgentState:
        """Load an existing session and message history from SQLite."""
        session_data = self.app_context.session_store.get_session(session_id)
        if not session_data:
            raise ValueError(f"Session with ID '{session_id}' not found.")

        raw_messages = self.app_context.session_store.get_messages(session_id)
        messages = [deserialize_from_storage(m) for m in raw_messages]

        state = AgentState(
            session_id=session_id,
            workspace_root=Path(session_data["workspace"]),
            provider_name=session_data["provider"],
            model_name=session_data["model"],
            messages=messages,
            turn_count=len([m for m in messages if m.role == "user"]),
        )
        return state

    async def run_turn(
        self,
        state: AgentState,
        user_input: str,
    ) -> AsyncIterator[AgentEvent]:
        """Run an execution turn on the given session state."""
        p_cfg = self.config.providers.get(state.provider_name)
        provider = create_provider(name=state.provider_name, config=p_cfg)

        loop = AgentLoop(
            provider=provider,
            tool_registry=self.tool_registry,
            context_builder=self.context_builder,
            session_store=self.app_context.session_store,
            event_store=self.app_context.event_store,
            config=self.config,
            base_system_prompt=self.base_system_prompt,
        )

        async for event in loop.run_turn(state=state, user_input=user_input):
            yield event

    def cancel(self, state: AgentState) -> None:
        """Signal cancellation for an active state."""
        state.is_cancelled = True

    def get_diff(self) -> str:
        """Produce working tree unified diff via git."""
        try:
            res = subprocess.run(
                ["git", "diff"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            return res.stdout.strip()
        except Exception:
            return ""

    def summarize_changes(self, state: AgentState) -> Dict[str, Any]:
        """Summarize modifications and resource usage for a completed session or task."""
        return {
            "session_id": state.session_id,
            "turns": state.turn_count,
            "iterations": state.iteration_count,
            "changed_files": list(state.changed_files),
            "tokens": {
                "prompt": state.prompt_tokens_used,
                "completion": state.completion_tokens_used,
                "total": state.total_tokens_used,
            },
            "finish_reason": state.finish_reason,
            "diff": self.get_diff(),
        }
