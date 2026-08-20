# Safety

- **Mechanical hard stops** 2 mm outside the software limit. A software limit must not be
  the only thing standing between a firmware bug and 10 kg of payload hitting the end of
  the rail.
- **The payload is bolted to the table.** Clamping or taping is not enough at 1 m/s².
- **Driver current at ~70 % of the motor's rating.** More than that means heat, missed
  steps and noise, with no useful gain in margin.
- **Do not power the Nano from 48 V.** VIN limit is 20 V; it runs from USB.
- **Keep the two grounds separate.** The driver's optoisolated inputs are the barrier
  between motor switching noise and the measurement chain.
- **Emergency stop:** `Esc` or `Space` in the application; `!` on the wire. It flushes the
  stream buffer as well as stopping motion.
- The rig has no enclosure. Keep hands off the belt and carriage while it is enabled — the
  carriage moves at up to 250 mm/s with 10 kg on it.
