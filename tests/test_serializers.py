import unittest

from drf_contenttype_contracts.tests.bootstrap import setup_django

setup_django()

from django.contrib.auth.models import User

from drf_contenttype_contracts.resources.django import (
    DEFAULT_USER_EXCLUDE_FIELDS,
    DjangoUserContract,
    DjangoUserSerializer,
    create_django_user_serializer,
)
from drf_contenttype_contracts.serializers import DynamicRetrieveModelSerializer


class DynamicRetrieveModelSerializerTests(unittest.TestCase):
    def test_content_type_factory_has_stable_serializer_name(self):
        serializer = DynamicRetrieveModelSerializer(
            'auth',
            'user',
            exclude_fields={'password'},
        )

        self.assertEqual(serializer.__name__, 'DynamicAuthUserSerializer')

    def test_exclude_fields_removes_model_fields(self):
        serializer = DynamicRetrieveModelSerializer.from_model_ref(
            User,
            exclude_fields={'password', 'is_superuser'},
        )

        fields = tuple(serializer().fields)

        self.assertIn('username', fields)
        self.assertNotIn('password', fields)
        self.assertNotIn('is_superuser', fields)


class DjangoUserContractTests(unittest.TestCase):
    def test_contract_resolves_active_auth_user_model(self):
        self.assertEqual(DjangoUserContract.as_contract().key, ('auth', 'user'))

    def test_default_serializer_excludes_sensitive_auth_fields(self):
        fields = tuple(DjangoUserSerializer().fields)

        self.assertEqual(fields, ('id', 'username', 'first_name', 'last_name', 'email', 'is_active'))

    def test_factory_accepts_extra_exclude_fields(self):
        serializer = create_django_user_serializer(
            exclude_fields=DEFAULT_USER_EXCLUDE_FIELDS | {'email'},
        )

        self.assertNotIn('email', tuple(serializer().fields))


if __name__ == '__main__':
    unittest.main()
