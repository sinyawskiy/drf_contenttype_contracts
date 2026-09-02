# drf-contenttype-contracts

Declarative contracts for Django generic APIs built on ContentType and Django REST Framework.

Use it when one generic endpoint needs to serve multiple Django models by
`app_label` and `model`, while keeping serializers, allowed actions,
permissions and lifecycle hooks explicit.

- `ContentTypeContract`
- `ContentTypeContractRegistry`
- serializer map resolution
- class-based declarations for autodiscover
- authenticated read/mutable declaration bases
- lifecycle hooks
- a generic `ContentTypeContractsView`

Project-specific serializers, policies and hooks stay in the host Django app.

Minimal declaration for Django's built-in `User` model:

```python
from django.contrib.auth.models import User
from rest_framework import serializers

from drf_contenttype_contracts import AuthenticatedReadOnlyContract


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'is_active')


class UserContract(AuthenticatedReadOnlyContract):
    model = User
    serializer = UserSerializer
```

Explicit policy and action set:

```python
from django.contrib.auth.models import User
from rest_framework import serializers

from drf_contenttype_contracts import Ctr


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'is_active')


def staff_only(context):
    user = context.request.user
    return bool(user and user.is_authenticated and user.is_staff)


class UserContract(Ctr):
    model = User
    actions = {'list', 'retrieve'}
    policy = staff_only
    serializer = UserSerializer
```

Register a module with declarations:

```python
registry.register_module(content_type_contracts)
```

Example `list` request, assuming your project exposes the view action at
`/api/content-types/list/`:

```bash
curl -X POST http://localhost:8000/api/content-types/list/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "app_label": "auth",
    "model": "user",
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
    {"name": "password", "verbose_name": "password"},
    {"name": "last_login", "verbose_name": "last login"},
    {"name": "is_superuser", "verbose_name": "superuser status"},
    {"name": "username", "verbose_name": "username"},
    {"name": "first_name", "verbose_name": "first name"},
    {"name": "last_name", "verbose_name": "last name"},
    {"name": "email", "verbose_name": "email address"},
    {"name": "is_staff", "verbose_name": "staff status"},
    {"name": "is_active", "verbose_name": "active"},
    {"name": "date_joined", "verbose_name": "date joined"}
  ]
}
```
