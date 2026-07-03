from typing import Final

class AgentConstants:
    KIS: Final[str] = "KIS"

    # HTTP Methods
    GET: Final[str] = "GET"
    POST: Final[str] = "POST"
    PUT: Final[str] = "PUT"
    DELETE: Final[str] = "DELETE"
    PATCH: Final[str] = "PATCH"
    DELPOST: Final[str] = "DELPOST"
    PUTPOST: Final[str] = "PUTPOST"

    # Authorization Scheme
    BASIC: Final[str] = "BASIC"
    BEARER: Final[str] = "BEARER"
    
    # Content-Types
    JSON: Final[str] = "JSON"
    OCTET: Final[str] = "OCTET"
    MULTIPART: Final[str] = "MULTIPART"

    # Object Bind Types
    SINGLE: Final[str] = "SINGLE"
    OBJECT: Final[str] = "OBJECT"
    ARRAY: Final[str] = "ARRAY"
    ARRAY_OBJ: Final[str] = "ARRAY_OBJ"

    # DB Actions
    SELECT: Final[str] = "SELECT"
    INSERT: Final[str] = "INSERT"
    UPDATE: Final[str] = "UPDATE"
    DELETE: Final[str] = "DELETE"