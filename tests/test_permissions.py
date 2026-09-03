import unittest

from drf_contenttype_contracts.tests.bootstrap import setup_django

setup_django()

from drf_contenttype_contracts.permissions import ContentTypeContractPermission
from drf_contenttype_contracts.registry import ContentTypeContractRegistry
from drf_contenttype_contracts.resources.base import (
    ContentTypeContract,
    contract_policy_applied,
)
from drf_contenttype_contracts.views import ContentTypeContractsView


class FakeRequest:
    def __init__(self, data=None, query_params=None, user=None):
        self.data = data
        self.query_params = query_params
        self.user = user


class FakeUser:
    id = 1
    username = 'user@example.com'
    is_authenticated = True


class FakeView:
    action = 'list'

    def __init__(self, registry):
        self.registry = registry

    def get_contract_registry(self):
        return self.registry


class ContentTypeContractPermissionTests(unittest.TestCase):
    def make_contract(self, **overrides):
        kwargs = {
            'app_label': 'auth',
            'model': 'user',
            'allowed_actions': frozenset({'list'}),
            'policy': lambda context: True,
        }
        kwargs.update(overrides)
        return ContentTypeContract(**kwargs)

    def make_view(self, contract=None):
        registry = ContentTypeContractRegistry()
        if contract is not None:
            registry.register(contract)
        return FakeView(registry)

    def make_request(self, data=None):
        return FakeRequest(
            data=data or {'app_label': 'auth', 'model': 'user'},
            user=FakeUser(),
        )

    def test_view_uses_contract_permission_by_default(self):
        self.assertEqual(
            ContentTypeContractsView.permission_classes,
            (ContentTypeContractPermission,),
        )

    def test_denies_request_without_app_label_or_model(self):
        permission = ContentTypeContractPermission()
        view = self.make_view(self.make_contract())

        self.assertFalse(permission.has_permission(FakeRequest(data={}, user=FakeUser()), view))

    def test_denies_unregistered_contract(self):
        permission = ContentTypeContractPermission()

        self.assertFalse(permission.has_permission(self.make_request(), self.make_view()))

    def test_denies_disallowed_action(self):
        permission = ContentTypeContractPermission()
        view = self.make_view(self.make_contract(allowed_actions=frozenset({'retrieve'})))

        self.assertFalse(permission.has_permission(self.make_request(), view))

    def test_delegates_to_contract_policy(self):
        permission = ContentTypeContractPermission()
        view = self.make_view(self.make_contract(policy=lambda context: False))

        self.assertFalse(permission.has_permission(self.make_request(), view))

    def test_allowed_request_marks_contract_policy_applied(self):
        permission = ContentTypeContractPermission()
        request = self.make_request()
        view = self.make_view(self.make_contract())

        self.assertTrue(permission.has_permission(request, view))
        self.assertTrue(contract_policy_applied(request))

    def test_missing_policy_action_logs_warning_but_still_applies_policy(self):
        permission = ContentTypeContractPermission()
        request = self.make_request()
        view = self.make_view(self.make_contract(missing_policy_actions=frozenset({'list'})))

        with self.assertLogs('drf_contenttype_contracts.permissions', level='WARNING') as logs:
            self.assertTrue(permission.has_permission(request, view))

        self.assertIn('policy is marked as missing or unaudited', '\n'.join(logs.output))

    def test_query_params_are_used_when_request_data_is_not_mapping(self):
        permission = ContentTypeContractPermission()
        request = FakeRequest(
            data=None,
            query_params={'app_label': 'auth', 'model': 'user'},
            user=FakeUser(),
        )
        view = self.make_view(self.make_contract())

        self.assertTrue(permission.has_permission(request, view))


if __name__ == '__main__':
    unittest.main()
