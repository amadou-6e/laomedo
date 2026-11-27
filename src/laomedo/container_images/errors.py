"""Safe registered-image acquisition failures."""


class ImageBuildError(RuntimeError):
    """Image acquisition failed; no image is admitted for execution.

    A failed build may leave Docker's normal build cache or an unverified staging
    tag. This error never asserts daemon-side build cancellation or cleanup.
    ``phase`` is an internal category, never daemon output or credential data.
    """

    code = "container_image_build_failed"

    def __init__(self, phase: str):
        self.phase = phase
        super().__init__(self.code)
