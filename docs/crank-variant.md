# Crank variant (alternative)

Kept for anyone who wants a *physically* bounded stroke more than they want resolution.
The trade-off is set out in [design rationale §1](design-rationale.md#1-belt-driven-stage-not-a-crank).

Remove the belt, pulley, idler and tensioner from the [bill of materials](bill-of-materials.md);
add:

| Part | Note |
|---|---|
| Crank disc, **adjustable radius** | Slot and clamp pin, 8–32 mm. This is how you set amplitude after a pilot sweep |
| Connecting rod, 160 mm | At least 5× the radius; longer means less distortion |
| 623ZZ bearings ×2 | Crank pin and wrist pin. Preload them — any play here is backlash |

In this mode the axis coordinate is the **crank angle**, not linear position: the generator
applies the arccos transform and enforces the ±0.7·r usable limit.

Sizing: at a 16 mm radius the 25× replay scale is fine; at 50× it clips by 14.8 % and the
radius has to go to 32 mm. Torque also rises — the force acts through the crank arm, so at
the same scale it is roughly 2.5× the belt figure, and a short-body motor no longer has
enough margin.
