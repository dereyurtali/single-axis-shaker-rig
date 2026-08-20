"""Generate the two example waveform files, deterministically.

These are synthetic. They exist so that the repository is self-contained: the test
suite and the application both have something real-shaped to chew on without shipping
anyone else's recordings. Re-running this script reproduces the files byte for byte.

    python3 make_examples.py
"""

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(20260820)


def taper(n, edge=0.05):
    """Half-cosine ramp on both ends, so the waveform starts and ends at zero.

    The rig rejects any waveform whose ends are not zero — a non-zero first sample
    means the table is asked to jump there within one tick.
    """
    w = np.ones(n)
    k = max(1, int(n * edge))
    ramp = 0.5 * (1 - np.cos(np.pi * np.arange(k) / k))
    w[:k] = ramp
    w[-k:] = ramp[::-1]
    return w


def displacement_example():
    """20 s of table displacement at 50 Hz, in millimetres. Columns: t_s, pos_mm."""
    fs, dur = 50.0, 20.0
    t = np.arange(int(fs * dur)) / fs
    x = (6.0 * np.sin(2 * np.pi * 0.7 * t)
         + 2.5 * np.sin(2 * np.pi * 1.9 * t + 1.1)
         + 1.0 * np.sin(2 * np.pi * 4.3 * t + 0.4)
         + 0.05 * RNG.standard_normal(t.size))
    x *= taper(t.size)
    x -= np.linspace(x[0], x[-1], t.size)          # kill any residual end offset
    np.savetxt(os.path.join(HERE, "displacement_example.csv"),
               np.c_[t, x], delimiter=",", header="t_s,pos_mm",
               comments="", fmt="%.6f")
    return x


def acceleration_example():
    """10 s of acceleration at 500 Hz, in g. Columns: t_s, a_g.

    Roughly the shape of a low-frequency structural disturbance: most of the energy
    below 5 Hz, a little broadband on top. Double integrated by the application into a
    few millimetres of displacement.
    """
    fs, dur = 500.0, 10.0
    t = np.arange(int(fs * dur)) / fs
    a = (0.050 * np.sin(2 * np.pi * 1.5 * t)
         + 0.020 * np.sin(2 * np.pi * 4.0 * t + 0.8)
         + 0.004 * np.sin(2 * np.pi * 12.0 * t + 2.0)
         + 0.002 * RNG.standard_normal(t.size))
    a *= taper(t.size)
    np.savetxt(os.path.join(HERE, "acceleration_example.csv"),
               np.c_[t, a], delimiter=",", header="t_s,a_g",
               comments="", fmt="%.6f")
    return a


if __name__ == "__main__":
    x = displacement_example()
    a = acceleration_example()
    print("displacement_example.csv  peak %.2f mm" % np.abs(x).max())
    print("acceleration_example.csv  peak %.4f g" % np.abs(a).max())
