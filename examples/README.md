# Example waveforms

Two synthetic files, so the repository is self-contained. Regenerate them byte for byte
with `python3 make_examples.py`.

| File | Columns | What it is |
|---|---|---|
| `displacement_example.csv` | `t_s, pos_mm` | 20 s of table displacement at 50 Hz, ±8.8 mm. Passes all five pre-flight checks |
| `acceleration_example.csv` | `t_s, a_g` | 10 s of acceleration in g at 500 Hz, mostly below 5 Hz. Double integrated by the application into ±7.7 mm |

Load either one from the application's **CSV waveform** tab: pick the file, say which
column holds the value and what unit it is in, then press *Prepare*.

The acceleration file is the more interesting one, because it exercises the double
integration: an acceleration record integrated twice will drift into a ramp unless the
integration is done in the frequency domain with the low end suppressed. `test_waveform.py`
checks exactly that — a record made four times longer must not drift four times as far.
