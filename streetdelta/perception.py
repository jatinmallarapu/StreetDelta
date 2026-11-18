"""Run Grounding DINO on local files and parse supported speed-limit OCR values."""

import argparse
import json
import re
from pathlib import Path

PROMPTS = ["speed limit sign", "stop sign", "traffic light", "pedestrian crosswalk"]
KINDS = dict(zip(PROMPTS, ("speed_limit", "stop_sign", "traffic_signal", "crosswalk"), strict=True))
LIMIT = re.compile(r"\b(?:SPEED\s*LIMIT\s*)?(15|20|25|30|35|40|45|50|55)\b", re.IGNORECASE)


def speed_limit(text):
    matches = LIMIT.findall(text.strip())
    if len(matches) != 1 or re.search(r"\d{3,}", text):
        return None
    return int(matches[0])


def detect(image, processor, model, threshold):
    import torch

    inputs = processor(images=image, text=[PROMPTS], return_tensors="pt").to(model.device)
    with torch.inference_mode():
        output = model(**inputs)
    results = processor.post_process_grounded_object_detection(
        output,
        inputs.input_ids,
        threshold=threshold,
        text_threshold=0.25,
        target_sizes=[(image.height, image.width)],
    )[0]
    for label, box, score in zip(
        results["text_labels"], results["boxes"].tolist(), results["scores"].tolist(), strict=True
    ):
        kind = KINDS.get(label.casefold().strip())
        if kind is not None:
            yield {
                "kind": kind,
                "bbox": box,
                "score": score,
                "ocr_value": None,
                "ocr_confidence": None,
                "mask_rle": None,
                "est_depth_m": None,
            }


def main():
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", type=Path, nargs="+")
    parser.add_argument("--model", default="IDEA-Research/grounding-dino-tiny")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("--revision needs an immutable model commit")
    processor = AutoProcessor.from_pretrained(args.model, revision=args.revision)
    model = (
        AutoModelForZeroShotObjectDetection.from_pretrained(args.model, revision=args.revision)
        .to(args.device)
        .eval()
    )
    for path in args.images:
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        for row in detect(image, processor, model, args.threshold):
            print(
                json.dumps(
                    {"image_id": path.stem, "width": image.width, "height": image.height, **row}
                )
            )


if __name__ == "__main__":
    main()
