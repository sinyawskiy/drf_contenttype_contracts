from drf_contenttype_contracts.contracts import AuthenticatedReadOnlyContract
from drf_contenttype_contracts.serializers import ContentTypeListSerializer


class DjangoContentTypeContract(AuthenticatedReadOnlyContract):
    """Read-only contract for Django's built-in ContentType model."""

    model = 'contenttypes.contenttype'
    serializer = ContentTypeListSerializer
