from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)

message_id_context: ContextVar[str] = ContextVar(
    "message_id",
    default="-",
)

document_id_context: ContextVar[str] = ContextVar(
    "document_id",
    default="-",
)


def get_request_id() -> str:
    return request_id_context.get()


def get_message_id() -> str:
    return message_id_context.get()


def get_document_id() -> str:
    return document_id_context.get()