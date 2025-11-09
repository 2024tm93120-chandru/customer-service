import logging
import sys
import structlog
from flask import request

# --- PII Masking Processor ---

PII_FIELDS = {'email', 'phone', 'line1'}


def mask_pii_processor(logger, log_method_name, event_dict):
    """
    A structlog processor to find and mask PII fields.
    """
    # Check request JSON body for PII
    if 'request_body' in event_dict:
        body = event_dict['request_body']
        if isinstance(body, dict):
            for key, value in body.items():
                if key in PII_FIELDS:
                    body[key] = "REDACTED"

    # Check response JSON body for PII
    if 'response_body' in event_dict:
        body = event_dict['response_body']
        if isinstance(body, dict):
            for key, value in body.items():
                if key in PII_FIELDS:
                    body[key] = "REDACTED"

    return event_dict


def setup_logging(log_level="INFO"):
    """
    Configures structlog for structured, PII-masked logging.
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            # Add correlationId if present in headers
            lambda _, __, ed: {
                'correlation_id': request.headers.get('X-Correlation-Id')
            } if request else {},
            mask_pii_processor,  # Apply our custom PII masker
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    # Configure the formatter for the root logger
    formatter = structlog.stdlib.ProcessorFormatter(
        # Render as JSON for production-style logs
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy loggers like werkzeug (Flask's internal server)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    print("Structured logging configured.")