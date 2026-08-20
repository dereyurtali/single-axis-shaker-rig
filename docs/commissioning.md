# Commissioning

Seven acceptance tests. Run them in order; do not start a measurement campaign until all
seven pass. Test 5 is the one that makes a home-built rig defensible at all.

| # | Test | Pass criterion |
|---|---|---|
| 1 | **Free friction.** Motor detached, push the carriage by hand | No binding anywhere along the rail |
| 2 | **Stroke verification.** Command ±10 mm, measure with a dial indicator | Commanded vs. measured within 2 % |
| 3 | **Backlash.** Reverse direction and watch the indicator | Dead zone < 20 µm |
| 4 | **Repeatability.** Return to the same position ten times | Spread < 15 µm |
| 5 | **Target vs. achieved.** Play the waveform, record with the accelerometer | Spectra overlap |
| 6 | **Under load.** Repeat 2 and 5 with the payload bolted on | Same criteria |
| 7 | **Acceleration tracking.** Compare the measured table acceleration against the commanded trajectory's | Peak within 10 % — if it is low, a firmware limit is throttling you |

## Two traps

**Firmware acceleration limits fail silently.** At the 25× replay scale the trajectory
reaches 1078 mm/s². If the motion firmware's `max_accel` is below that, it will quietly
slow the moves down — no error, just a wrong playback of the recording. Test 5 and test 7
exist to catch exactly this.

**Do not lock the waveform to the payload's own rhythm.** A 125-second recording loops
about eight times during a 16-minute print. If every loop starts at the same point and the
print's layer time is ~20 seconds, the disturbance pattern locks to the layer rhythm and
prints a false banding pattern into the specimen. Offset the start point on every loop.

## Do not disassemble mid-campaign

Once commissioned, the rig stays assembled and the bolts stay at the same torque.
Disassembly resets the calibration and invalidates every test above.
