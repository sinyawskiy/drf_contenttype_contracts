from importlib import import_module
from types import ModuleType
from typing import Optional, Tuple

from django.apps import apps as django_apps

from drf_contenttype_contracts.contracts import (
    DEFAULT_SERIALIZER_TYPE,
    ContentTypeContract,
    ContentTypeResource,
    DeclarativeContentTypeContract,
)


def is_contract_class(value) -> bool:
    return (
        isinstance(value, type)
        and issubclass(value, DeclarativeContentTypeContract)
        and value is not DeclarativeContentTypeContract
        and not value.__dict__.get('abstract', False)
    )


def _callable_signature(value):
    if value is None:
        return None
    return (
        getattr(value, '__module__', value.__class__.__module__),
        getattr(value, '__qualname__', getattr(value, '__name__', value.__class__.__qualname__)),
    )


def _serializer_signature(value):
    if isinstance(value, dict):
        return tuple(
            (key, _serializer_signature(item))
            for key, item in sorted(value.items(), key=lambda item: item[0])
        )
    return _callable_signature(value)


def _lifecycle_signature(lifecycle):
    return tuple(
        (hook_name, _callable_signature(getattr(lifecycle, hook_name, None)))
        for hook_name in (
            'before_create',
            'after_create',
            'before_update',
            'after_update',
            'before_delete',
            'after_delete',
        )
    )


def contract_signature(contract):
    return (
        contract.allowed_actions,
        _callable_signature(contract.policy),
        _serializer_signature(contract.serializer_map),
        _serializer_signature(contract.request_serializer_map),
        _serializer_signature(contract.response_serializer_map),
        contract.missing_policy_actions,
        _lifecycle_signature(contract.lifecycle),
    )


class ContentTypeContractRegistry:
    """Explicit allowlist of ContentType-backed API contracts."""

    def __init__(self):
        self._contracts: dict[Tuple[str, str], ContentTypeContract] = {}

    def register(self, contract) -> ContentTypeContract:
        if is_contract_class(contract):
            contract = contract.as_contract()

        key = contract.key
        if key in self._contracts:
            existing = self._contracts[key]
            if contract_signature(existing) == contract_signature(contract):
                return existing
            raise ValueError(
                f'Contract {contract.app_label}.{contract.model} is already registered '
                f'with a different definition'
            )
        self._contracts[key] = contract
        return contract

    def register_module(self, module: ModuleType):
        registered = []
        for value in vars(module).values():
            if is_contract_class(value):
                registered.append(self.register(value))
        return registered

    def autodiscover(self, module_name: str = 'content_type_contracts'):
        imported_modules = []
        for app_config in django_apps.get_app_configs():
            dotted_path = f'{app_config.name}.{module_name}'
            try:
                module = import_module(dotted_path)
            except ModuleNotFoundError as exc:
                if exc.name == dotted_path:
                    continue
                raise
            self.register_module(module)
            imported_modules.append(module)
        return imported_modules

    def get(self, app_label: Optional[str], model: Optional[str]) -> Optional[ContentTypeContract]:
        return self._contracts.get((app_label, model))

    def is_registered(self, app_label: Optional[str], model: Optional[str]) -> bool:
        return (app_label, model) in self._contracts

    def get_serializer(
        self,
        app_label: Optional[str],
        model: Optional[str],
        action: str,
        serializer_type: str = DEFAULT_SERIALIZER_TYPE,
    ):
        contract = self.get(app_label, model)
        if contract is None:
            return None
        return contract.get_serializer(action, serializer_type)

    def get_request_serializer(
        self,
        app_label: Optional[str],
        model: Optional[str],
        action: str,
        serializer_type: str = DEFAULT_SERIALIZER_TYPE,
        operation: Optional[str] = None,
    ):
        contract = self.get(app_label, model)
        if contract is None:
            return None
        return contract.get_request_serializer(action, serializer_type, operation=operation)


default_registry = ContentTypeContractRegistry()


# Backward-compatible aliases for projects that started with Resource naming.
ContentTypeResourceRegistry = ContentTypeContractRegistry
ResourceRegistry = ContentTypeContractRegistry
Resource = ContentTypeResource
