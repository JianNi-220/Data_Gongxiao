"""Split empty whole-image OCR into half pages, then merge normalized coordinates.

python3 ocr_fallback.py prepare manifest.json ocr_dir scratch_dir
ocr scratch_dir/crop_manifest.json scratch_dir/crop_ocr 4
python3 ocr_fallback.py merge manifest.json ocr_dir scratch_dir

Requires Pillow for `prepare`; `merge` uses only the standard library.
"""
import copy
import json
import sys
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def prepare(manifest_path, output, scratch):
    from PIL import Image

    crops = scratch / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    manifest, transforms, sources = [], [], []
    for source in read(manifest_path):
        record = read(output / (source["id"] + ".json"))
        if record.get("status") != "ok" or record.get("observations"):
            continue
        sources.append(source)
        with Image.open(source["path"]) as image:
            width, height = image.size
            for label, left, right in [("L", 0, width // 2), ("R", width // 2, width)]:
                crop_id = source["id"] + "_" + label
                path = (crops / (crop_id + ".png")).resolve()
                image.crop((left, 0, right, height)).save(path)
                manifest.append({"id": crop_id, "path": str(path)})
                transforms.append({"id": crop_id, "source_id": source["id"], "left": left,
                    "top": 0, "width": right - left, "height": height,
                    "source_width": width, "source_height": height})
    save(scratch / "zero_manifest.json", sources)
    save(scratch / "crop_manifest.json", manifest)
    save(scratch / "crop_transforms.json", transforms)
    print(f"Prepared {len(manifest)} crops for {len(sources)} empty whole-image results")


def original_box(box, transform):
    width, height = transform["source_width"], transform["source_height"]
    return {
        "x": (transform["left"] + box["x"] * transform["width"]) / width,
        "y": (height - transform["top"] - transform["height"] + box["y"] * transform["height"]) / height,
        "width": box["width"] * transform["width"] / width,
        "height": box["height"] * transform["height"] / height,
    }


def merge(output, scratch):
    groups = {}
    for transform in read(scratch / "crop_transforms.json"):
        groups.setdefault(transform["source_id"], []).append(transform)
    originals = scratch / "originals"
    originals.mkdir(exist_ok=True)
    count = 0
    for source_id, transforms in groups.items():
        destination = output / (source_id + ".json")
        record = read(destination)
        if not (originals / destination.name).exists():
            save(originals / destination.name, record)
        observations = []
        for transform in transforms:
            crop = read(scratch / "crop_ocr" / (transform["id"] + ".json"))
            assert crop["status"] == "ok", (source_id, crop.get("error"))
            for line in crop["observations"]:
                line = copy.deepcopy(line)
                line["bbox"] = original_box(line["bbox"], transform)
                line["crop_id"] = transform["id"]
                for character in line.get("characters", []):
                    character["bbox"] = original_box(character["bbox"], transform)
                observations.append(line)
        assert observations, f"Both half pages still have no text: {source_id}"
        record["observations"] = sorted(observations, key=lambda item: (-item["bbox"]["y"], item["bbox"]["x"]))
        record["preprocessing"] = {"method": "split_left_right_half_pages",
            "reason": "whole_image_returned_no_text", "coordinate_mapping": "original_image_normalized_bottom_left",
            "original_observations_count": 0, "crops": transforms}
        save(destination, record)
        count += len(observations)
    print(f"Merged {len(groups)} sources, recovered {count} observations")


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in ("prepare", "merge"):
        sys.exit("Usage: ocr_fallback.py prepare|merge manifest.json ocr_dir scratch_dir")
    operation, manifest_path, output_dir, scratch_dir = sys.argv[1:]
    output, scratch = Path(output_dir), Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    if operation == "prepare":
        prepare(manifest_path, output, scratch)
    else:
        merge(output, scratch)
