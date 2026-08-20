# Bill of materials

What was actually ordered and built, not an idealised list. Suppliers are Turkish because
that is where it was built; the specification column is what matters if you source it
elsewhere.

Rough total: **~270 USD** excluding the printer, the host PC and metrology.

## Drive

| # | Part | Qty | Specification that matters |
|---|---|---|---|
| 1 | Stepper motor, NEMA 23 | 1 | **57HB84-154** · 84 mm body · 1.8° · 1.5 A/phase · 5.0 Ω · **10 mH/phase** · 1.6 N·m holding (datasheet, not the listing — see [design rationale §4](design-rationale.md#4-verifying-the-motor-against-its-datasheet)) · Ø8 mm shaft |
| 2 | Stepper driver | 1 | **DM542**, 4.5 A capable, STEP/DIR, optoisolated inputs. A TB6600 also works; **a TMC2209 does not** — it cannot supply this motor's current |
| 3 | Power supply | 1 | **Meanwell LRS-150-48**, 48 V / 3.3 A, enclosed. 48 V is required, not preference — [§6](design-rationale.md#6-why-48-v) |
| 4 | Microcontroller | 1 | **Arduino Nano**, ATmega328P, CH340, USB-C |
| 5 | Nano screw-terminal shield | 1 | Saves soldering; any equivalent breakout works |

## Motion

| # | Part | Qty | Specification that matters |
|---|---|---|---|
| 6 | GT2 belt, open-ended | 1.5 m | **10 mm wide, steel cord.** 6 mm stretches more than one microstep under this load — [§5](design-rationale.md#5-belt-width-is-a-design-variable-not-a-constant) |
| 7 | GT2 pulley, 20 teeth | 1 | Ø8 mm bore (match your motor shaft), **flanged**, two grub screws. 40 mm/rev → 12.5 µm/step. Buy a 16-tooth as well if you may need more amplitude |
| 8 | GT2 idler, 20 teeth | 1 | **Toothed and on a bearing.** The belt wraps it teeth-inwards; a flat idler lets it walk |
| 9 | Supported linear rail, Ø12 mm | 2 × 500 mm | Induction-hardened, with the aluminium support rail. Ø12 rather than Ø8 because of the 10.6 kg moving mass and the 500 mm span |
| 10 | Linear bearing, SBR12UU | 4 | Ball bearings. **Not plastic bushings** — the friction eats the motor's margin |
| 11 | Belt clamp | 2 | 3D printed, [thing:2354961](https://www.thingiverse.com/thing:2354961) |

## Structure

| # | Part | Qty | Specification that matters |
|---|---|---|---|
| 12 | 20×20 V-slot extrusion, slot 6 | 2 × 430 mm | Frame |
| 13 | 20×80 extrusion, slot 6 | 2 × 250 mm | Cross members / rail supports |
| 14 | Aluminium plate | 1 | **300 × 320 × 6 mm**, laser cut. 1.56 kg. Sized to the printer footprint — see [§2](design-rationale.md#2-the-printer-choice-dominates-everything) |
| 15 | Wide corner bracket, 20×25, slot 6 | 4 | Wide type, not the hidden internal connector — it carries the moment from the printer's mass |
| 16 | T-slot nuts, slot 6, M5 | 30 | |
| 17 | M5 socket-head bolt set, DIN 912 | 1 | 411-piece assortment; you will use more sizes than you plan for |

## 3D-printed parts

PETG or ABS, **60 % infill, 4 perimeters**, 0.2 mm layers. **Not PLA** for structural
parts — it creeps and fatigues under continuous vibration.

| Part | Note |
|---|---|
| Motor mount | Bolts to the extrusion; belt line must be parallel to the rails |
| Idler bracket | Same |
| Carriage body | Four SBR12UU seats plus the belt clamp interface |
| Belt clamps ×2 | Toothed grip, not friction |
| Accelerometer mounts ×2 | Rigid; a loose mount invents resonances that are not there |
| Hard-stop blocks ×2 | 2 mm outside the software limit |

## Instrumentation (optional — needed to *characterise* the rig, not to run it)

| # | Part | Qty | Note |
|---|---|---|---|
| 18 | ADXL345 accelerometer breakout | 2–3 | One under the table (proof of what the shaker actually applied), one on whatever you are testing. A third, mounted alongside the first, gives you an honest upper bound on your own measurement uncertainty |
| 19 | Digital dial indicator, 1 µm, with data output | 1 | Stroke verification. In this band it is **better than an accelerometer** |
| 20 | Magnetic indicator base | 1 | |

## Suppliers used

GT2 belt and idler — rhino3dprinter · motor, pulley, Nano and shield — motorobit · driver —
robolinkmarket · rail and extrusion — mermakcnc, otomasyoncu · linear bearings —
sahinrulman · PSU — kartalotomasyon · T-nuts — ileri3d · aluminium plate — local laser
cutting shop.

## What we would change

- A printer with a **stationary bed**. The Ender-3's own Y axis pushes back against the
  shaker table during a print.
- Order the 16-tooth pulley at the same time as the 20-tooth. It is 6 USD and it is the
  only lever you have if you need more amplitude later.
