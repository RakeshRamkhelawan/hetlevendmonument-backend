"""
SC-11.1: Dependency Injection Container
Simple DI container for managing service dependencies.
"""

import inspect
import logging
from functools import wraps
from typing import Any, Optional, TypeVar, cast
from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DIContainer:
    """
    SC-11.1: Lightweight Dependency Injection Container.

    Features:
    - Singleton and transient service registration
    - Automatic dependency resolution
    - Factory function support
    - Scoped services
    """

    def __init__(self) -> None:
        self._services: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._singletons: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._scoped: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def register(
        self,
        service_type: type[T],
        implementation: type[T] | None = None,
        singleton: bool = True,
        factory: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        name: str | None = None,
    ) -> "DIContainer":
        """
        Register a service.

        Args:
            service_type: The interface/base type
            implementation: The concrete implementation
            singleton: Whether to create only one instance
            factory: Factory function to create instances
            name: Optional name for multiple implementations

        Returns:
            Self for chaining
        """
        key = self._get_key(service_type, name)

        self._services[key] = {
            "type": service_type,
            "implementation": implementation or service_type,
            "singleton": singleton,
            "factory": factory,
        }

        logger.debug(f"Registered service: {key} (singleton={singleton})")
        return self

    def register_instance(
        self, service_type: type[T], instance: T, name: str | None = None
    ) -> "DIContainer":
        """Register an existing instance as a singleton."""
        key = self._get_key(service_type, name)

        self._services[key] = {
            "type": service_type,
            "implementation": type(instance),
            "singleton": True,
            "factory": None,
        }
        self._singletons[key] = instance

        logger.debug(f"Registered instance: {key}")
        return self

    def resolve(self, service_type: type[T], name: str | None = None) -> T:
        """
        Resolve a service instance.

        Args:
            service_type: The type to resolve
            name: Optional name for named registrations

        Returns:
            Service instance
        """
        key = self._get_key(service_type, name)

        if key not in self._services:
            raise KeyError(f"Service not registered: {key}")

        config = self._services[key]

        # Return singleton if exists
        if config["singleton"] and key in self._singletons:
            return cast(T, self._singletons[key])

        # Create instance
        if config["factory"]:
            instance = config["factory"]()
        else:
            instance = self._create_instance(config["implementation"])

        # Store singleton
        if config["singleton"]:
            self._singletons[key] = instance

        return cast(T, instance)

    def _create_instance(self, implementation: type[T]) -> T:
        """Create an instance with automatic dependency injection."""
        # Get constructor parameters
        sig = inspect.signature(implementation.__init__)
        params: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Try to resolve parameter type
            if param.annotation != inspect.Parameter.empty:
                try:
                    params[param_name] = self.resolve(param.annotation)
                except KeyError:
                    if param.default != inspect.Parameter.empty:
                        params[param_name] = param.default
                    else:
                        raise

        return implementation(**params)

    def _get_key(self, service_type: type[Any], name: str | None = None) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate unique key for a service."""
        type_name = f"{service_type.__module__}.{service_type.__name__}"
        return f"{type_name}:{name}" if name else type_name

    def has(self, service_type: type[Any], name: str | None = None) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if a service is registered."""
        key = self._get_key(service_type, name)
        return key in self._services

    def clear(self) -> None:
        """Clear all registrations and instances."""
        self._services.clear()
        self._singletons.clear()
        self._scoped.clear()


# Global container instance
container = DIContainer()


def inject(service_type: type[T], name: str | None = None) -> T:
    """
    Decorator/function for dependency injection.

    Usage:
        # As function
        db = inject(DatabaseService)

        # In class
        class MyService:
            db: DatabaseService = inject(DatabaseService)
    """
    return container.resolve(service_type, name)


def injectable(cls: type[T]) -> type[T]:
    """
    Decorator to mark a class as injectable and auto-register it.

    Usage:
        @injectable
        class MyService:
            def __init__(self, db: DatabaseService) -> None:
                self.db = db
    """
    container.register(cls, cls, singleton=True)
    return cls


def provide(service_type: type[T], name: str | None = None) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to inject dependencies into a function.

    Usage:
        @provide(DatabaseService)
        def my_function(db: DatabaseService):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            instance = container.resolve(service_type, name)
            return func(instance, *args, **kwargs)

        return wrapper

    return decorator
