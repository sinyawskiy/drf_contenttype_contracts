from django.contrib.contenttypes.models import ContentType
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
        if getattr(model, 'filter_fields', None):
            fields = list(filter(lambda x: x.name in model.filter_fields, model._meta.fields))
        else:
            fields = list(model._meta.fields)
        return FilterItemSerializer(fields, many=True).data


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
    id = serializers.IntegerField(required=False)
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
    def __new__(cls, app_label, model, *args, **kwargs):
        resolved = {}

        def resolve():
            if 'serializer_class' not in resolved:
                content_type = ContentType.objects.get(app_label=app_label, model=model)
                model_class = content_type.model_class()
                if model_class is None:
                    raise serializers.ValidationError(
                        f'Model class is not available for {app_label}.{model}. '
                        f'Possible stale django_content_type row.'
                    )
                resolved['serializer_class'] = cls.create_dynamical_serializer(model_class)
            return resolved['serializer_class']

        class LazyDynamicSerializer:
            def __new__(lazy_cls, *a, **kw):
                return resolve()(*a, **kw)

        return LazyDynamicSerializer

    @staticmethod
    def get_model_fields(model_class, with_pk=True):
        fields = []
        for field in model_class._meta.get_fields(include_parents=False):
            if hasattr(field, 'primary_key') and field.primary_key:
                if not with_pk:
                    continue

            if hasattr(field, 'is_relation') and field.is_relation:
                if isinstance(field, RelatedField):
                    fields.append(field.attname)
            else:
                fields.append(field.name)
        return fields

    @classmethod
    def create_dynamical_serializer(cls, model_class):
        return type(f'dynamical_serializer_{model_class.__name__}', (
            serializers.ModelSerializer,
        ), {
            'Meta': type('Meta', (), {
                'model': model_class,
                'fields': cls.get_model_fields(model_class),
            })
        })
