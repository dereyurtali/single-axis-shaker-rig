# Assembly

![The stage from the side](../photos/rig-side.jpg)

Order matters: each step is only checkable while the next one is still off.

1. **Frame.** A rectangle from the 20×20 extrusion. Square the corners; fit the damping
   feet. The wide 20×25 corner brackets carry the moment from the printer's mass — the
   hidden internal connectors are not enough here.

2. **Rails.** Bolt the supported rails to the frame. **Parallelism is the critical
   tolerance:** slide the carriage along by hand over the whole length; it must not bind
   anywhere. A rig that binds at one end will show up later as a position error you will
   spend a day blaming on the firmware.

3. **Carriage.** Four SBR12UU bearings into the printed body, onto the rails. Unloaded, it
   must push with one finger.

4. **Motor and belt.** Motor at one end, idler at the other, belt line parallel to the
   rails. Clamp the belt to the carriage and tension it — **taut enough to give a solid
   note when plucked, and no more**; overtightening loads the rail bearings. Target preload
   is ≥ 20 N, about 1.5× the peak transmitted force. Practical check: finger pressure
   should deflect it no more than 1–2 mm.

5. **Table.** Bolt the aluminium plate to the carriage.

6. **Electronics.** See [wiring](wiring.md). Set the driver current to about 70 % of the
   motor's rated value before powering the motor for the first time.

7. **Hard stops.** Mechanical stops 2 mm outside the software limit, both ends.

8. **Payload.** Bolt the printer to the table — **bolted, not clamped or taped.** Orient
   it so that the shaking axis is perpendicular to the surface you will be measuring.

9. **Sensors.** One accelerometer under the table, one on the payload. Mount them rigidly;
   a loose mount invents resonances that are not there.

Then run every test in [commissioning](commissioning.md) before trusting a single
measurement.
