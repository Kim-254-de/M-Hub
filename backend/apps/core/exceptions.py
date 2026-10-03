import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def exception_handler(exc, context):
    """DRF exception handler that logs unexpected errors.

    Known API errors keep DRF's response format. Anything DRF does not handle
    is logged with the view name and re-raised so Django returns a 500 without
    leaking internals.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        view = context.get("view")
        logger.exception("Unhandled API error in %s", type(view).__name__ if view else "unknown view")
    return response
