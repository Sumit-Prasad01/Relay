"""Application entry point and lifecycle orchestrator."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from Relay.config.loader import load_config
from Relay.config.schemas import RootConfig
from Relay.storage.database import Database
from Relay.storage.event_store import EventStore
from Relay.storage.session_store import SessionStore
from Relay.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


@dataclass
class AppContext:
    config: RootConfig
    workspace_root: Path
    db: Database
    session_store: SessionStore
    event_store: EventStore


def create_app_context(
    workspace_root: Optional[Path] = None,
    config_override_path: Optional[Path] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    debug: bool = False,
) -> AppContext:
    """Initialize application context, configuration, logging, and database."""
    resolved_workspace = (workspace_root or Path.cwd()).resolve()

    cfg = load_config(
        workspace_root=resolved_workspace,
        config_path=config_override_path,
        cli_provider=provider,
        cli_model=model,
        cli_api_key=api_key,
    )

    configure_logging(debug=debug)
    logger.debug(
        "Application context initializing",
        extra={
            "workspace": str(resolved_workspace),
            "provider": cfg.default_provider,
            "model": cfg.default_model,
        },
    )

    db_path = Path(cfg.storage.database_path).expanduser().resolve()
    db = Database(db_path)
    db.run_migrations()

    session_store = SessionStore(db)
    event_store = EventStore(db)

    return AppContext(
        config=cfg,
        workspace_root=resolved_workspace,
        db=db,
        session_store=session_store,
        event_store=event_store,
    )
