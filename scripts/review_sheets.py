"""Render every recorded comparison, including missing/failed cells, for visual review."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.root
    report_path = args.report or root / ".local/benchmark/report.json"
    report = json.loads(report_path.read_text("utf-8"))
    cases = report.get("config") or json.loads((root / "moss_go/assets/benchmark_cases.json").read_text("utf-8"))
    out = report_path.parent / (report_path.stem + "-review")
    out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=18)
    for character in cases["characters"]:
        for engine in ("moss-charref", "flux-klein"):
            sheet = Image.new("RGB", (1440, 1380), "#211927")
            draw = ImageDraw.Draw(sheet)
            reference = report["references"][character["id"]]["output_id"]
            with Image.open(root / ".local/data/images" / f"{reference}.png") as source:
                sheet.paste(ImageOps.contain(source.convert("RGB"), (220, 285)), (10, 10))
            draw.text((250, 20), f"{character['name']} | {engine}\nReference at left; all declared cases follow.\nReview is not a quality score.\nMarkers: " + ", ".join(character["markers"]), font=font, fill="white")
            for scene_index, scene in enumerate(cases["scenes"]):
                for seed_index, seed in enumerate(cases["seeds"]):
                    index = scene_index * 2 + seed_index
                    x, y = index % 3 * 480, 320 + index // 3 * 520
                    key = f"compare/{engine}/{character['id']}/{scene['id']}/{seed}"
                    run = next((item for item in report["runs"] if item["key"] == key), None)
                    result = (run or {}).get("result", {})
                    output_id = result.get("output_id")
                    if output_id:
                        with Image.open(root / ".local/data/images" / f"{output_id}.png") as source:
                            image = ImageOps.contain(source.convert("RGB"), (460, 470))
                            sheet.paste(image, (x + (480 - image.width) // 2, y))
                    draw.text((x + 10, y + 476), f"{scene['id']} | seed {seed} | {result.get('status', 'missing')}", font=font, fill="white")
            path = out / f"{engine}-{character['id']}.jpg"
            sheet.save(path, quality=94)
            print(path)


if __name__ == "__main__":
    main()
