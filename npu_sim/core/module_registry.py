"""Global IModule factory.

Reference: SPEC-001 §4.
"""

from __future__ import annotations

import jsonschema

from npu_sim.core.errors import (
    DuplicateModuleTypeError,
    InvalidModuleTypeNameError,
    UnknownModuleTypeError,
)
from npu_sim.interfaces.module import MODULE_TYPE_REGEX, IModule


class ModuleRegistry:
    """Global factory. All IModule subclasses register via @register.

    Architecture Elaborator uses ModuleRegistry.create(type_name, config),
    never importing concrete module classes directly. Reference: SPEC-001 §4.
    """

    _registry: dict[str, type[IModule]] = {}

    @classmethod
    def register(cls, module_class: type[IModule]) -> type[IModule]:
        """Decorator. Validates the module_type name and inserts into the registry."""
        key = module_class.module_type()

        if not MODULE_TYPE_REGEX.match(key):
            raise InvalidModuleTypeNameError(
                f"module_type() returned {key!r}; must match "
                f"{MODULE_TYPE_REGEX.pattern} (PascalCase, <=24 chars). "
                f"See SPEC-001 §3.1.1."
            )

        existing = cls._registry.get(key)
        if existing is not None and existing is not module_class:
            raise DuplicateModuleTypeError(
                f"Module type '{key}' already registered by {existing!r}."
            )

        # Also validate that config_schema returns a valid JSON Schema.
        jsonschema.Draft7Validator.check_schema(module_class.config_schema())

        # Capability dependency consistency: depends_on names must exist among declared.
        caps = module_class.declared_capabilities()
        cap_names = {c.name for c in caps}
        for c in caps:
            for dep in c.depends_on:
                if dep not in cap_names:
                    raise InvalidModuleTypeNameError(
                        f"Module {key}: capability {c.name!r} depends on "
                        f"undeclared capability {dep!r}."
                    )

        cls._registry[key] = module_class
        return module_class

    @classmethod
    def create(cls, module_type: str, config: dict) -> IModule:
        """Instantiate and configure a registered module.

        Validates `config` against the class's `config_schema()` before
        instantiating.
        """
        if module_type not in cls._registry:
            raise UnknownModuleTypeError(
                f"Unknown module_type {module_type!r}. "
                f"Registered: {sorted(cls._registry)}"
            )

        module_class = cls._registry[module_type]
        jsonschema.validate(config, module_class.config_schema())
        return module_class()

    @classmethod
    def list_modules(cls) -> list[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def _unregister_for_test(cls, module_type: str) -> None:
        """Test helper. Not part of the public spec API."""
        cls._registry.pop(module_type, None)

    @classmethod
    def _clear_for_test(cls) -> None:
        """Test helper. Wipes the registry; useful between test cases."""
        cls._registry.clear()
