from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet, Iterable, Optional


DEFAULT_SERIALIZER_TYPE = 'default'
DEFAULT_READ_ACTIONS = frozenset({'list', 'retrieve'})
REGISTRY_POLICY_APPLIED_ATTR = '_content_type_registry_policy_applied'
CONTRACT_POLICY_APPLIED_ATTR = REGISTRY_POLICY_APPLIED_ATTR


@dataclass(frozen=True)
class PermissionCheckContext:
    request: object
    view: object
    action: str


PermissionPolicy = Callable[[PermissionCheckContext], bool]
LifecycleHook = Callable[..., None]


def deny_all(context: PermissionCheckContext) -> bool:
    return False


def any_authenticated_user(context: PermissionCheckContext) -> bool:
    user = getattr(context.request, 'user', None)
    return bool(user and getattr(user, 'is_authenticated', False))


def mark_contract_policy_applied(request, app_label: str, model: str, action: str):
    setattr(request, CONTRACT_POLICY_APPLIED_ATTR, {
        'app_label': app_label,
        'model': model,
        'action': action,
    })


def contract_policy_applied(request) -> bool:
    return bool(getattr(request, CONTRACT_POLICY_APPLIED_ATTR, None))


# Backward-compatible names for the first DrTrial implementation.
mark_registry_policy_applied = mark_contract_policy_applied
registry_policy_applied = contract_policy_applied


def normalize_actions(actions: Optional[Iterable[str]]) -> FrozenSet[str]:
    if actions is None:
        return DEFAULT_READ_ACTIONS
    if isinstance(actions, str):
        return frozenset({actions})
    return frozenset(actions)


def resolve_serializer_from_map(
    serializer_map: Any,
    action: str,
    serializer_type: str = DEFAULT_SERIALIZER_TYPE,
):
    if serializer_map is None:
        return None
    if not isinstance(serializer_map, dict):
        return serializer_map

    action_serializer_map = serializer_map.get(action)
    if action_serializer_map is None:
        return None
    if not isinstance(action_serializer_map, dict):
        return action_serializer_map
    return action_serializer_map.get(serializer_type)


@dataclass(frozen=True)
class ContentTypeLifecycle:
    before_create: Optional[LifecycleHook] = None
    after_create: Optional[LifecycleHook] = None
    before_update: Optional[LifecycleHook] = None
    after_update: Optional[LifecycleHook] = None
    before_delete: Optional[LifecycleHook] = None
    after_delete: Optional[LifecycleHook] = None

    def run(self, hook_name: str, **kwargs):
        hook = getattr(self, hook_name, None)
        if hook is None:
            return None
        return hook(**kwargs)


@dataclass(frozen=True)
class ContentTypeContract:
    app_label: str
    model: str
    allowed_actions: FrozenSet[str]
    policy: PermissionPolicy = deny_all
    serializer_map: Any = None
    request_serializer_map: Any = None
    response_serializer_map: Any = None
    missing_policy_actions: FrozenSet[str] = frozenset()
    lifecycle: ContentTypeLifecycle = field(default_factory=ContentTypeLifecycle)

    @property
    def key(self):
        return self.app_label, self.model

    @property
    def actions(self):
        return self.allowed_actions

    def check_permission(self, request, view) -> bool:
        action = view.action
        if action not in self.allowed_actions:
            return False
        return bool(self.policy(PermissionCheckContext(request=request, view=view, action=action)))

    def get_request_serializer(
        self,
        action: str,
        serializer_type: str = DEFAULT_SERIALIZER_TYPE,
        operation: Optional[str] = None,
    ):
        if action not in self.allowed_actions:
            return None
        if operation:
            serializer_class = resolve_serializer_from_map(
                self.request_serializer_map,
                operation,
                serializer_type,
            )
            if serializer_class is not None:
                return serializer_class
        return resolve_serializer_from_map(self.request_serializer_map, action, serializer_type)

    def get_response_serializer(
        self,
        action: str,
        serializer_type: str = DEFAULT_SERIALIZER_TYPE,
    ):
        if action not in self.allowed_actions:
            return None
        serializer_map = (
            self.response_serializer_map
            if self.response_serializer_map is not None
            else self.serializer_map
        )
        return resolve_serializer_from_map(serializer_map, action, serializer_type)

    def get_serializer(self, action: str, serializer_type: str = DEFAULT_SERIALIZER_TYPE):
        return self.get_response_serializer(action, serializer_type)


class DeclarativeContentTypeContract:
    """Class-based declaration used by autodiscover modules.

    Subclasses are declarations only. They must not handle requests or return
    DRF responses; the view owns the HTTP lifecycle.
    """

    abstract = False
    model = None
    app_label = None
    model_name = None
    actions = DEFAULT_READ_ACTIONS
    allowed_actions = None
    serializer = None
    serializer_map = None
    request_serializers = None
    request_serializer_map = None
    response_serializers = None
    response_serializer_map = None
    policy = deny_all
    permissions = None
    missing_policy_actions = frozenset()
    lifecycle = None

    @classmethod
    def as_contract(cls) -> ContentTypeContract:
        model = cls.model
        app_label = cls.app_label
        model_name = cls.model_name

        if model is not None and hasattr(model, '_meta'):
            app_label = app_label or model._meta.app_label
            model_name = model_name or model._meta.model_name
        elif isinstance(model, str):
            if '.' in model and not (app_label and model_name):
                app_label, model_name = model.split('.', 1)
            else:
                model_name = model_name or model

        if not app_label or not model_name:
            raise ValueError(
                f'{cls.__name__} must declare model or both app_label and model_name'
            )

        allowed_actions = (
            cls.allowed_actions
            if cls.allowed_actions is not None
            else cls.actions
        )
        request_serializer_map = (
            cls.request_serializer_map
            if cls.request_serializer_map is not None
            else cls.request_serializers
        )
        response_serializer_map = cls.response_serializer_map
        if response_serializer_map is None:
            response_serializer_map = cls.response_serializers
        if response_serializer_map is None:
            response_serializer_map = cls.serializer_map
        if response_serializer_map is None:
            response_serializer_map = cls.serializer

        policy = cls.permissions if cls.permissions is not None else cls.policy
        lifecycle = cls.lifecycle or ContentTypeLifecycle()

        return ContentTypeContract(
            app_label=app_label,
            model=model_name,
            allowed_actions=normalize_actions(allowed_actions),
            policy=policy,
            serializer_map=response_serializer_map,
            request_serializer_map=request_serializer_map,
            response_serializer_map=response_serializer_map,
            missing_policy_actions=normalize_actions(cls.missing_policy_actions),
            lifecycle=lifecycle,
        )


# Backward-compatible aliases for projects that started with Resource naming.
ContentTypeResource = ContentTypeContract
Ctr = DeclarativeContentTypeContract
