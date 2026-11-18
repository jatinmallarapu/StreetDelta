# Evaluating a Chicago street-imagery system

A feature that looks well localized in a dashboard can be consistently wrong if nearby photos share the same heading error. The first StreetDelta benchmark starts with known geometry so the error can be measured exactly. It separates geometric recovery from detector quality.

For a Chicago study, freeze the imagery dates, map extract and test zone. Label detection boxes on 300 images with groups held out by sequence, and independently verify positions for at least 100 distinct features. Preserve disagreements and ambiguous objects in the annotation log. Distinguish painted crossing geometry, crossing nodes and traffic-signal locations.

Train the ImageNet ViT, frozen DINOv3 linear probe, and DINOv3 LoRA head on identical crop splits. Report macro F1 per sign class and mAP at IoU 0.50 for the candidate detector. Compare median and p90 distance, unmatched rate, and one-to-one precision at 25 and 50 with the Mapillary feature snapshot. Report results separately for night, occlusion, dense duplicates and urban canyons.

A VLM verifier should see the same bounded evidence a human can see. Store Yes, No or Unclear, the prompt/model revisions, and disagreement rates on the frozen labelled set. Use manual decisions to prioritize follow-up rather than automatically editing OSM.
