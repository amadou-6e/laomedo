"""Trusted case metadata for the Skill HTTP boundary regression matrix."""

from collections.abc import Callable
from http.server import ThreadingHTTPServer

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class SkillHTTPCase(BaseModel):
    """Keep one server route, its service method and client projection together."""

    model_config = ConfigDict(strict=True, frozen=True, arbitrary_types_allowed=True)

    server_type: type[ThreadingHTTPServer] = Field(
        description="Real loopback server class."
    )
    client: Callable = Field(
        description="Defining request function used by its callers."
    )
    route: str = Field(description="Fixed HTTP path exercised by the case.")
    method: str = Field(description="Service method dispatched by that route.")
    body: dict[str, JsonValue] = Field(
        description="Independent admitted request fields."
    )
    prefix: str = Field(description="Host URL and token-file environment prefix.")
    fallback: str = Field(
        description="Safe HTTP category for an unexpected domain failure."
    )
    client_error: str = Field(
        description="Expected caller-facing category for that failure."
    )
