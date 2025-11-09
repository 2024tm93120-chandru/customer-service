import structlog
from flask import jsonify, request

log = structlog.get_logger()


class ApiError(Exception):
    """Custom exception class for API errors."""

    def __init__(self, message, status_code, code):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        """Handle custom ApiError exceptions."""
        correlation_id = structlog.contextvars.get_contextvars().get('correlation_id', 'not-available')
        response = {
            "error": {
                "code": error.code,
                "message": error.message,
                "correlationId": correlation_id
            }
        }
        log.error("api_error", code=error.code, status=error.status_code, error=error.message)
        return jsonify(response), error.status_code

    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 Not Found errors."""
        correlation_id = structlog.contextvars.get_contextvars().get('correlation_id', 'not-available')
        response = {
            "error": {
                "code": "NOT_FOUND",
                "message": "The requested resource was not found",
                "correlationId": correlation_id
            }
        }
        log.warn("not_found", path=request.path)
        return jsonify(response), 404

    @app.errorhandler(Exception)
    def handle_generic_error(error):
        """Handle all other unhandled exceptions."""
        correlation_id = structlog.contextvars.get_contextvars().get('correlation_id', 'not-available')
        response = {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "correlationId": correlation_id
            }
        }
        log.exception("unhandled_exception", error=str(error))
        return jsonify(response), 500