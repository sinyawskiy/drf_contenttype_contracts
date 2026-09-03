from drf_contenttype_contracts.views import ContentTypeContractsView

from api.registry import demo_contract_registry


class DemoContentTypeContractsView(ContentTypeContractsView):
    contract_registry = demo_contract_registry
