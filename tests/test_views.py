import unittest

from drf_contenttype_contracts.tests.bootstrap import setup_django

setup_django()

from django.contrib.auth.models import User
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError

from drf_contenttype_contracts.registry import ContentTypeContractRegistry
from drf_contenttype_contracts.resources.base import ContentTypeContract
from drf_contenttype_contracts.views import ContentTypeContractsView


class FakeRequest:
    def __init__(self, data):
        self.data = data


class ContentTypeContractsViewAllowlistTests(unittest.TestCase):
    def make_contract(self, allowed_actions):
        return ContentTypeContract(
            app_label='auth',
            model='user',
            allowed_actions=frozenset(allowed_actions),
            policy=lambda context: True,
        )

    def make_view(self, action, contract=None):
        registry = ContentTypeContractRegistry()
        if contract is not None:
            registry.register(contract)

        view = ContentTypeContractsView()
        view.action = action
        view.contract_registry = registry
        return view

    def test_get_action_contract_denies_unregistered_model(self):
        view = self.make_view('list')
        view.request = FakeRequest({'app_label': 'auth', 'model': 'user'})

        with self.assertRaises(PermissionDenied):
            view.get_action_contract()

    def test_get_action_contract_denies_unregistered_action(self):
        view = self.make_view('destroy', self.make_contract({'list'}))
        view.request = FakeRequest({'app_label': 'auth', 'model': 'user'})

        with self.assertRaises(PermissionDenied):
            view.get_action_contract()

    def test_get_action_contract_returns_registered_action_contract(self):
        contract = self.make_contract({'destroy'})
        view = self.make_view('destroy', contract)
        view.request = FakeRequest({'app_label': 'auth', 'model': 'user'})

        self.assertIs(view.get_action_contract(), contract)

    def test_list_enforces_contract_before_queryset_resolution(self):
        request = FakeRequest({
            'app_label': 'auth',
            'model': 'user',
            'filters': {},
            'excludes': {},
        })
        view = self.make_view('list')
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.list(request)

    def test_retrieve_enforces_contract_before_model_resolution(self):
        request = FakeRequest({'app_label': 'auth', 'model': 'user', 'id': 1})
        view = self.make_view('retrieve')
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.retrieve(request)

    def test_retrieve_validates_payload_before_model_resolution(self):
        request = FakeRequest({'app_label': 'auth', 'model': 'user', 'id': 'not-an-int'})
        view = self.make_view('retrieve', self.make_contract({'retrieve'}))
        view.request = request

        response = view.retrieve(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn('id', response.data)

    def test_add_or_edit_enforces_contract_before_generic_fallback(self):
        request = FakeRequest({
            'app_label': 'auth',
            'model': 'user',
            'data': {'username': 'unsafe-create'},
        })
        view = self.make_view('add_or_edit')
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.add_or_edit(request)

    def test_add_or_edit_denies_read_only_contract_before_generic_fallback(self):
        request = FakeRequest({
            'app_label': 'auth',
            'model': 'user',
            'data': {'username': 'unsafe-create'},
        })
        view = self.make_view('add_or_edit', self.make_contract({'list', 'retrieve'}))
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.add_or_edit(request)

    def test_destroy_enforces_contract_before_model_resolution(self):
        request = FakeRequest({'app_label': 'auth', 'model': 'user', 'id': '1'})
        view = self.make_view('destroy')
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.destroy(request)

    def test_destroy_denies_read_only_contract_before_model_resolution(self):
        request = FakeRequest({'app_label': 'auth', 'model': 'user', 'id': '1'})
        view = self.make_view('destroy', self.make_contract({'list', 'retrieve'}))
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.destroy(request)


class ContentTypeContractsViewFilterValidationTests(unittest.TestCase):
    class UsernameOnlyModel:
        filter_fields = ('username',)
        _meta = User._meta

    class NoPublicFiltersModel:
        filter_fields = ()
        _meta = User._meta

    def test_default_filters_allow_local_field_and_lookup(self):
        ContentTypeContractsView.validate_filter_tree(
            User,
            {'username__icontains': 'admin', 'id__in': [1, 2]},
        )

    def test_default_filters_deny_relation_traversal(self):
        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_filter_tree(
                User,
                {'groups__name': 'admin'},
            )

    def test_contract_filter_fields_allow_explicit_relation_path(self):
        contract = ContentTypeContract(
            app_label='auth',
            model='user',
            allowed_actions=frozenset({'list'}),
            policy=lambda context: True,
            filter_fields=frozenset({'username', 'groups__name'}),
        )

        ContentTypeContractsView.validate_filter_tree(
            User,
            {'groups__name': 'admin'},
            contract=contract,
        )

        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_filter_tree(
                User,
                {'email': 'admin@example.com'},
                contract=contract,
            )

    def test_declared_filter_fields_are_enforced(self):
        ContentTypeContractsView.validate_filter_tree(
            self.UsernameOnlyModel,
            {'username__icontains': 'admin'},
        )

        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_filter_tree(
                self.UsernameOnlyModel,
                {'email': 'admin@example.com'},
            )

    def test_empty_declared_filter_fields_deny_all_filters(self):
        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_filter_tree(
                self.NoPublicFiltersModel,
                {'username': 'admin'},
            )

    def test_nested_filter_groups_are_validated(self):
        ContentTypeContractsView.validate_filter_tree(
            User,
            {'_or': {'username': 'admin', 'email__icontains': '@example.com'}},
        )

        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_filter_tree(
                User,
                {'_or': {'username': 'admin', 'groups__name': 'admin'}},
            )

    def test_ordering_allows_only_public_fields(self):
        ContentTypeContractsView.validate_ordering_fields(User, ['username', '-id'])

        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_ordering_fields(User, ['groups__name'])

    def test_declared_filter_fields_are_used_for_ordering(self):
        ContentTypeContractsView.validate_ordering_fields(self.UsernameOnlyModel, ['username'])

        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_ordering_fields(self.UsernameOnlyModel, ['email'])

    def test_contract_order_fields_can_be_stricter_than_filter_fields(self):
        contract = ContentTypeContract(
            app_label='auth',
            model='user',
            allowed_actions=frozenset({'list'}),
            policy=lambda context: True,
            filter_fields=frozenset({'username', 'email'}),
            order_fields=frozenset({'username'}),
        )

        ContentTypeContractsView.validate_ordering_fields(User, ['username'], contract=contract)

        with self.assertRaises(ValidationError):
            ContentTypeContractsView.validate_ordering_fields(User, ['email'], contract=contract)


if __name__ == '__main__':
    unittest.main()
