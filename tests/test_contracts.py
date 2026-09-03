import unittest

from drf_contenttype_contracts.tests.bootstrap import setup_django

setup_django()

from django.contrib.contenttypes.models import ContentType

from drf_contenttype_contracts.contracts import (
    DEFAULT_LOAD_STORE_ACTIONS,
    DEFAULT_READ_ACTIONS,
    AuthenticatedMutableContract,
    AuthenticatedReadOnlyContract,
    ContentTypeContract,
    ContentTypeLifecycle,
    DeclarativeContentTypeContract,
    PermissionCheckContext,
    UnauditedContentTypeContract,
    any_authenticated_user,
    contract_policy_applied,
    deny_all,
    mark_contract_policy_applied,
    normalize_actions,
    resolve_model_reference,
    resolve_serializer_from_map,
)


class FakeRequest:
    def __init__(self, user=None):
        self.user = user


class FakeUser:
    def __init__(self, is_authenticated):
        self.is_authenticated = is_authenticated


class FakeView:
    def __init__(self, action):
        self.action = action


class SerializerA:
    pass


class SerializerB:
    pass


class NormalizeActionsTests(unittest.TestCase):
    def test_none_defaults_to_read_actions(self):
        self.assertEqual(normalize_actions(None), DEFAULT_READ_ACTIONS)

    def test_single_string_becomes_singleton_set(self):
        self.assertEqual(normalize_actions('list'), frozenset({'list'}))

    def test_iterable_becomes_frozenset(self):
        self.assertEqual(normalize_actions(['list', 'retrieve']), frozenset({'list', 'retrieve'}))


class ResolveSerializerFromMapTests(unittest.TestCase):
    def test_none_map_returns_none(self):
        self.assertIsNone(resolve_serializer_from_map(None, 'list'))

    def test_bare_serializer_ignores_action(self):
        self.assertIs(resolve_serializer_from_map(SerializerA, 'anything'), SerializerA)

    def test_missing_action_returns_none(self):
        self.assertIsNone(resolve_serializer_from_map({'list': SerializerA}, 'retrieve'))

    def test_flat_action_map_returns_value_directly(self):
        self.assertIs(resolve_serializer_from_map({'list': SerializerA}, 'list'), SerializerA)

    def test_nested_map_missing_type_returns_none(self):
        serializer_map = {'list': {'default': SerializerA}}
        self.assertIsNone(resolve_serializer_from_map(serializer_map, 'list', 'summary'))

    def test_nested_map_returns_type_specific_serializer(self):
        serializer_map = {'list': {'default': SerializerA, 'summary': SerializerB}}
        self.assertIs(resolve_serializer_from_map(serializer_map, 'list', 'summary'), SerializerB)


