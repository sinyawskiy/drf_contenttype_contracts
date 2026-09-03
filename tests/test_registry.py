import io
import types
import unittest

from drf_contenttype_contracts.contracts import (
    ContentTypeContract,
    ContentTypeLifecycle,
    DeclarativeContentTypeContract,
    deny_all,
)
from drf_contenttype_contracts.registry import (
    ContentTypeContractRegistry,
    contract_signature,
    default_registry,
    is_contract_class,
    serializer_map_to_names,
    serializer_name,
)


class SerializerA:
    pass


class SerializerB:
    pass


def make_contract(app_label='auth', model='user', **overrides):
    kwargs = dict(
        app_label=app_label,
        model=model,
        allowed_actions=frozenset({'list', 'retrieve'}),
        serializer_map={'list': SerializerA, 'retrieve': SerializerA},
    )
    kwargs.update(overrides)
    return ContentTypeContract(**kwargs)


class IsContractClassTests(unittest.TestCase):
    def test_concrete_subclass_is_a_contract_class(self):
        class ConcreteContract(DeclarativeContentTypeContract):
            app_label = 'a'
            model_name = 'b'

        self.assertTrue(is_contract_class(ConcreteContract))

    def test_abstract_subclass_is_excluded(self):
        class AbstractContract(DeclarativeContentTypeContract):
            abstract = True

        self.assertFalse(is_contract_class(AbstractContract))

    def test_base_class_itself_is_excluded(self):
        self.assertFalse(is_contract_class(DeclarativeContentTypeContract))

    def test_unrelated_class_is_excluded(self):
        class NotAContract:
            pass

        self.assertFalse(is_contract_class(NotAContract))

    def test_non_class_value_is_excluded(self):
        self.assertFalse(is_contract_class(make_contract()))
        self.assertFalse(is_contract_class('not a class'))
        self.assertFalse(is_contract_class(None))


class RegisterTests(unittest.TestCase):
    def test_register_contract_instance(self):
        registry = ContentTypeContractRegistry()
        contract = make_contract()
        registered = registry.register(contract)
        self.assertIs(registered, contract)
        self.assertIs(registry.get('auth', 'user'), contract)

    def test_register_declarative_class_is_converted(self):
        class UserContract(DeclarativeContentTypeContract):
            app_label = 'auth'
            model_name = 'user'
            serializer = SerializerA

        registry = ContentTypeContractRegistry()
        registered = registry.register(UserContract)
        self.assertIsInstance(registered, ContentTypeContract)
        self.assertEqual(registered.key, ('auth', 'user'))

    def test_reregistering_identical_definition_returns_existing_instance(self):
        registry = ContentTypeContractRegistry()
        first = registry.register(make_contract())
        second = registry.register(make_contract())  # a structurally-identical, distinct instance
        self.assertIs(registry.get('auth', 'user'), first)
        self.assertIs(second, first)  # register() returns the original, not the new instance

    def test_reregistering_conflicting_definition_raises(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract())
        with self.assertRaises(ValueError):
            registry.register(make_contract(allowed_actions=frozenset({'list', 'retrieve', 'destroy'})))

    def test_reregistering_conflicting_definition_leaves_original_in_place(self):
        registry = ContentTypeContractRegistry()
        original = registry.register(make_contract())
        try:
            registry.register(make_contract(policy=deny_all))
        except ValueError:
            pass
        self.assertIs(registry.get('auth', 'user'), original)


class RegisterModuleTests(unittest.TestCase):
    def test_only_concrete_contract_classes_are_registered(self):
        class OneContract(DeclarativeContentTypeContract):
            app_label = 'auth'
            model_name = 'user'

        class AbstractContract(DeclarativeContentTypeContract):
            abstract = True

        module = types.ModuleType('fake_content_type_contracts')
        module.OneContract = OneContract
        module.AbstractContract = AbstractContract
        module.SOME_CONSTANT = 42
        module.helper = lambda: None

        registry = ContentTypeContractRegistry()
        registered = registry.register_module(module)

        self.assertEqual(len(registered), 1)
        self.assertEqual(registry.registered_keys(), (('auth', 'user'),))


class AutodiscoverTests(unittest.TestCase):
    def test_autodiscover_registers_contracts_from_installed_apps(self):
        registry = ContentTypeContractRegistry()
        modules = registry.autodiscover()

        self.assertTrue(any(module.__name__.endswith('testapp.content_type_contracts') for module in modules))
        self.assertIn(('testapp', 'widget'), registry.registered_keys())

    def test_autodiscover_skips_apps_without_the_module(self):
        # 'django.contrib.contenttypes' has no content_type_contracts submodule;
        # autodiscover must not raise for it.
        registry = ContentTypeContractRegistry()
        registry.autodiscover()
        self.assertNotIn('contenttypes', {app_label for app_label, _ in registry.registered_keys()})


class LookupTests(unittest.TestCase):
    def test_get_and_is_registered_for_unknown_key(self):
        registry = ContentTypeContractRegistry()
        self.assertIsNone(registry.get('auth', 'user'))
        self.assertFalse(registry.is_registered('auth', 'user'))

    def test_get_and_is_registered_after_registration(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract())
        self.assertTrue(registry.is_registered('auth', 'user'))
        self.assertEqual(registry.get('auth', 'user').key, ('auth', 'user'))

    def test_registered_keys_are_sorted(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract(app_label='shop', model='product'))
        registry.register(make_contract(app_label='auth', model='user'))
        self.assertEqual(
            registry.registered_keys(),
            (('auth', 'user'), ('shop', 'product')),
        )


