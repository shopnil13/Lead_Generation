REQUIRED_FIELDS = [
    "record_index",
]

DROP_FIELDS = [
    "document_name",
]

SYSTEM_PROMPT = (
    "You extract structured data from documents. "
    "Return ONLY valid JSON. "
    "Output must be an object with keys 'schema' and 'records'. "
    "'schema' is a list of field names in snake_case. "
    "'records' is a list of objects using those fields. "
    "If a field is missing, use an empty string."
)

REPAIR_SYSTEM_PROMPT = (
    "You repair JSON. "
    "Return ONLY valid JSON with no extra text."
)

USER_PROMPT_TEMPLATE = (
    "Infer the best schema for the document and extract all logical records.\n"
    "Always include the required fields: {required_fields}.\n"
    "Return JSON: {{ 'schema': [...], 'records': [{{...}}, ...] }}.\n\n"
    "Document name: {name}\n\n"
    "Document text:\n{text}\n"
)

REPAIR_USER_PROMPT_TEMPLATE = (
    "Fix the following so it is valid JSON only. "
    "Do not add commentary or code fences.\n\n"
    "{bad_json}\n"
)
