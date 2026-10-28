"""Exact reservation identity; it does not grant Docker or mediation authority."""

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr


class ContainerIdentity(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    name: str = Field(description="Exact container name reserved by the host.")
    run_id: str = Field(description="Application run owning this reservation.")
    token: SecretStr = Field(
        repr=False, description="Private host lease ownership label."
    )
    docker_endpoint: str | None = Field(
        default=None,
        description="Original pinned daemon endpoint; missing legacy data cannot establish cleanup.",
    )

    @classmethod
    def from_registration(cls, record):
        """Read a private lease registration without inferring a legacy endpoint."""
        return cls(
            name=record["name"],
            run_id=record["run_id"],
            token=record["token"],
            docker_endpoint=record.get("docker_endpoint"),
        )

    def client(self):
        """Open only the recorded endpoint, never the ambient default daemon."""
        if not self.docker_endpoint:
            raise ValueError("Original Docker endpoint unavailable")
        from py_docker import Client

        return Client(environment={"DOCKER_HOST": self.docker_endpoint})

    def reservation(self):
        """Project application ownership into the canonical runtime reservation."""
        from py_docker.containers.models import ContainerReservation
        from laomedo.host.leases import settings

        return ContainerReservation(
            name=self.name,
            labels={settings.LABEL_RUN: self.run_id, settings.LABEL_TOKEN: self.token},
        )

    def registration(self, *, runner_pid, created_at, mediation):
        """Explicit private IPC record, never an HTTP/Activity/log projection."""
        return {
            "name": self.name,
            "run_id": self.run_id,
            "token": self.token.get_secret_value(),
            **(
                {"docker_endpoint": self.docker_endpoint}
                if self.docker_endpoint is not None
                else {}
            ),
            "runner_pid": runner_pid,
            "created_at": created_at,
            "mediation": mediation,
        }