class SerializerLookupTests(unittest.TestCase):
    def test_get_serializer_for_unregistered_contract_returns_none(self):
        registry = ContentTypeContractRegistry()
        self.assertIsNone(registry.get_serializer('auth', 'user', 'list'))

    def test_get_serializer_delegates_to_contract(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract())
        self.assertIs(registry.get_serializer('auth', 'user', 'list'), SerializerA)

    def test_get_request_serializer_for_unregistered_contract_returns_none(self):
        registry = ContentTypeContractRegistry()
        self.assertIsNone(registry.get_request_serializer('auth', 'user', 'create'))

    def test_get_request_serializer_delegates_to_contract(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract(
            allowed_actions=frozenset({'add_or_edit'}),
            request_serializer_map={'create': SerializerB},
        ))
        self.assertIs(
            registry.get_request_serializer('auth', 'user', 'add_or_edit', operation='create'),
            SerializerB,
        )


class IterSerializerBindingsTests(unittest.TestCase):
    def test_bare_serializer_map_yields_one_binding_per_allowed_action(self):
        contract = make_contract(serializer_map=SerializerA)
        registry = ContentTypeContractRegistry()
        registry.register(contract)

        bindings = list(registry.iter_serializer_bindings())
        self.assertEqual(
            sorted((b['action'], b['serializer_type'], b['serializer']) for b in bindings),
            [('list', 'default', 'SerializerA'), ('retrieve', 'default', 'SerializerA')],
        )

    def test_nested_serializer_map_yields_per_action_and_type(self):
        contract = make_contract(serializer_map={
            'list': {'default': SerializerA, 'summary': SerializerB},
        })
        registry = ContentTypeContractRegistry()
        registry.register(contract)

        bindings = list(registry.iter_serializer_bindings(contract))
        self.assertEqual(
            sorted((b['action'], b['serializer_type'], b['serializer']) for b in bindings),
            [('list', 'default', 'SerializerA'), ('list', 'summary', 'SerializerB')],
        )

    def test_without_contract_argument_iterates_all_registered_contracts(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract(app_label='auth', model='user', serializer_map=SerializerA))
        registry.register(make_contract(app_label='shop', model='product', serializer_map=SerializerB))

        models = {b['model'] for b in registry.iter_serializer_bindings()}
        self.assertEqual(models, {'auth.user', 'shop.product'})


class ToModelSerializerMapTests(unittest.TestCase):
    def test_matches_documented_shape(self):
        registry = ContentTypeContractRegistry()
        registry.register(make_contract(serializer_map=SerializerA))

        self.assertEqual(registry.to_model_serializer_map(), {'auth': {'user': 'SerializerA'}})

    def test_json_variant_round_trips_through_json(self):
        import json

        registry = ContentTypeContractRegistry()
        registry.register(make_contract(serializer_map=SerializerA))

        payload = json.loads(registry.to_model_serializer_map_json())
        self.assertEqual(payload, {'auth': {'user': 'SerializerA'}})


class ContractSignatureTests(unittest.TestCase):
    def test_structurally_identical_contracts_have_equal_signatures(self):
        self.assertEqual(contract_signature(make_contract()), contract_signature(make_contract()))

    def test_different_policy_changes_signature(self):
        a = make_contract(policy=deny_all)
        b = make_contract(policy=lambda context: True)
        self.assertNotEqual(contract_signature(a), contract_signature(b))

    def test_different_lifecycle_hook_changes_signature(self):
        a = make_contract(lifecycle=ContentTypeLifecycle())
        b = make_contract(lifecycle=ContentTypeLifecycle(before_create=lambda **kwargs: None))
        self.assertNotEqual(contract_signature(a), contract_signature(b))


class SerializerNamingTests(unittest.TestCase):
    def test_serializer_name_for_none(self):
        self.assertIsNone(serializer_name(None))

    def test_serializer_name_for_class(self):
        self.assertEqual(serializer_name(SerializerA), 'SerializerA')

    def test_serializer_name_for_instance(self):
        self.assertEqual(serializer_name(SerializerA()), 'SerializerA')

    def test_serializer_map_to_names_recurses_nested_dicts(self):
        serializer_map = {'list': {'default': SerializerA, 'summary': SerializerB}}
        self.assertEqual(
            serializer_map_to_names(serializer_map),
            {'list': {'default': 'SerializerA', 'summary': 'SerializerB'}},
        )

    def test_serializer_map_to_names_for_none(self):
        self.assertIsNone(serializer_map_to_names(None))


class DebugOutputTests(unittest.TestCase):
    def test_debug_true_prints_one_line_per_binding(self):
        stream = io.StringIO()
        registry = ContentTypeContractRegistry(debug=True, debug_stream=stream)
        registry.register(make_contract(serializer_map=SerializerA))

        output = stream.getvalue()
        self.assertIn('model=auth.user action=list type=default serializer=SerializerA', output)
        self.assertIn('model=auth.user action=retrieve type=default serializer=SerializerA', output)

    def test_debug_false_prints_nothing(self):
        stream = io.StringIO()
        registry = ContentTypeContractRegistry(debug=False, debug_stream=stream)
        registry.register(make_contract())
        self.assertEqual(stream.getvalue(), '')


class DefaultRegistryTests(unittest.TestCase):
    def test_default_registry_is_a_registry_instance(self):
        self.assertIsInstance(default_registry, ContentTypeContractRegistry)


if __name__ == '__main__':
    unittest.main()
