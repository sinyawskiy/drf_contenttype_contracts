import json
import sys
from collections.abc import Mapping
from importlib import import_module
from types import ModuleType
from typing import Any, Iterator, Optional, TextIO, Tuple

from django.apps import apps as django_apps
from django.conf import settings as django_settings

from drf_contenttype_contracts.resources.base import (
    DEFAULT_SERIALIZER_TYPE,
    ContentTypeContract,
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


def _django_debug_enabled() -> bool:
    try:
        return bool(
            django_settings.configured
            and getattr(django_settings, 'DRF_CONTENTTYPE_CONTRACTS_DEBUG', False)
        )
    except Exception:
        return False


def serializer_name(serializer) -> Optional[str]:
    if serializer is None:
        return None
    if isinstance(serializer, type):
        return serializer.__name__
    return serializer.__class__.__name__


def serializer_map_to_names(serializer_map: Any) -> Any:
    if serializer_map is None:
        return None
    if isinstance(serializer_map, Mapping):
        return {
            str(key): serializer_map_to_names(value)
            for key, value in serializer_map.items()
        }
    return serializer_name(serializer_map)


def _contract_response_serializer_map(contract: ContentTypeContract):
    if contract.response_serializer_map is not None:
        return contract.response_serializer_map
    return contract.serializer_map


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
        contract.filter_fields,
        contract.order_fields,
    )


class ContentTypeContractRegistry:
    """Explicit allowlist of ContentType-backed API contracts."""

    def __init__(self, debug: Optional[bool] = None, debug_stream: Optional[TextIO] = None):
        self._contracts: dict[Tuple[str, str], ContentTypeContract] = {}
        self.debug = _django_debug_enabled() if debug is None else debug
        self.debug_stream = debug_stream

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
        self._debug_print_contract(contract)
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

    def registered_keys(self) -> tuple[Tuple[str, str], ...]:
        return tuple(sorted(self._contracts))

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

    def iter_serializer_bindings(self, contract: Optional[ContentTypeContract] = None) -> Iterator[dict]:
        contracts = [contract] if contract is not None else [
            self._contracts[key] for key in sorted(self._contracts)
        ]
        for item in contracts:
            serializer_map = _contract_response_serializer_map(item)
            if isinstance(serializer_map, Mapping):
                for action, value in serializer_map.items():
                    if isinstance(value, Mapping):
                        for serializer_type, serializer in value.items():
                            yield self._serializer_binding(item, action, serializer_type, serializer)
                    else:
                        yield self._serializer_binding(item, action, DEFAULT_SERIALIZER_TYPE, value)
            elif serializer_map is not None:
                for action in sorted(item.allowed_actions):
                    yield self._serializer_binding(
                        item, action, DEFAULT_SERIALIZER_TYPE, serializer_map
                    )

    def to_model_serializer_map(self) -> dict:
        result = {}
        for app_label, model in sorted(self._contracts):
            contract = self._contracts[(app_label, model)]
            result.setdefault(app_label, {})[model] = serializer_map_to_names(
                _contract_response_serializer_map(contract)
            )
        return result

    def to_model_serializer_map_json(self, **json_kwargs) -> str:
        kwargs = {
            'ensure_ascii': False,
            'indent': 4,
            'sort_keys': True,
        }
        kwargs.update(json_kwargs)
        return json.dumps(self.to_model_serializer_map(), **kwargs)

    @staticmethod
    def _serializer_binding(contract, action, serializer_type, serializer) -> dict:
        return {
            'model': f'{contract.app_label}.{contract.model}',
            'app_label': contract.app_label,
            'model_name': contract.model,
            'action': str(action),
            'serializer_type': str(serializer_type),
            'serializer': serializer_name(serializer),
        }

    def _debug_print_contract(self, contract: ContentTypeContract):
        if not self.debug:
            return
        stream = self.debug_stream or sys.stdout
        for binding in self.iter_serializer_bindings(contract):
            print(
                'drf-contenttype-contracts registered '
                f'model={binding["model"]} '
                f'action={binding["action"]} '
                f'type={binding["serializer_type"]} '
                f'serializer={binding["serializer"]}',
                file=stream,
            )


default_registry = ContentTypeContractRegistry()
