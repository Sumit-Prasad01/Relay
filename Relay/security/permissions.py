"""Permission policy evaluation across execution modes (Section 9.1)."""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional, Tuple

from Relay.security.command_policy import CommandPolicy, CommandRisk

PermissionMode = Literal["plan", "ask", "auto-edit", "full-auto"]


class PermissionAction(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionManager:
    """Authoritative gatekeeper evaluating tool operations against policy and active mode."""

    def __init__(self, workspace_root: Path, mode: PermissionMode = "ask"):
        self.workspace_root = workspace_root.resolve()
        self.mode: PermissionMode = mode

    def check_file_path(self, target_path: Path) -> bool:
        """Verify target path is strictly within the workspace root (prevent path traversal)."""
        try:
            resolved = target_path.resolve()
            return resolved == self.workspace_root or resolved.is_relative_to(self.workspace_root)
        except Exception:
            return False

    def evaluate_tool(
        self,
        tool_name: str,
        category: str,  # read, write, execute, git
        arguments: dict,
    ) -> Tuple[PermissionAction, Optional[str]]:
        """Determine whether tool invocation is allowed, needs human approval, or is denied."""
        # 1. Plan mode: Absolutely no mutations or command executions
        if self.mode == "plan":
            if category in ("write", "execute", "git"):
                return PermissionAction.DENY, f"Operation denied: session is in 'plan' mode (read-only)."
            return PermissionAction.ALLOW, None

        # 2. Filesystem path containment check
        path_arg = arguments.get("path") or arguments.get("file")
        if path_arg:
            target = Path(path_arg)
            if not target.is_absolute():
                target = self.workspace_root / target
            if not self.check_file_path(target):
                return PermissionAction.DENY, f"Path traversal blocked: target '{path_arg}' escapes workspace root."

        # 3. Read operations are always silently allowed
        if category == "read":
            return PermissionAction.ALLOW, None

        # 4. Command execution policy
        if tool_name == "run_command":
            cmd = arguments.get("command", "")
            risk, _ = CommandPolicy.classify(cmd)

            if risk == CommandRisk.PRIVILEGED:
                return PermissionAction.DENY, f"Blocked privileged operation (sudo/admin): '{cmd}'."
            if risk == CommandRisk.DESTRUCTIVE:
                return PermissionAction.ASK, f"High-risk destructive command: '{cmd}'."
            if risk == CommandRisk.NETWORK:
                if self.mode == "full-auto":
                    return PermissionAction.ALLOW, None
                return PermissionAction.ASK, f"Network operation: '{cmd}'."
            if risk == CommandRisk.READ_ONLY:
                return PermissionAction.ALLOW, None
            if risk == CommandRisk.MUTATION:
                if self.mode in ("auto-edit", "full-auto"):
                    return PermissionAction.ALLOW, None
                return PermissionAction.ASK, f"Command with side effects: '{cmd}'."
            # UNKNOWN risk
            if self.mode == "full-auto":
                return PermissionAction.ALLOW, None
            return PermissionAction.ASK, f"Command requires approval: '{cmd}'."

        # 5. File modifications (write, edit, patch)
        if category == "write":
            if self.mode in ("auto-edit", "full-auto"):
                return PermissionAction.ALLOW, None
            return PermissionAction.ASK, f"Modify file: '{path_arg}'."

        # 6. Git mutations (git_commit, git_branch)
        if category == "git":
            if self.mode == "full-auto":
                return PermissionAction.ALLOW, None
            return PermissionAction.ASK, f"Git mutation: {tool_name}."

        return PermissionAction.ASK, f"Action requires approval: {tool_name}."
