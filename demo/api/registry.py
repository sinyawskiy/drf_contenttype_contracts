from drf_contenttype_contracts import ContentTypeContractRegistry
from drf_contenttype_contracts.resources.django import (
    DjangoContentTypeContract,
    DjangoUserContract,
)


demo_contract_registry = ContentTypeContractRegistry()
demo_contract_registry.register(DjangoUserContract)
demo_contract_registry.register(DjangoContentTypeContract)
