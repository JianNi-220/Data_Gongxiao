"""Validate a completed OCR batch: python3 check_ocr.py manifest.json output_dir."""
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
assert len({source["id"] for source in manifest}) == len(manifest), "duplicate source IDs"
total = 0
for source in manifest:
    result = json.loads((Path(sys.argv[2]) / (source["id"] + ".json")).read_text())
    assert result["id"] == source["id"]
    assert result["status"] == "ok", (source["id"], result.get("error"))
    assert result["image_width"] > 0 and result["image_height"] > 0
    for observation in result["observations"]:
        assert isinstance(observation["text"], str)
        assert 0 <= observation["confidence"] <= 1
        assert observation["bbox"]["width"] >= 0 and observation["bbox"]["height"] >= 0
        total += 1
print(f"Validated {len(manifest)} images and {total} observations")
