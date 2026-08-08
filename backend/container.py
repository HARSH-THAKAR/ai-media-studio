"""Dependency-injection container for application service instances."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Generic, TypeVar, cast

from backend.config import Settings


ServiceType = TypeVar("ServiceType")
ServiceFactory = Callable[[Settings], ServiceType]


class ServiceNotRegisteredError(LookupError):
    """Raised when code requests an unregistered service."""


class ServiceAlreadyRegisteredError(ValueError):
    """Raised when a service type is registered more than once."""


class ServiceCreationError(RuntimeError):
    """Raised when a service factory cannot create its service."""


class ServiceContainer(Generic[ServiceType]):
    """Own lazy service instances constructed with shared application settings."""

    def __init__(self, settings: Settings) -> None:
        """Initialize an empty service registry using the provided settings."""
        self.settings = settings
        self._factories: dict[type[object], ServiceFactory[object]] = {}
        self._services: dict[type[object], object] = {}
        self._logger = logging.getLogger(__name__)

    def register_factory(
        self, service_type: type[ServiceType], factory: ServiceFactory[ServiceType],
    ) -> None:
        """Register a factory that will create one instance of a service."""
        self._assert_not_registered(service_type)
        self._factories[service_type] = cast(ServiceFactory[object], factory)

    def get(self, service_type: type[ServiceType]) -> ServiceType:
        """Return the singleton instance for a registered service type."""
        existing = self._services.get(service_type)
        if existing is not None:
            return cast(ServiceType, existing)
        factory = self._factories.get(service_type)
        if factory is None:
            raise ServiceNotRegisteredError(f"Service is not registered: {service_type}")
        return self._create_service(service_type, factory)

    def close(self) -> None:
        """Close owned services that expose a callable ``close`` method."""
        for service in reversed(list(self._services.values())):
            self._close_service(service)
        self._services.clear()

    def _assert_not_registered(self, service_type: type[object]) -> None:
        if service_type in self._factories or service_type in self._services:
            raise ServiceAlreadyRegisteredError(
                f"Service is already registered: {service_type}",
            )

    def _create_service(
        self, service_type: type[ServiceType], factory: ServiceFactory[object],
    ) -> ServiceType:
        try:
            service = factory(self.settings)
        except Exception as error:
            self._logger.exception("Unable to create service: %s", service_type)
            raise ServiceCreationError(f"Unable to create service: {service_type}") from error
        self._services[service_type] = service
        return cast(ServiceType, service)

    def _close_service(self, service: object) -> None:
        close_method = getattr(service, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                self._logger.exception("Unable to close service: %s", type(service))
