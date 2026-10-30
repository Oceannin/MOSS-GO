"""Export readable example ComfyUI API graphs using the studio's own builder."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
from moss_go.settings import validate_request
from moss_go.workflows import MODEL_ROLES, build_workflow


def main():
    destination = ROOT / "workflows"
    destination.mkdir(exist_ok=True)
    cases = json.loads((ROOT / "moss_go/assets/benchmark_action_v2.json").read_text("utf-8"))
    character = cases["characters"][0]["description"]
    scene = cases["scenes"][0]["description"]
    examples = [
        ("moss-create-api", "moss", "create", character),
        ("flux-create-api", "flux-klein", "create", character),
        ("flux-reference-api", "flux-klein", "reference", scene),
        ("flux-masked-refine-api", "flux-klein", "refine", "Change the raincoat to deep blue. Keep the character's identity, pose and all unmasked details. Clean cel-shaded anime illustration."),
    ]
    for name, engine, mode, prompt in examples:
        request = {"request_id": "0" * 32, "engine": engine, "mode": mode, "profile": "balanced", "prompt": prompt, "seed": 42, "variants": 1}
        if mode != "create":
            request["input_id"] = "1" * 32
        settings = validate_request(request)
        if mode == "refine":
            settings.update(source_width=768, source_height=1024)
        models = {role: aliases[0] for role, (_, aliases) in MODEL_ROLES[engine].items()}
        graph = build_workflow(settings, models, input_image="mira.png" if mode != "create" else None,
                               mask_image="mira-edit-mask.png" if mode == "refine" else None, prefix="MOSS-GO/examples/" + name)
        (destination / (name + ".json")).write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mask = Image.new("L", (768, 1024), 0)
    ImageDraw.Draw(mask).rectangle((260, 250, 490, 650), fill=255)
    mask.save(destination / "mira-edit-mask.png")
    print("Exported four API graphs and one example mask. No model was run.")


if __name__ == "__main__":
    main()
