# drf-contenttype-contracts

Declarative ContentType-backed API contracts for Django REST Framework.

This package is extracted from DrTrial as a small internal library candidate.
It provides the reusable mechanics only:

- `ContentTypeContract`
- `ContentTypeContractRegistry`
- serializer map resolution
- class-based declarations for autodiscover
- lifecycle hook placeholders
- a generic `ContentTypeContractsView`

Project-specific serializers, policies and hooks stay in the host Django app.

Minimal declaration:

```python
from drf_contenttype_contracts import Ctr


class MonitorCtr(Ctr):
    model = Monitor
    serializer = MonitorDetailSerializer
```

Explicit registration:

```python
from drf_contenttype_contracts import ContentTypeContract

registry.register(ContentTypeContract(
    app_label='researches',
    model='monitor',
    allowed_actions=frozenset({'list', 'retrieve'}),
    policy=monitor_policy,
    serializer_map=MonitorDetailSerializer,
))
```
