from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields.related import RelatedField
from rest_framework import serializers


class ContentTypeListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentType
        fields = '__all__'


class FilterItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    verbose_name = serializers.CharField()


class ContentTypeFilterSerializer(serializers.Serializer):
    filter_fields = serializers.SerializerMethodField()

    def get_filter_fields(self, model):
        contract_filter_fields = self.context.get('filter_fields')
        if contract_filter_fields is not None:
            return [
                {
                    'name': field_name,
                    'verbose_name': self.get_verbose_name(model, field_name),
                }
                for field_name in sorted(contract_filter_fields)
            ]

        if hasattr(model, 'filter_fields'):
            fields = list(filter(lambda x: x.name in model.filter_fields, model._meta.fields))
        else:
            fields = list(model._meta.fields)
        return FilterItemSerializer(fields, many=True).data

    @staticmethod
    def get_verbose_name(model, field_name):
        try:
            field = model._meta.get_field(field_name)
        except FieldDoesNotExist:
            for field in model._meta.fields:
                if getattr(field, 'attname', None) == field_name:
                    return str(field.verbose_name)
            return field_name
        return str(field.verbose_name)


class ContentTypeInstanceListSerializer(serializers.Serializer):
    app_label = serializers.CharField()
    model = serializers.CharField()
    serializer_type = serializers.CharField(allow_blank=True, required=False)
    search = serializers.CharField(allow_blank=True, required=False)
    order = serializers.CharField(allow_blank=True, required=False)
    start_index = serializers.IntegerField(required=False)
    stop_index = serializers.IntegerField(required=False)
    all = serializers.BooleanField(default=False)
    filters = serializers.DictField(required=False)
    excludes = serializers.DictField(required=False)


class ContentTypeInstanceRetrieveSerializer(serializers.Serializer):
    app_label = serializers.CharField()
    model = serializers.CharField()
    id = serializers.CharField(required=False)
    uuid = serializers.UUIDField(required=False)
    external_id = serializers.UUIDField(required=False)
    serializer_type = serializers.CharField(allow_blank=True, required=False)


class ContentTypeInstanceDeleteSerializer(serializers.Serializer):
    app_label = serializers.CharField()
    model = serializers.CharField()
    id = serializers.CharField()


class ContentTypeInstanceAddOrEditSerializer(serializers.Serializer):
    app_label = serializers.CharField()
    model = serializers.CharField()
    data = serializers.DictField()

    def validate(self, attrs):
        app_label = attrs.get('app_label')
        model = attrs.get('model')
        data = attrs.get('data')
        object_id = data.get('id')

        try:
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError('model does not exist')

        model_class = content_type.model_class()
        if model_class is None:
            raise serializers.ValidationError(
                f'Model class is not available for {app_label}.{model}. '
                f'Possible stale django_content_type row.'
            )
        attrs.update(model_class=model_class)

        if object_id:
            try:
                attrs.update(instance=content_type.get_object_for_this_type(pk=object_id))
            except Exception as exc:
                raise serializers.ValidationError(f'object does not exist {str(exc)}')
        return attrs

    def create(self, validated_data):
        model_class = validated_data.get('model_class')
        data = validated_data.get('data')
        return model_class.objects.create(**data)

    def update(self, instance, validated_data):
        data = validated_data.get('data')
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    def to_representation(self, instance):
        serializer = DynamicRetrieveModelSerializer.create_dynamical_serializer(instance.__class__)
        return serializer().to_representation(instance)


