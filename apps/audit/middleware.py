"""Attaches request metadata used by the audit services."""

from django.core.exceptions import PermissionDenied


class AuditRequestMiddleware:
    """Records the caller's IP and agent, and logs refused access attempts."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audit_ip = self._client_ip(request)
        request.audit_user_agent = request.META.get("HTTP_USER_AGENT", "")
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied):
            from .services import log_activity

            log_activity(
                request=request,
                action="access_denied",
                metadata={"reason": str(exception)[:255]},
            )
        return None

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
