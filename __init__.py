from drf_contenttype_contracts.contracts import (
    CONTRACT_POLICY_APPLIED_ATTR,
    DEFAULT_LOAD_STORE_ACTIONS,
    DEFAULT_READ_ACTIONS,
    DEFAULT_SERIALIZER_TYPE,
    AuthenticatedContentTypeContract,
    AuthenticatedMutableContract,
    AuthenticatedReadOnlyContract,
    ContentTypeContract,
    ContentTypeLifecycle,
    DeclarativeContentTypeContract,
    PermissionCheckContext,
    PermissionPolicy,
    UnauditedContentTypeContract,
    any_authenticated_user,
    contract_policy_applied,
    deny_all,
    mark_contract_policy_applied,
    normalize_actions,
    resolve_serializer_from_map,
)
from drf_contenttype_contracts.registry import (
    ContentTypeContractRegistry,
    contract_signature,
    default_registry,
    is_contract_class,
    serializer_map_to_names,
    serializer_name,
)

__all__ = (
    'CONTRACT_POLICY_APPLIED_ATTR',
    'DEFAULT_LOAD_STORE_ACTIONS',
    'DEFAULT_READ_ACTIONS',
    'DEFAULT_SERIALIZER_TYPE',
    'AuthenticatedContentTypeContract',
    'AuthenticatedMutableContract',
    'AuthenticatedReadOnlyContract',
    'ContentTypeContract',
    'ContentTypeContractRegistry',
    'ContentTypeLifecycle',
    'DjangoContentTypeContract',
    'DeclarativeContentTypeContract',
    'PermissionCheckContext',
    'PermissionPolicy',
    'UnauditedContentTypeContract',
    'any_authenticated_user',
    'contract_policy_applied',
    'default_registry',
    'contract_signature',
    'deny_all',
    'is_contract_class',
    'mark_contract_policy_applied',
    'normalize_actions',
    'resolve_serializer_from_map',
    'serializer_map_to_names',
    'serializer_name',
)


def __getattr__(name):
    if name == 'DjangoContentTypeContract':
        from drf_contenttype_contracts.contenttypes import DjangoContentTypeContract

        return DjangoContentTypeContract
    raise AttributeError(f"module 'drf_contenttype_contracts' has no attribute {name!r}")
