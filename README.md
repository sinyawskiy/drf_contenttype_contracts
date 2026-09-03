# drf-contenttype-contracts

Declarative contracts for a Django generic API built on `ContentType` and
Django REST Framework.

Use this package when one endpoint should load different Django models by
`app_label` and `model`, while the backend still keeps the public contract
explicit: serializer, allowed actions, permission policy and lifecycle hooks.

The package does not auto-register models. Installing it does not expose your
database. A model becomes available only after the host Django project registers
a contract for it.

## Install

```bash
pip install drf-contenttype-contracts
```

With Poetry:

```bash
poetry add drf-contenttype-contracts
```

## Core Concepts

- `ContentTypeContract` is the runtime contract for one model.
- `DeclarativeContentTypeContract` is the class-based declaration style.
- `ContentTypeContractRegistry` is an explicit allowlist of contracts.
- `ContentTypeContractsView` is the generic DRF view.
- `ContentTypeContractPermission` is the default DRF permission class that
  applies the selected contract policy.
- `DynamicRetrieveModelSerializer` can build a read serializer from a Django
  model, with optional `exclude_fields`.
- Built-in opt-in contracts are available for `contenttypes.contenttype` and
  the active `settings.AUTH_USER_MODEL`.

Project-specific serializers, permission policies and lifecycle hooks stay in
the host Django app.

## Quick Start

Create a contract:

```python
# app/content_type_contracts.py
from django.contrib.auth import get_user_model
from rest_framework import serializers

from drf_contenttype_contracts.resources.base import AuthenticatedReadOnlyContract


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'username', 'email', 'is_active')


class UserContract(AuthenticatedReadOnlyContract):
    model = get_user_model()
    serializer = UserSerializer
    filter_fields = ('id', 'username', 'email')
    order_fields = ('username', 'email')
```

Register it:

```python
# app/content_type_registry.py
from drf_contenttype_contracts import ContentTypeContractRegistry

from app.content_type_contracts import UserContract


content_type_registry = ContentTypeContractRegistry()
content_type_registry.register(UserContract)
```

Expose the generic view:

```python
# app/views.py
from drf_contenttype_contracts.views import ContentTypeContractsView

from app.content_type_registry import content_type_registry


class ApiContentTypeView(ContentTypeContractsView):
    contract_registry = content_type_registry
```

`ContentTypeContractsView` uses `ContentTypeContractPermission` by default.
Requests for unregistered contracts are denied before the view reads the model
or serializer.

The view also enforces the registry allowlist inside its action handlers.
Even if a host project replaces `permission_classes`, `list`, `retrieve`,
`add_or_edit` and `destroy` still require a registered contract with the current
action in `allowed_actions`.

Wire actions in `urls.py`:

```python
# app/urls.py
from django.urls import path

from app.views import ApiContentTypeView


urlpatterns = [
    path(
        'content-types/list/',
        ApiContentTypeView.as_view({'post': 'list'}),
        name='content-type-list',
    ),
    path(
        'content-types/retrieve/',
        ApiContentTypeView.as_view({'post': 'retrieve'}),
        name='content-type-retrieve',
    ),
    path(
        'content-types/add-or-edit/',
        ApiContentTypeView.as_view({'post': 'add_or_edit'}),
        name='content-type-add-or-edit',
    ),
    path(
        'content-types/delete/',
        ApiContentTypeView.as_view({'post': 'destroy'}),
        name='content-type-delete',
    ),
]
```

## Request

Assuming the view is mounted at `/api/content-types/list/`:

```bash
curl -X POST http://localhost:8000/api/content-types/list/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "app_label": "auth",
    "model": "user",
    "serializer_type": "default",
    "search": "",
    "order": "",
    "start_index": 0,
    "stop_index": 10,
    "filters": {},
    "excludes": {}
  }'
```

Example response:

```json
{
  "start_index": 0,
  "stop_index": 10,
  "total": 1,
  "elements": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "is_active": true
    }
  ],
  "order": "",
  "search": "",
  "filter_fields": [
    {"name": "id", "verbose_name": "ID"},
    {"name": "username", "verbose_name": "username"},
    {"name": "email", "verbose_name": "email address"}
  ]
}
```

## Public Filters And Ordering

`filters`, `excludes` and client-provided `order` are part of the public API.
`ContentTypeContractsView` validates them before applying them to the queryset.

