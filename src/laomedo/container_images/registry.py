"""Read trusted registrations from packaged assets or a source checkout."""

import json
from pathlib import Path

from laomedo.container_images.errors import ImageBuildError
from laomedo.container_images.models import ImageRecipe, ImageRegistration


class ImageRegistry:
    """Resolve a fixed image name to its declared, bounded build context."""

    def __init__(self, root: Path):
        self.root = root
        try:
            self.images = {
                key: ImageRegistration.model_validate(value)
                for key, value in json.loads(
                    (root / "images.json").read_text(encoding="utf-8")
                ).items()
            }
            names = [value.image for value in self.images.values()]
            if len(set(names)) != len(names):
                raise ValueError("duplicate_image_tag")
        except (OSError, ValueError, TypeError, AttributeError):
            raise ImageBuildError("image_registry_invalid") from None

    @classmethod
    def load(cls):
        packaged = Path(__file__).parent / "resources"
        source = Path(__file__).resolve().parents[3] / "docker"
        return cls(packaged if (packaged / "images.json").is_file() else source)

    def find(self, reference: str, *, max_bytes: int):
        for registration in self.images.values():
            if registration.image == reference:
                return ImageRecipe.from_registration(
                    registration, self.root, max_bytes=max_bytes
                )
        return None
