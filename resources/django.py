from django.conf import settings

from drf_contenttype_contracts.resources.base import AuthenticatedReadOnlyContract
from drf_contenttype_contracts.serializers import (
    ContentTypeListSerializer,
    DynamicRetrieveModelSerializer,
)


DEFAULT_USER_EXCLUDE_FIELDS = frozenset({
    'password',
    'last_login',
    'is_superuser',
    'is_staff',
    'date_joined',
    'groups',
    'user_permissions',
})


def create_django_user_serializer(
    *,
    exclude_fields=DEFAULT_USER_EXCLUDE_FIELDS,
    serializer_name='DjangoUserSerializer',
):
    return DynamicRetrieveModelSerializer.from_model_ref(
        lambda: settings.AUTH_USER_MODEL,
        exclude_fields=exclude_fields,
        serializer_name=serializer_name,
    )


DjangoUserSerializer = create_django_user_serializer()


class DjangoContentTypeContract(AuthenticatedReadOnlyContract):
    """Read-only contract for Django's built-in ContentType model."""

    model = 'contenttypes.contenttype'
    serializer = ContentTypeListSerializer


class DjangoUserContract(AuthenticatedReadOnlyContract):
    """Read-only contract for the active Django AUTH_USER_MODEL."""

    serializer = DjangoUserSerializer

    @classmethod
    def get_model(cls):
        return settings.AUTH_USER_MODEL


__all__ = (
    'DEFAULT_USER_EXCLUDE_FIELDS',
    'DjangoContentTypeContract',
    'DjangoUserContract',
    'DjangoUserSerializer',
    'create_django_user_serializer',
)