Use `filter_fields` on a contract to declare which filter keys are public:

```python
class UserContract(AuthenticatedReadOnlyContract):
    model = get_user_model()
    serializer = UserSerializer
    filter_fields = ('id', 'username', 'email')
```

Lookup suffixes are allowed only on public field prefixes. For example,
`username__icontains` and `id__in` are accepted when `username` and `id` are
public fields.

Relation traversal is denied by default. Declare the full path when it is an
intentional part of the generic API:

```python
class DocumentContract(AuthenticatedReadOnlyContract):
    model = 'documents.document'
    serializer = DocumentSerializer
    filter_fields = (
        'id',
        'content_type',
        'content_type__app_label',
        'content_type__model',
        'object_id',
    )
```

Declaring a foreign key field also allows its database id alias. For example,
`content_type` allows `content_type_id`, and `document_type` allows
`document_type_id`.

`filter_fields = ()` means no client filters are public. `filter_fields = None`
keeps the compatibility behavior: use `model.filter_fields` when the model has
it, otherwise allow local model fields and foreign key id aliases.

Use `order_fields` when sorting should be stricter than filtering:

```python
class UserContract(AuthenticatedReadOnlyContract):
    model = get_user_model()
    serializer = UserSerializer
    filter_fields = ('id', 'username', 'email')
    order_fields = ('username',)
```

If `order_fields` is not set, sorting uses the same public field list as
filtering. Invalid filters, excludes and order fields return `400`.

`retrieve` also validates its request serializer before resolving the model.
Invalid `id`, `uuid` or `external_id` payloads return `400`.

## Built-In Django Contracts

`DjangoUserContract` registers a read-only contract for the active Django user
model from `settings.AUTH_USER_MODEL`:

```python
from drf_contenttype_contracts import ContentTypeContractRegistry
from drf_contenttype_contracts.resources.django import DjangoUserContract


registry = ContentTypeContractRegistry()
registry.register(DjangoUserContract)
```

The default user serializer is built with `DynamicRetrieveModelSerializer` and
excludes Django auth fields that should not be exposed by a generic API:
`password`, `last_login`, `is_superuser`, `is_staff`, `date_joined`, `groups`
and `user_permissions`.

For custom user models, review the exposed fields and provide a stricter
serializer or a larger exclude set when needed:

```python
from drf_contenttype_contracts.resources.django import (
    DEFAULT_USER_EXCLUDE_FIELDS,
    DjangoUserContract,
    create_django_user_serializer,
)


class PublicUserContract(DjangoUserContract):
    serializer = create_django_user_serializer(
        exclude_fields=DEFAULT_USER_EXCLUDE_FIELDS | {'phone', 'birth_date'},
    )
```

`DjangoContentTypeContract` registers a read-only contract for
`contenttypes.contenttype`:

```python
from drf_contenttype_contracts.resources.django import DjangoContentTypeContract


registry.register(DjangoContentTypeContract)
```

By default, `ContentTypeContractsView` limits `contenttypes.contenttype` list
responses to models registered in the active contract registry. This prevents
the generic API from exposing every row from `django_content_type`.

Disable this limit only if your project intentionally exposes all content
types:

```python
DRF_CONTENTTYPE_CONTRACTS_LIMIT_CONTENTTYPE_LIST = False
```

## Dynamic Serializers

Use `DynamicRetrieveModelSerializer` when a read-only model contract does not
need a custom serializer:

```python
from drf_contenttype_contracts.resources.base import AuthenticatedReadOnlyContract
from drf_contenttype_contracts.serializers import DynamicRetrieveModelSerializer


class PublicUserContract(AuthenticatedReadOnlyContract):
    model = 'auth.User'
    serializer = DynamicRetrieveModelSerializer(
        'auth',
        'user',
        exclude_fields={'password', 'groups', 'user_permissions'},
    )
```

The helper can also resolve a model class or dotted model reference:

```python
serializer = DynamicRetrieveModelSerializer.from_model_ref(
    'auth.User',
    exclude_fields={'password'},
)
```

For registered installed models, the helper resolves through Django's app
registry first and does not need a `django_content_type` database row just to
build the serializer.

## Serializer Maps

Contracts can define per-action and per-type serializers:

