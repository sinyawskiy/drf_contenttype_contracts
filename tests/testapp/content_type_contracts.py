"""Sample contract module used to exercise ContentTypeContractRegistry.autodiscover()."""
from drf_contenttype_contracts import DeclarativeContentTypeContract


class _StubMeta:
    app_label = 'testapp'
    model_name = 'widget'


class _StubModel:
    _meta = _StubMeta


class WidgetSerializer:
    pass


class WidgetContract(DeclarativeContentTypeContract):
    model = _StubModel
    serializer = WidgetSerializer
