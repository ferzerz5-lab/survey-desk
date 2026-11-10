---
name: field-book
description: Use the survey_* tools for any bearing, distance, traverse, area or coordinate-system work, and deliver the plan files in chat.
---

# Survey desk

Never do survey arithmetic (bearings, closure, area, datum shifts) in your head. Call the tools.

1. **Traverse or plot area** -> `survey_plan` (drawing + files) or `survey_traverse` (numbers only).
   - Bearings are whole-circle (`45-30-20`, `045°30'20"`) or quadrant (`N45-30-20E`). Distances are metres.
   - The last leg returns to the start station. If the user gives station names, pass them as `to`.
   - Pass `crs` when the user states the coordinate system (for Nigerian cadastral work usually `minna_west`, `minna_mid` or `minna_east`); it enables the georeferenced KML/GeoJSON.
2. **Coordinate conversion** -> `survey_convert`. Geographic points are longitude (x), latitude (y). Read out the `warnings` and the datum-shift accuracy; do not hide them.
3. **Bearing and distance between two points** -> `survey_inverse`.

After `survey_plan`, reply with: verdict, area (m2 and ha), misclosure and relative accuracy, any failed check, and any suspect leg. Then include every line of `attachments` verbatim, each on its own line, so the files are delivered. If the verdict is RE-OBSERVE, say which leg to re-measure first and do not present the area as final.

These results are computations, not a licensed survey plan.