class DynamicRetrieveModelSerializer:
    def __new__(
        cls,
        app_label,
        model,
        *args,
        exclude_fields=None,
        with_pk=True,
        serializer_name=None,
        **kwargs,
    ):
        return cls.from_content_type(
            app_label,
            model,
            exclude_fields=exclude_fields,
            with_pk=with_pk,
            serializer_name=serializer_name,
        )

    @classmethod
    def from_content_type(
        cls,
        app_label,
        model,
        *,
        exclude_fields=None,
        with_pk=True,
        serializer_name=None,
    ):
        resolved = {}
        serializer_name = serializer_name or cls.build_serializer_name(app_label, model)

        def resolve():
            if 'serializer_class' not in resolved:
                model_class = None
                try:
                    model_class = django_apps.get_model(
                        app_label,
                        model,
                        require_ready=False,
                    )
                except LookupError:
                    pass

                if model_class is None:
                    content_type = ContentType.objects.get(app_label=app_label, model=model)
                    model_class = content_type.model_class()
                if model_class is None:
                    raise serializers.ValidationError(
                        f'Model class is not available for {app_label}.{model}. '
                        f'Possible stale django_content_type row.'
                    )
                resolved['serializer_class'] = cls.create_dynamical_serializer(
                    model_class,
                    exclude_fields=exclude_fields,
                    with_pk=with_pk,
                )
            return resolved['serializer_class']

        return cls.create_lazy_serializer(resolve, serializer_name=serializer_name)

    @classmethod
    def from_model_ref(
        cls,
        model_ref,
        *,
        exclude_fields=None,
        with_pk=True,
        serializer_name=None,
    ):
        resolved = {}
        serializer_name = serializer_name or cls.build_serializer_name_from_ref(model_ref)

        def resolve():
            if 'serializer_class' not in resolved:
                model_class = cls.resolve_model_class(model_ref)
                resolved['serializer_class'] = cls.create_dynamical_serializer(
                    model_class,
                    exclude_fields=exclude_fields,
                    with_pk=with_pk,
                )
            return resolved['serializer_class']

        return cls.create_lazy_serializer(resolve, serializer_name=serializer_name)

    @staticmethod
    def create_lazy_serializer(resolve, serializer_name='LazyDynamicSerializer'):
        class LazyDynamicSerializer:
            def __new__(cls, *args, **kwargs):
                return resolve()(*args, **kwargs)

        LazyDynamicSerializer.__name__ = serializer_name
        LazyDynamicSerializer.__qualname__ = serializer_name
        return LazyDynamicSerializer

    @classmethod
    def build_serializer_name_from_ref(cls, model_ref):
        if isinstance(model_ref, str) and '.' in model_ref:
            app_label, model = model_ref.split('.', 1)
            return cls.build_serializer_name(app_label, model)
        if hasattr(model_ref, '_meta'):
            return cls.build_serializer_name(
                model_ref._meta.app_label,
                model_ref._meta.model_name,
            )
        return 'LazyDynamicSerializer'

    @staticmethod
    def build_serializer_name(*parts):
        tokens = []
        for part in parts:
            normalized = ''.join(
                char if char.isalnum() else '_'
                for char in str(part)
            )
            tokens.extend(token for token in normalized.split('_') if token)
        if not tokens:
            return 'LazyDynamicSerializer'
        return f'Dynamic{"".join(token[:1].upper() + token[1:] for token in tokens)}Serializer'

    @staticmethod
    def resolve_model_class(model_ref):
        if callable(model_ref) and not hasattr(model_ref, '_meta'):
            model_ref = model_ref()

        if hasattr(model_ref, '_meta'):
            return model_ref

        if isinstance(model_ref, str) and '.' in model_ref:
            app_label, model = model_ref.split('.', 1)
            return django_apps.get_model(app_label, model, require_ready=False)

        raise serializers.ValidationError(f'Invalid model reference {model_ref!r}')

    @staticmethod
    def get_model_fields(model_class, with_pk=True, exclude_fields=None):
        exclude_fields = {str(field) for field in (exclude_fields or ())}
        fields = []
        for field in model_class._meta.get_fields(include_parents=False):
            if hasattr(field, 'primary_key') and field.primary_key:
                if not with_pk:
                    continue

            field_name = None
            if hasattr(field, 'is_relation') and field.is_relation:
                if isinstance(field, RelatedField):
                    field_name = getattr(field, 'attname', field.name)
            else:
                field_name = field.name

            if field_name is None:
                continue

            field_aliases = {field_name, getattr(field, 'name', None), getattr(field, 'attname', None)}
            if exclude_fields.intersection(field_aliases):
                continue

            fields.append(field_name)
        return fields

    @classmethod
    def create_dynamical_serializer(cls, model_class, *, exclude_fields=None, with_pk=True):
        return type(f'dynamical_serializer_{model_class.__name__}', (
            serializers.ModelSerializer,
        ), {
            'Meta': type('Meta', (), {
                'model': model_class,
                'fields': cls.get_model_fields(
                    model_class,
                    exclude_fields=exclude_fields,
                    with_pk=with_pk,
                ),
            })
        })