class ResolveModelReferenceTests(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(resolve_model_reference(None))

    def test_object_with_meta_short_circuits(self):
        class StubMeta:
            app_label = 'app'
            model_name = 'model'

        class StubModel:
            _meta = StubMeta

        self.assertIs(resolve_model_reference(StubModel), StubModel)

    def test_string_without_dot_returns_none(self):
        self.assertIsNone(resolve_model_reference('user'))

    def test_unregistered_dotted_string_returns_none(self):
        self.assertIsNone(resolve_model_reference('nosuchapp.nosuchmodel'))

    def test_registered_dotted_string_resolves_model_class(self):
        self.assertIs(resolve_model_reference('contenttypes.contenttype'), ContentType)

    def test_registered_dotted_string_is_case_insensitive(self):
        self.assertIs(resolve_model_reference('contenttypes.ContentType'), ContentType)


class ContentTypeLifecycleTests(unittest.TestCase):
    def test_missing_hook_returns_none(self):
        lifecycle = ContentTypeLifecycle()
        self.assertIsNone(lifecycle.run('before_create', instance=None))

    def test_present_hook_is_called_with_kwargs_and_return_value_propagates(self):
        calls = []

        def before_create(**kwargs):
            calls.append(kwargs)
            return 'sentinel'

        lifecycle = ContentTypeLifecycle(before_create=before_create)
        result = lifecycle.run('before_create', instance='obj', request='req')
        self.assertEqual(result, 'sentinel')
        self.assertEqual(calls, [{'instance': 'obj', 'request': 'req'}])


class ContentTypeContractTests(unittest.TestCase):
    def _contract(self, **overrides):
        kwargs = dict(
            app_label='auth',
            model='user',
            allowed_actions=frozenset({'list', 'retrieve'}),
        )
        kwargs.update(overrides)
        return ContentTypeContract(**kwargs)

    def test_key_and_actions_properties(self):
        contract = self._contract()
        self.assertEqual(contract.key, ('auth', 'user'))
        self.assertEqual(contract.actions, contract.allowed_actions)

    def test_check_permission_denies_disallowed_action_without_consulting_policy(self):
        def exploding_policy(context):
            raise AssertionError('policy should not run for a disallowed action')

        contract = self._contract(policy=exploding_policy)
        view = FakeView(action='destroy')
        self.assertFalse(contract.check_permission(FakeRequest(), view))

    def test_check_permission_delegates_to_policy_for_allowed_action(self):
        contract_allow = self._contract(policy=lambda context: True)
        contract_deny = self._contract(policy=lambda context: False)
        view = FakeView(action='list')
        self.assertTrue(contract_allow.check_permission(FakeRequest(), view))
        self.assertFalse(contract_deny.check_permission(FakeRequest(), view))

    def test_check_permission_builds_permission_check_context(self):
        seen = {}

        def capturing_policy(context):
            seen['context'] = context
            return True

        contract = self._contract(policy=capturing_policy)
        request = FakeRequest()
        view = FakeView(action='list')
        contract.check_permission(request, view)
        self.assertEqual(
            seen['context'],
            PermissionCheckContext(request=request, view=view, action='list'),
        )

    def test_get_request_serializer_returns_none_for_disallowed_action(self):
        contract = self._contract(request_serializer_map={'create': SerializerA})
        self.assertIsNone(contract.get_request_serializer('create'))

    def test_get_request_serializer_prefers_operation_over_action(self):
        contract = self._contract(
            allowed_actions=frozenset({'add_or_edit'}),
            request_serializer_map={'add_or_edit': SerializerA, 'create': SerializerB},
        )
        self.assertIs(contract.get_request_serializer('add_or_edit', operation='create'), SerializerB)

    def test_get_request_serializer_falls_back_to_action_when_operation_unmatched(self):
        contract = self._contract(
            allowed_actions=frozenset({'add_or_edit'}),
            request_serializer_map={'add_or_edit': SerializerA},
        )
        self.assertIs(
            contract.get_request_serializer('add_or_edit', operation='update'),
            SerializerA,
        )

    def test_get_response_serializer_prefers_response_map_over_serializer_map(self):
        contract = self._contract(
            serializer_map={'list': SerializerA},
            response_serializer_map={'list': SerializerB},
        )
        self.assertIs(contract.get_response_serializer('list'), SerializerB)

    def test_get_response_serializer_falls_back_to_serializer_map(self):
        contract = self._contract(serializer_map={'list': SerializerA}, response_serializer_map=None)
        self.assertIs(contract.get_response_serializer('list'), SerializerA)

    def test_get_serializer_delegates_to_get_response_serializer(self):
        contract = self._contract(serializer_map={'list': SerializerA})
        self.assertEqual(contract.get_serializer('list'), contract.get_response_serializer('list'))


class DeclarativeContentTypeContractTests(unittest.TestCase):
    def test_missing_model_information_raises(self):
        class NoModelContract(DeclarativeContentTypeContract):
            pass

        with self.assertRaises(ValueError):
            NoModelContract.as_contract()

    def test_model_with_meta_object_resolves_app_label_and_model_name(self):
        class StubMeta:
            app_label = 'shop'
            model_name = 'product'

        class StubModel:
            _meta = StubMeta

        class ProductContract(DeclarativeContentTypeContract):
            model = StubModel

        contract = ProductContract.as_contract()
        self.assertEqual(contract.key, ('shop', 'product'))

    def test_get_model_hook_is_used_instead_of_model_attribute(self):
        class StubMeta:
            app_label = 'shop'
            model_name = 'variant'

        class StubModel:
            _meta = StubMeta

        class VariantContract(DeclarativeContentTypeContract):
            @classmethod
            def get_model(cls):
                return StubModel

        self.assertEqual(VariantContract.as_contract().key, ('shop', 'variant'))

    def test_unregistered_dotted_string_falls_back_to_split_and_lowercases(self):
        class WidgetContract(DeclarativeContentTypeContract):
            model = 'demoapp.Widget'

        self.assertEqual(WidgetContract.as_contract().key, ('demoapp', 'widget'))

    def test_registered_dotted_string_resolves_through_apps_registry(self):
        class ContentTypeContractDecl(DeclarativeContentTypeContract):
            model = 'contenttypes.ContentType'

        self.assertEqual(ContentTypeContractDecl.as_contract().key, ('contenttypes', 'contenttype'))

    def test_bare_model_name_without_dot_is_lowercased(self):
        class WidgetContract(DeclarativeContentTypeContract):
            app_label = 'demoapp'
            model = 'Widget'

        self.assertEqual(WidgetContract.as_contract().key, ('demoapp', 'widget'))

    def test_explicit_app_label_and_model_name_win_over_model(self):
        class StubMeta:
            app_label = 'ignored'
            model_name = 'ignored'

        class StubModel:
            _meta = StubMeta

        class OverrideContract(DeclarativeContentTypeContract):
            model = StubModel
            app_label = 'explicit'
            model_name = 'explicit_model'

        self.assertEqual(OverrideContract.as_contract().key, ('explicit', 'explicit_model'))

    def test_allowed_actions_overrides_actions(self):
        class ActionsContract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            actions = DEFAULT_READ_ACTIONS
            allowed_actions = frozenset({'destroy'})

        self.assertEqual(ActionsContract.as_contract().allowed_actions, frozenset({'destroy'}))

    def test_actions_used_when_allowed_actions_unset(self):
        class ActionsContract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            actions = frozenset({'list'})

        self.assertEqual(ActionsContract.as_contract().allowed_actions, frozenset({'list'}))

    def test_request_serializer_map_overrides_request_serializers(self):
        class RequestMapContract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            request_serializers = {'create': SerializerA}
            request_serializer_map = {'create': SerializerB}

        self.assertEqual(
            RequestMapContract.as_contract().request_serializer_map,
            {'create': SerializerB},
        )

    def test_request_serializers_used_when_request_serializer_map_unset(self):
        class RequestMapContract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            request_serializers = {'create': SerializerA}

        self.assertEqual(
            RequestMapContract.as_contract().request_serializer_map,
            {'create': SerializerA},
        )

    def test_response_serializer_map_fallback_chain(self):
        class OnlySerializer(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            serializer = SerializerA

        class OnlySerializerMap(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            serializer = SerializerA
            serializer_map = {'list': SerializerB}

        class OnlyResponseSerializers(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            serializer_map = {'list': SerializerA}
            response_serializers = {'list': SerializerB}

        class OnlyResponseSerializerMap(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            response_serializers = {'list': SerializerA}
            response_serializer_map = {'list': SerializerB}

        self.assertIs(OnlySerializer.as_contract().response_serializer_map, SerializerA)
        self.assertEqual(OnlySerializerMap.as_contract().response_serializer_map, {'list': SerializerB})
        self.assertEqual(
            OnlyResponseSerializers.as_contract().response_serializer_map,
            {'list': SerializerB},
        )
        self.assertEqual(
            OnlyResponseSerializerMap.as_contract().response_serializer_map,
            {'list': SerializerB},
        )

    def test_serializer_map_field_mirrors_response_serializer_map(self):
        class Contract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            serializer = SerializerA

        contract = Contract.as_contract()
        self.assertIs(contract.serializer_map, SerializerA)
        self.assertIs(contract.response_serializer_map, SerializerA)

    def test_permissions_overrides_policy(self):
        def policy_fn(context):
            return False

        def permissions_fn(context):
            return True

        class Contract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            policy = staticmethod(policy_fn)
            permissions = staticmethod(permissions_fn)

        self.assertIs(Contract.as_contract().policy, permissions_fn)

    def test_lifecycle_defaults_to_empty_instance(self):
        class Contract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'

        contract = Contract.as_contract()
        self.assertEqual(contract.lifecycle, ContentTypeLifecycle())

    def test_explicit_lifecycle_is_preserved(self):
        explicit_lifecycle = ContentTypeLifecycle(before_create=lambda **kwargs: None)

        class Contract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'
            lifecycle = explicit_lifecycle

        self.assertIs(Contract.as_contract().lifecycle, explicit_lifecycle)


class ContractBaseClassesTests(unittest.TestCase):
    def test_authenticated_read_only_contract_defaults(self):
        class UserContract(AuthenticatedReadOnlyContract):
            app_label = 'auth'
            model_name = 'user'

        contract = UserContract.as_contract()
        self.assertEqual(contract.allowed_actions, DEFAULT_READ_ACTIONS)
        self.assertIs(contract.policy, any_authenticated_user)

    def test_authenticated_mutable_contract_defaults(self):
        class UserContract(AuthenticatedMutableContract):
            app_label = 'auth'
            model_name = 'user'

        contract = UserContract.as_contract()
        self.assertEqual(contract.allowed_actions, DEFAULT_LOAD_STORE_ACTIONS)
        self.assertIs(contract.policy, any_authenticated_user)

    def test_unaudited_contract_fills_missing_policy_actions_by_default(self):
        class LegacyContract(UnauditedContentTypeContract):
            app_label = 'auth'
            model_name = 'user'

        contract = LegacyContract.as_contract()
        self.assertEqual(contract.missing_policy_actions, contract.allowed_actions)

    def test_unaudited_contract_respects_explicit_missing_policy_actions(self):
        class LegacyContract(UnauditedContentTypeContract):
            app_label = 'auth'
            model_name = 'user'
            missing_policy_actions = frozenset({'destroy'})

        contract = LegacyContract.as_contract()
        self.assertEqual(contract.missing_policy_actions, frozenset({'destroy'}))


class PolicyHelperTests(unittest.TestCase):
    def test_deny_all_always_false(self):
        context = PermissionCheckContext(request=FakeRequest(), view=FakeView('list'), action='list')
        self.assertFalse(deny_all(context))

    def test_any_authenticated_user_with_no_user(self):
        context = PermissionCheckContext(request=FakeRequest(user=None), view=FakeView('list'), action='list')
        self.assertFalse(any_authenticated_user(context))

    def test_any_authenticated_user_with_unauthenticated_user(self):
        request = FakeRequest(user=FakeUser(is_authenticated=False))
        context = PermissionCheckContext(request=request, view=FakeView('list'), action='list')
        self.assertFalse(any_authenticated_user(context))

    def test_any_authenticated_user_with_authenticated_user(self):
        request = FakeRequest(user=FakeUser(is_authenticated=True))
        context = PermissionCheckContext(request=request, view=FakeView('list'), action='list')
        self.assertTrue(any_authenticated_user(context))


class ContractPolicyAppliedMarkerTests(unittest.TestCase):
    def test_unmarked_request_reports_not_applied(self):
        self.assertFalse(contract_policy_applied(FakeRequest()))

    def test_mark_then_check_round_trips(self):
        request = FakeRequest()
        mark_contract_policy_applied(request, 'auth', 'user', 'list')
        self.assertTrue(contract_policy_applied(request))


if __name__ == '__main__':
    unittest.main()
