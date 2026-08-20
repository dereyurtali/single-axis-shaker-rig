# Serial protocol

Between the host application (`software/link.py`) and the board
(`firmware/shaker/shaker.ino`). Read this alongside the header comment in the firmware.

**250 000 baud**, not 115 200. At 16 MHz it divides without error; 115 200 does not.

## Framing

The parser is always in exactly one of two states: reading a text line, or reading exactly
2N binary bytes. There is no way for the two to be confused, which is why the stream needs
no escaping or checksums.

## Commands

| | |
|---|---|
| `?` | request a status line |
| `H` | treat the current position as zero |
| `L <min> <max>` | set the software limit, in steps |
| `J <rate>` | jog, signed steps/s; `0` stops |
| `G <pos> <rate>` | go to an absolute position |
| `N <freq_mHz> <amp_steps>` | sine; frequency in millihertz |
| `R <n>` | prepare to stream, `n` samples coming (`0` = open-ended) |
| `D <n>` | followed by exactly 2n bytes: int16 little-endian **absolute** positions |
| `X` | stop, in any mode, at any time |
| `!` | emergency stop — also flushes the stream buffer |

## Responses

| | |
|---|---|
| `S <pos> <mode> <free> <under> <clip> <target>` | status, at 20 Hz |
| `K <message>` | command accepted |
| `E <message>` | error |

Modes: `0` idle · `1` jog · `2` goto · `3` sine · `4` stream.

## Design decisions worth knowing

**Absolute positions, never deltas.** A dropped sample in a delta stream becomes a
permanent offset that nothing downstream can detect — the table would sit in the wrong
place for the rest of the experiment, silently. With absolute positions the following
sample corrects it. int16 gives ±32 767 steps = ±409 mm; the stroke is ±150 mm.

**Position is always a count of pulses actually emitted.** No mode estimates position; each
mode states a target and the difference is stepped out.

**Flow control runs on credit, pessimistically.** The board's ring buffer holds 256 samples
(256 ms, 512 bytes of the Nano's 2 KB); the host sends 1000 samples/s. Overrunning loses
samples, underrunning stops the table, and both are silent. So credit is computed as

```
available = free_reported_in_last_status − sent_since_that_status
```

which deliberately understates the space available — by the time a status line arrives the
buffer has continued draining. Sending too little costs nothing (it goes out on the next
round). Sending too much costs silent data loss.

**`under` and `clip` must both stay zero.** `under` counts buffer starvation — the table
stopped mid-waveform. `clip` counts targets that exceeded the software limit or the step
rate ceiling, meaning the commanded motion and the applied motion are no longer the same
thing. The application marks any run with a non-zero counter as SUSPECT; such a run must
not go into an analysis.

**Step rate ceiling is 20 steps/tick** = 20 000 steps/s = 250 mm/s. Exceeding it does *not*
silently clip: `clip` increments and the run is flagged.

**Sine amplitude ramps over ~0.4 s (400 ticks), never steps.** Position is
`centre + amplitude · sin(phase)`. Change amplitude instantly and the position jumps by
`sin(phase)` — raising amplitude by 1 mm at the crest means moving the table 1 mm in a
single tick, which is 80 steps/ms, four times the ceiling. The ramp also makes starting and
stopping shock-free.

**Sine phase accumulator is 32-bit**, top 8 bits indexing the table. 16 bits is not enough:
at 1 Hz the increment works out to 65.5, and rounding to 65 shifts the frequency by 0.8 % —
you cannot hunt for a resonance peak with that error.
