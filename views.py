import json
import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.serializers import ValidationError as SerializerValidationError
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT

from drf_contenttype_contracts.registry import default_registry
from drf_contenttype_contracts.serializers import (
    ContentTypeInstanceAddOrEditSerializer,
    ContentTypeFilterSerializer,
    ContentTypeInstanceDeleteSerializer,
    ContentTypeInstanceListSerializer,
    ContentTypeInstanceRetrieveSerializer,
)


logger = logging.getLogger(__name__)


class ContentTypeContractsView(viewsets.GenericViewSet):
    contract_registry = default_registry
    parser_classes = (JSONParser,)
    filter_serializer_class = ContentTypeFilterSerializer
    delete_signal = None
    limit_content_type_list_setting = 'DRF_CONTENTTYPE_CONTRACTS_LIMIT_CONTENTTYPE_LIST'
    serializer_classes = {
        'list': ContentTypeInstanceListSerializer,
        'retrieve': ContentTypeInstanceRetrieveSerializer,
        'destroy': ContentTypeInstanceDeleteSerializer,
        'add_or_edit': ContentTypeInstanceAddOrEditSerializer,
    }

    def get_contract_registry(self):
        return self.contract_registry

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action)

    @staticmethod
    def apply_filters(qs, filters, exclude=False):
        from django.db.models import Q

        condition = ContentTypeContractsView.create_condition(filters, Q.AND)
        if exclude:
            return qs.exclude(condition)
        return qs.filter(condition).distinct()

    @staticmethod
    def apply_ordering(qs, order_by):
        return qs.order_by(*order_by)

    @staticmethod
    def create_condition(filters, op):
        from django.db.models import Q

        operators_map = {
            '_and': Q.AND,
            '_or': Q.OR,
        }
        condition = Q()
        for key in filters.keys():
            if key in operators_map:
                condition.add(
                    ContentTypeContractsView.create_condition(filters[key], operators_map[key]),
                    op,
                )
            else:
                condition.add(Q(**{key: filters[key]}), op)
        return condition

    def set_model_class(self):
        app_label = self.request.data.get('app_label')
        model = self.request.data.get('model')
        try:
            content_type = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            raise ValidationError({'errors': f'ContentType not found for {app_label}.{model}'})
        self.model_class = content_type.model_class()
        if self.model_class is None:
            raise ValidationError({'errors': f'Model class is not available for {app_label}.{model}. '
                                             f'Possible stale django_content_type row.'})

    def base_queryset(self):
        if getattr(self.model_class, 'list_queryset', None):
            queryset = self.model_class.list_queryset(**{'request': self.request})
        else:
            queryset = self.model_class.objects.all()

        if self.should_limit_content_type_queryset():
            return self.registered_content_types_queryset(queryset)
        return queryset

    def should_limit_content_type_queryset(self) -> bool:
        return (
            self.model_class is ContentType
            and bool(getattr(settings, self.limit_content_type_list_setting, True))
        )

    def registered_content_types_queryset(self, queryset):
        keys = self.get_contract_registry().registered_keys()
        if not keys:
            return queryset.none()

        condition = Q()
        for app_label, model in keys:
            condition |= Q(app_label=app_label, model=model)
        return queryset.filter(condition)

    def get_content_type_queryset(self, data):
        self.set_model_class()

        queryset = self.base_queryset()

        if getattr(self.model_class, 'published', None):
            queryset = queryset.filter(published=True)

        include_all = data.get('all')
        filters = data.get('filters', {})
        exclude_filters = data.get('excludes', {})
        search = data.get('search', '')
        start_index = data.get('start_index', 0)
        stop_index = data.get('stop_index', 5)
        order = data.get('order', '')

        if order:
            order_by = order.split(';')
        else:
            order_by = self.model_class._meta.ordering or ''

        filtering_method = getattr(
            self.model_class,
            'apply_filters',
            ContentTypeContractsView.apply_filters,
        )
        if 'app_label' in filters and 'model' in filters:
            filters_app_label = filters.pop('app_label')
            filters_model = filters.pop('model')
            if filters_app_label and filters_model:
                try:
                    filters_content_type = ContentType.objects.get(
                        app_label=filters_app_label,
                        model=filters_model,
                    )
                except ContentType.DoesNotExist:
                    pass
                else:
                    if isinstance(filters_content_type, ContentType):
                        filters['id'] = filters_content_type.id
                    else:
                        filters['content_type_id'] = filters_content_type.id
        queryset = filtering_method(queryset, filters)
        queryset = filtering_method(queryset, exclude_filters, exclude=True)

        full_match_exists = None
        if search:
            queryset = self.model_class.set_filter(queryset, search)
            try:
                full_match_exists_method = getattr(self.model_class, 'full_match_exists')
            except AttributeError:
                pass
            else:
                full_match_exists = full_match_exists_method(queryset, search)

        if order_by:
            ordering_method = getattr(
                self.model_class,
                'apply_ordering',
                ContentTypeContractsView.apply_ordering,
            )
            queryset = ordering_method(queryset, order_by)

        count = queryset.count()

        if include_all:
            return queryset, count, 0, count, order, search, full_match_exists

        queryset = queryset[start_index:stop_index + 1]
        return queryset, count, start_index, stop_index, order, search, full_match_exists

    def get_model_serializer(self):
        app_label = self.request.data.get('app_label')
        model = self.request.data.get('model')
        serializer_type = self.request.data.get('serializer_type', 'default')
        contract_registry = self.get_contract_registry()
        serializer_class = contract_registry.get_serializer(
            app_label,
            model,
            self.action,
            serializer_type,
        )
        if serializer_class is not None:
            return serializer_class

        contract = contract_registry.get(app_label, model)
        if contract is not None:
            if self.action not in contract.allowed_actions:
                raise SerializerValidationError({
                    'errors': f'Action {self.action} is not registered for {app_label}.{model}'
                })
            raise SerializerValidationError({
                'errors': f'Serializer is not registered for {app_label}.{model}.{self.action}'
            })

        raise SerializerValidationError({
            'errors': f'Serializer is not registered for {app_label}.{model}.{self.action}'
        })

    def list(self, request):
        content_type_serializer = self.get_serializer_class()
        content_type_data = content_type_serializer(data=request.data)

        try:
            content_type_data.is_valid(raise_exception=True)
        except ValidationError as exc:
            return Response(exc.detail, status=HTTP_200_OK)

        try:
            queryset, count, start_index, stop_index, order, search, full_match_exists = (
                self.get_content_type_queryset(content_type_data.data)
            )
        except ValidationError as exc:
            return Response(exc.detail, status=HTTP_200_OK)
        except Exception as exc:
            logger.exception(
                'ContentTypeContractsView list failed for request=%s',
                json.dumps(request.data, indent=4, sort_keys=True, ensure_ascii=False),
            )
            raise exc

        serializer_class = self.get_model_serializer()
        serializer = serializer_class(queryset, many=True, context={'request': request})

        data = {
            'start_index': start_index,
            'stop_index': stop_index,
            'total': count,
            'elements': serializer.data,
            'order': order,
            'search': search,
        }
        if full_match_exists is not None:
            data['full_match_exists'] = full_match_exists
        data.update(self.filter_serializer_class(self.model_class).data)

        return Response(data, status=HTTP_200_OK)

    def retrieve(self, request, *args):
        app_label = request.data.get('app_label')
        model_name = request.data.get('model')
        logger.info('Retrieving content type instance %s.%s', app_label, model_name)
        content_type = ContentType.objects.get(app_label=app_label, model=model_name)
        model = content_type.model_class()
        if model is None:
            logger.error('Model class is None for content type %s.%s', app_label, model_name)
            return Response(
                {'error': f"Модель {app_label}.{model_name} недоступна "
                          f"(возможна устаревшая запись django_content_type)"},
                status=HTTP_200_OK,
            )

        if 'id' in request.data:
            try:
                instance = model.objects.get(id=request.data['id'])
            except model.DoesNotExist:
                logger.error('Instance with ID %s not found for model %s', request.data['id'], model.__name__)
                return Response({'error': f'Указанного объекта класса {model.__name__} не существует'})
        elif 'uuid' in request.data:
            try:
                instance = model.objects.get(uuid=request.data['uuid'])
            except model.DoesNotExist:
                logger.error('Instance with UUID %s not found for model %s', request.data['uuid'], model.__name__)
                return Response({'error': f'Указанного объекта класса {model.__name__} не существует'})
        elif 'external_id' in request.data:
            if not hasattr(model, 'external_id'):
                logger.error('Model %s does not support external_id lookup', model.__name__)
                return Response({'error': f'Класс {model.__name__} не поддерживает поиск по external_id'})
            try:
                instance = model.objects.get(external_id=request.data['external_id'])
            except (model.DoesNotExist, ValueError):
                logger.error(
                    'Instance with external_id %s not found for model %s',
                    request.data['external_id'],
                    model.__name__,
                )
                return Response({'error': f'Указанного объекта класса {model.__name__} не существует'})
        else:
            logger.warning('No ID, UUID or external_id provided for content type retrieval')
            return Response('Необходимые поля id, uuid или external_id', status=HTTP_200_OK)

        model_serializer_class = self.get_model_serializer()
        serializer = model_serializer_class(instance, context={'request': request})
        return Response(serializer.data, status=HTTP_200_OK)

    def add_or_edit(self, request):
        contract = self.get_contract_registry().get(
            request.data.get('app_label'),
            request.data.get('model'),
        )
        serializer_type = request.data.get('serializer_type', 'default')
        payload = request.data.get('data')
        payload = payload if isinstance(payload, dict) else {}
        operation = 'update' if payload.get('id') else 'create'

        request_serializer_class = None
        if contract is not None:
            request_serializer_class = contract.get_request_serializer(
                self.action,
                serializer_type=serializer_type,
                operation=operation,
            )

        if request_serializer_class is not None:
            instance = None
            if operation == 'update':
                content_type = ContentType.objects.get(
                    app_label=request.data.get('app_label'),
                    model=request.data.get('model'),
                )
                instance = content_type.get_object_for_this_type(pk=payload.get('id'))
            serializer = request_serializer_class(
                instance,
                data=payload,
                context={'request': request},
            )
            try:
                serializer.is_valid(raise_exception=True)
            except ValidationError as exc:
                logger.error('Validation error in add_or_edit: %s', exc.detail)
                return Response({'errors': exc.detail}, status=HTTP_200_OK)

            before_hook = 'before_update' if instance else 'before_create'
            after_hook = 'after_update' if instance else 'after_create'
            contract.lifecycle.run(
                before_hook,
                request=request,
                view=self,
                instance=instance,
                validated_data=serializer.validated_data,
            )
            instance = serializer.save()
            contract.lifecycle.run(
                after_hook,
                request=request,
                view=self,
                instance=instance,
                validated_data=serializer.validated_data,
            )

            response_serializer_class = (
                contract.get_response_serializer(self.action, serializer_type)
                or contract.get_response_serializer('retrieve', serializer_type)
            )
            if response_serializer_class is not None:
                response_serializer = response_serializer_class(
                    instance,
                    context={'request': request},
                )
                return Response(response_serializer.data, status=HTTP_200_OK)
            return Response(serializer.data, status=HTTP_200_OK)

        serializer_class = self.get_serializer_class()
        serializer = serializer_class(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            logger.error('Validation error in add_or_edit: %s', exc.detail)
            return Response({'errors': exc.detail}, status=HTTP_200_OK)
        instance = serializer.validated_data.get('instance')
        if instance:
            serializer.update(instance, serializer.validated_data)
        else:
            instance = serializer.create(serializer.validated_data)
        return Response(serializer.to_representation(instance), status=HTTP_200_OK)

    def destroy(self, request, *args):
        app_label = request.data.get('app_label')
        model_name = request.data.get('model')
        logger.info('Destroying content type instance %s.%s', app_label, model_name)
        content_type_serializer = self.get_serializer_class()
        content_type_data = content_type_serializer(data=request.data, context={'request': request})

        try:
            content_type_data.is_valid(raise_exception=True)
        except ValidationError as exc:
            logger.error('Validation error in destroy: %s', exc.detail)
            return Response(exc.detail, status=HTTP_200_OK)

        content_type = ContentType.objects.get(app_label=app_label, model=model_name)
        model = content_type.model_class()
        if model is None:
            logger.error('Model class is None for content type %s.%s', app_label, model_name)
            return Response(
                {'error': f"Модель {app_label}.{model_name} недоступна "
                          f"(возможна устаревшая запись django_content_type)"},
                status=HTTP_200_OK,
            )

        try:
            instance = model.objects.get(id=request.data['id'])
        except model.DoesNotExist:
            logger.error('Instance with ID %s not found for model %s', request.data['id'], model.__name__)
            return Response({'error': f'Указанного объекта класса {model.__name__} не существует'})

        contract = self.get_contract_registry().get(app_label, model_name)
        if contract is not None:
            contract.lifecycle.run('before_delete', request=request, view=self, instance=instance)

        if self.delete_signal is not None:
            self.delete_signal.send(sender=instance.__class__, instance=instance, request=request)

        instance.delete()

        if contract is not None:
            contract.lifecycle.run('after_delete', request=request, view=self, instance=instance)

        return Response({}, status=HTTP_204_NO_CONTENT)
