import logging
from collections.abc import Mapping

from rest_framework.permissions import BasePermission

from drf_contenttype_contracts.resources.base import mark_contract_policy_applied


logger = logging.getLogger(__name__)


class ContentTypeContractPermission(BasePermission):
    """Apply the registered ContentType contract policy for the requested model."""

    message = 'Content type contract permission denied.'

    def has_permission(self, request, view):
        app_label, model = self.get_requested_model(request)
        action = getattr(view, 'action', None)
        if not app_label or not model or not action:
            logger.warning(
                'ContentType contract permission denied: incomplete request '
                'app_label=%s model=%s action=%s',
                app_label,
                model,
                action,
            )
            return False

        contract_registry = self.get_contract_registry(view)
        contract = contract_registry.get(app_label, model) if contract_registry else None
        if contract is None:
            logger.warning(
                'ContentType contract permission denied: contract is not registered '
                'for %s.%s action=%s',
                app_label,
                model,
                action,
            )
            return False

        if action in (contract.missing_policy_actions or frozenset()):
            self.log_missing_policy_action(request, action, app_label, model)

        allowed = contract.check_permission(request, view)
        if allowed:
            mark_contract_policy_applied(request, app_label, model, action)
        return allowed

    @staticmethod
    def get_requested_model(request):
        data = getattr(request, 'data', None)
        if not isinstance(data, Mapping):
            data = getattr(request, 'query_params', None)
        if not isinstance(data, Mapping):
            return None, None
        return data.get('app_label'), data.get('model')

    @staticmethod
    def get_contract_registry(view):
        if hasattr(view, 'get_contract_registry'):
            return view.get_contract_registry()
        return getattr(view, 'contract_registry', None)

    @staticmethod
    def log_missing_policy_action(request, action, app_label, model):
        user = getattr(request, 'user', None)
        logger.warning(
            'ContentType contract policy is marked as missing or unaudited: '
            'content_type=%s.%s action=%s user_id=%s username=%s',
            app_label,
            model,
            action,
            getattr(user, 'id', None),
            getattr(user, 'username', None),
        )
