"""Original, bundled reference images. Preparing one never starts a model."""

import hashlib
import json
from pathlib import Path

from .errors import StudioError

HERE = Path(__file__).parent
EXAMPLES = {item["id"]: item for item in json.loads((HERE / "assets/illustrated_examples.json").read_text("utf-8"))["images"]}


def example(example_id):
    if example_id not in EXAMPLES:
        raise StudioError("This example is not available.", code="example_missing", status=404)
    return EXAMPLES[example_id]


def example_bytes(example_id):
    item = example(example_id)
    content = (HERE / "web/examples" / item["filename"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != item["sha256"]:
        raise StudioError("The bundled example failed its integrity check. Reinstall this build.", code="example_corrupt", status=500)
    return content


def public_examples(api_prefix):
    return [{"id": item["id"], "label": item["label"], "label_ru": item["label_ru"],
             "width": item["width"], "height": item["height"], "source": item["source"],
             "image_url": f"{api_prefix}/examples/{item['id']}/{item['sha256']}.png"}
            for item in EXAMPLES.values()]
