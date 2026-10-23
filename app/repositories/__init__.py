"""
Event Repositories Package.

Exports repository interfaces, storage implementations, and the factory function
responsible for resolving the active storage backend.
"""

from app.config import ConfigurationError, Settings, get_settings
from app.repositories.base import (
    BaseEventRepository,
    DatabaseConnectionError,
    EventNotFoundError,
    RepositoryError,
    RepositoryIntegrityError,
)
from app.repositories.in_memory import InMemoryEventRepository
from app.repositories.postgres import PostgresEventRepository


def create_event_repository(settings: Settings | None = None) -> BaseEventRepository:
    """Create and return an event repository instance based on application configuration.

    Args:
        settings: Application settings instance. Defaults to cached get_settings().

    Returns:
        BaseEventRepository implementation (InMemoryEventRepository or PostgresEventRepository).

    Raises:
        ConfigurationError: If PostgreSQL backend is requested without required configuration
            or if an unsupported storage backend is configured.
    """
    active_settings = settings or get_settings()
    backend = active_settings.storage_backend.lower().strip()

    if backend == "memory":
        return InMemoryEventRepository()

    if backend == "postgres":
        if (
            not active_settings.is_database_configured
            or not active_settings.get_database_url_value()
        ):
            raise ConfigurationError(
                "STORAGE_BACKEND is configured as 'postgres', but DATABASE_URL is missing or empty."
            )
        return PostgresEventRepository(
            database_url=active_settings.get_database_url_value(),
            min_size=active_settings.database_pool_min_size,
            max_size=active_settings.database_pool_max_size,
            timeout=active_settings.database_connection_timeout,
            settings=active_settings,
        )

    raise ConfigurationError(
        f"Unsupported STORAGE_BACKEND: '{active_settings.storage_backend}'. "
        "Permitted options are 'memory' or 'postgres'."
    )


__all__ = [
    "BaseEventRepository",
    "InMemoryEventRepository",
    "PostgresEventRepository",
    "RepositoryError",
    "EventNotFoundError",
    "DatabaseConnectionError",
    "RepositoryIntegrityError",
    "create_event_repository",
]
