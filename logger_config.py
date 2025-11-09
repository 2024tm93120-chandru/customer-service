import logging
import sys
import structlog
from flask import request
import os
from enum import IntEnum


from opentelemetry.sdk._logs import LoggerProvider, LogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import TraceFlags, INVALID_SPAN_CONTEXT


class SeverityNumber(IntEnum):
    UNSPECIFIED = 0
    TRACE = 1
    TRACE2 = 2
    TRACE3 = 3
    TRACE4 = 4
    DEBUG = 5
    DEBUG2 = 6
    DEBUG3 = 7
    DEBUG4 = 8
    INFO = 9
    INFO2 = 10
    INFO3 = 11
    INFO4 = 12
    WARN = 13
    WARN2 = 14
    WARN3 = 15
    WARN4 = 16
    ERROR = 17
    ERROR2 = 18
    ERROR3 = 19
    ERROR4 = 20
    FATAL = 21
    FATAL2 = 22
    FATAL3 = 23
    FATAL4 = 24


PII_FIELDS = {'email', 'phone', 'line1'}
SEVERITY_NUMBER_MAP = {
    logging.CRITICAL: SeverityNumber.FATAL,
    logging.ERROR: SeverityNumber.ERROR,
    logging.WARNING: SeverityNumber.WARN,
    logging.INFO: SeverityNumber.INFO,
    logging.DEBUG: SeverityNumber.DEBUG,
    logging.NOTSET: SeverityNumber.UNSPECIFIED,
}


def mask_pii_processor(logger, log_method_name, event_dict):
    """Redact PII fields in request/response bodies."""
    for field_name in ['request_body', 'response_body']:
        body = event_dict.get(field_name)
        if isinstance(body, dict):
            for key in PII_FIELDS:
                if key in body:
                    body[key] = "REDACTED"
    return event_dict


class OTLPLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        return record.getMessage()

    def formatException(self, exc_info):
        return str(exc_info[1])


class OTLPHandler(logging.Handler):
    def __init__(self, logger_provider: LoggerProvider, level=logging.NOTSET):
        super().__init__(level)
        self._logger_provider = logger_provider
        self._otel_logger = logger_provider.get_logger(__name__)

    def emit(self, record):
        try:
            # get OpenTelemetry span context if available
            ctx = INVALID_SPAN_CONTEXT
            trace_id = ctx.trace_id
            span_id = ctx.span_id
            trace_flags = ctx.trace_flags

            severity_number = SEVERITY_NUMBER_MAP.get(record.levelno, SeverityNumber.UNSPECIFIED)
            log_record = LogRecord(
                timestamp=int(record.created * 1e9),
                observed_timestamp=int(record.created * 1e9),
                trace_id=trace_id,
                span_id=span_id,
                trace_flags=trace_flags,
                severity_text=record.levelname,
                severity_number=severity_number,
                body=self.format(record),
                resource=self._logger_provider.resource,
                attributes={"logger.name": record.name},
            )

            self._otel_logger.emit(log_record)
        except Exception:
            self.handleError(record)



def setup_logging(log_level="INFO"):
    """Configure structlog + OpenTelemetry logging."""
    loki_otlp_url = os.environ.get("LOKI_OTLP_URL", "http://loki:4318/v1/logs")

    resource = Resource(attributes={"service.name": "customer-service"})
    logger_provider = LoggerProvider(resource=resource)

    otlp_exporter = OTLPLogExporter(endpoint=loki_otlp_url)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))

    # Use custom OTLP handler
    otlp_handler = OTLPHandler(logger_provider=logger_provider)
    otlp_handler.setFormatter(OTLPLogFormatter())

    # Structlog setup
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            lambda _, __, ed: {
                'correlation_id': request.headers.get('X-Correlation-Id')
            } if request else {},
            mask_pii_processor,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    root_logger = logging.getLogger()
    root_log_level = logging.getLevelName(log_level.upper())

    root_logger.addHandler(console_handler)
    root_logger.addHandler(otlp_handler)
    root_logger.setLevel(root_log_level)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)

    print(f"✅ Structured logging configured (Console + OTLP to {loki_otlp_url})")
