"""Exact reservation identity; it does not grant Docker or mediation authority."""

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr


class ContainerIdentity(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    name: str
    run_id: str
    token: SecretStr = Field(repr=False)

    def registration(self, *, runner_pid, created_at, mediation):
        """Explicit private IPC record, never an HTTP/Activity/log projection."""
        return {
            "name": self.name,
            "run_id": self.run_id,
            "token": self.token.get_secret_value(),
            "runner_pid": runner_pid,
            "created_at": created_at,
            "mediation": mediation,
        }
