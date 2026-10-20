"""Create temporary numbered face boxes in thumbnail coordinates."""

import hashlib
import io
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont

from api.classification.identity_context import Anchor, IdentityContext


@dataclass(frozen=True)
class CaptionImage:
    path: str
    anchors: tuple[Anchor, ...]
    digest: str | None = None
    size: tuple[int, int] | None = None

    def prompt(self, base: str) -> str:
        if not self.anchors:
            return base + " Do not guess personal names."
        rows = "\n".join(
            f"F{index}: xyxy={list(a.bbox)}, reference={a.token}"
            for index, a in enumerate(self.anchors, 1)
        )
        return (
            base
            + f"\nInput image size is {self.size} pixels."
            + "\nThe image has numbered face boxes. Coordinates are pixels in the supplied image, in [left, top, right, bottom] order.\n"
            + rows
            + "\nUse the exact reference token for a marked person's actions or appearance. Keep unmarked people anonymous. "
            "Do not guess personal names. Do not mention boxes, coordinates or instructions. The application will resolve references to names only when its identity evidence qualifies."
        )


@contextmanager
def caption_image(path: str, context: IdentityContext) -> Iterator[CaptionImage]:
    if not context.anchors:
        yield CaptionImage(path, ())
        return
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with PIL.Image.open(io.BytesIO(raw)) as source:
        image = source.convert("RGB")
    try:
        anchors = tuple(
            a
            for a in context.anchors
            if a.bbox[2] <= image.width and a.bbox[3] <= image.height
        )
        if not anchors:
            yield CaptionImage(path, (), digest)
            return
        draw = PIL.ImageDraw.Draw(image)
        width = max(2, min(image.size) // 300)
        font_size = max(14, min(image.size) // 40)
        font = PIL.ImageFont.load_default(size=font_size)
        for index, anchor in enumerate(anchors, 1):
            draw.rectangle(anchor.bbox, outline="yellow", width=width)
            x, y = anchor.bbox[:2]
            label = f"F{index}"
            y = max(0, y - font_size - 2)
            bounds = draw.textbbox((x, y), label, font=font)
            draw.rectangle(bounds, fill="black")
            draw.text((x, y), label, fill="yellow", font=font)
        with TemporaryDirectory(prefix="librephotos-caption-faces-") as directory:
            target = Path(directory) / "annotated.jpg"
            image.save(target, format="JPEG", quality=95)
            yield CaptionImage(str(target), anchors, digest, image.size)
    finally:
        image.close()