```python
class UserContract(AuthenticatedReadOnlyContract):
    model = 'auth.User'
    serializer_map = {
        'list': {
            'default': UserListSerializer,
            'select': UserSelectSerializer,
        },
        'retrieve': UserDetailSerializer,
    }
```

The frontend can choose a serializer variant with `serializer_type`.

You can inspect the registry in a legacy `MODEL_WITH_SERIALIZER_MAP`-like
shape:

```python
print(registry.to_model_serializer_map_json())
```

Example output:

```json
{
    "auth": {
        "user": {
            "list": {
                "default": "UserListSerializer",
                "select": "UserSelectSerializer"
            },
            "retrieve": "UserDetailSerializer"
        }
    }
}
```

Enable registration diagnostics:

```python
registry = ContentTypeContractRegistry(debug=True)
registry.register(UserContract)
# drf-contenttype-contracts registered model=auth.user action=list type=default serializer=UserListSerializer
# drf-contenttype-contracts registered model=auth.user action=list type=select serializer=UserSelectSerializer
# drf-contenttype-contracts registered model=auth.user action=retrieve type=default serializer=UserDetailSerializer
```

In Django settings, registries created with `debug=None` can read the same flag:

```python
DRF_CONTENTTYPE_CONTRACTS_DEBUG = True
```

## Policies

A contract policy receives `PermissionCheckContext`:

```python
from drf_contenttype_contracts.policies.base import PermissionCheckContext
from drf_contenttype_contracts.resources.base import DeclarativeContentTypeContract


def staff_only(context: PermissionCheckContext):
    user = context.request.user
    return bool(user and user.is_authenticated and user.is_staff)


class StaffUserContract(DeclarativeContentTypeContract):
    model = 'auth.User'
    actions = {'list', 'retrieve'}
    policy = staff_only
    serializer = UserSerializer
```

`AuthenticatedReadOnlyContract` and `AuthenticatedMutableContract` are small
base classes that use the built-in `any_authenticated_user` policy. For real
business rules, keep project-specific policies in your Django app and register
them on contracts.

`ContentTypeContractsView` applies contract policies by default through
`ContentTypeContractPermission`. If your project overrides
`permission_classes`, include this permission class or intentionally replace it:

```python
from rest_framework.permissions import IsAdminUser

from drf_contenttype_contracts.permissions import ContentTypeContractPermission
from drf_contenttype_contracts.views import ContentTypeContractsView


class ApiContentTypeView(ContentTypeContractsView):
    permission_classes = [IsAdminUser | ContentTypeContractPermission]
```

Contracts based on `UnauditedContentTypeContract` mark their actions in
`missing_policy_actions`. The default permission class still applies the
contract policy, but also logs a warning so temporary authenticated access is
visible in application logs.

## Lifecycle Hooks

`add_or_edit` and `destroy` can run lifecycle hooks from the contract:

```python
from drf_contenttype_contracts.resources.base import (
    ContentTypeLifecycle,
    DeclarativeContentTypeContract,
)


def after_create_user(**kwargs):
    instance = kwargs['instance']
    request = kwargs['request']
    audit_user_created(instance, actor=request.user)


class UserMutationContract(DeclarativeContentTypeContract):
    model = 'auth.User'
    actions = {'list', 'retrieve', 'add_or_edit', 'destroy'}
    request_serializers = {
        'create': UserCreateSerializer,
        'update': UserUpdateSerializer,
    }
    response_serializers = {
        'retrieve': UserSerializer,
        'add_or_edit': UserSerializer,
    }
    lifecycle = ContentTypeLifecycle(after_create=after_create_user)
```

Available hook names:

- `before_create`
- `after_create`
- `before_update`
- `after_update`
- `before_delete`
- `after_delete`

## Autodiscover

The registry can import `content_type_contracts.py` from installed Django apps:

```python
registry = ContentTypeContractRegistry()
registry.autodiscover()
```

Only concrete subclasses of `DeclarativeContentTypeContract` are registered.
Classes with `abstract = True` are skipped.

## Demo

The repository contains a small Django + DRF + drf-spectacular demo in `demo/`.
It is intentionally excluded from published wheel and sdist artifacts.

Run it from the repository:

```bash
cd demo
poetry install
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
poetry run python manage.py runserver
```

OpenAPI schema:

```text
http://localhost:8000/api/schema/
http://localhost:8000/api/docs/
```
