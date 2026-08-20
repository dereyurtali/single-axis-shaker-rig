"""CSV → adım dönüşümünün sınanması, projenin gerçek dosyalarıyla.

Buradaki asıl mesele ivme→yer değiştirme dönüşümü. Zaman ekseninde iki kez
toplasak sonuç makul görünür ama yavaşça sürüklenir; tabla dakikalar içinde
sınıra yürür ve bunu ancak deney sırasında fark ederiz. O yüzden sürüklenme
açıkça ölçülüyor: bilerek kaydırılmış bir ivme kaydından üretilen yer
değiştirmenin merkezde kalması gerekiyor.

    ./.venv/bin/python test_waveform.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

import waveform as wf

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
BELT = os.path.join(REPO, "data", "results", "shaker_belt_25x.csv")
HOT = os.path.join(REPO, "data", "results", "hot_windows", "hot_06_1854ug.csv")
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_tmp.csv")

fails = 0


def ok(cond, msg, got=""):
    global fails
    if not cond:
        fails += 1
    print("%s%s%s%s" % ("  ok  " if cond else "FAIL  ", msg,
                        "   -> " if got != "" else "", got))


# --- 1. gerçek yer değiştirme dosyası (t_s, pos_mm) ---
if os.path.exists(BELT):
    w = wf.build(BELT, col_value=1, col_time=0, units="mm", limit_mm=150)
    ok(len(w.steps) > 0, "shaker_belt_25x.csv okundu",
       "%d ornek, %.1f s, kaynak %.0f Hz" % (len(w.steps), w.duration_s, w.fs_in))
    ok(abs(w.fs_in - 50) < 2, "ornekleme hizi zaman kolonundan bulundu",
       "%.1f Hz" % w.fs_in)
    ok(len(w.steps) == int(round(w.n_in / w.fs_in * 1000)),
       "1 kHz'e yeniden orneklendi", str(len(w.steps)))
    ok(abs(w.mm[0]) < 1e-6 and abs(w.mm[-1]) < 1e-6,
       "uclar sifirda — tabla ilk tick'te sicramiyor",
       "%.2e / %.2e" % (w.mm[0], w.mm[-1]))
    for c in w.checks:
        print("        %s %-7s %s" % ("+" if c.ok else "!", c.name, c.detail))
else:
    ok(False, "shaker_belt_25x.csv bulunamadi")

# --- 2. gerçek ivme dosyası (t_s, x_g …) ---
if os.path.exists(HOT):
    w2 = wf.build(HOT, col_value=1, col_time=0, units="g", gain=1.0, limit_mm=150)
    ok(len(w2.steps) > 0, "hot_06 ivme dosyasi cift integre edildi",
       "%.1f s, tepe %.4f mm" % (w2.duration_s, w2.peak_mm))
    off = abs(float(np.mean(w2.mm)))
    ok(off < 0.05 * w2.peak_mm, "ortalama merkezde (tepenin %5'inden az)",
       "%.2e mm / tepe %.4f mm" % (off, w2.peak_mm))
else:
    ok(False, "hot window bulunamadi")

# --- 3. SÜRÜKLENME: kaydirilmis ivmeden yer degistirme ---
fs = 1000.0
t = np.arange(int(20 * fs)) / fs
acc = 0.5 * np.sin(2 * np.pi * 10 * t) + 0.02          # 0.02 m/s2 sabit kayma
np.savetxt(TMP, np.c_[t, acc], delimiter=",", header="t,a", comments="")

w3 = wf.build(TMP, col_value=1, col_time=0, units="m/s2", limit_mm=150, taper_s=0.5)
# Beklenen genlik: a/omega^2 = 0.5/(2*pi*10)^2 m = 0.127 mm
want_mm = 0.5 / (2 * np.pi * 10) ** 2 * 1000
ok(abs(w3.peak_mm - want_mm) / want_mm < 0.10,
   "cift integral genligi dogru (a/omega^2)",
   "%.4f mm / beklenen %.4f" % (w3.peak_mm, want_mm))

def _drift(seconds):
    tt = np.arange(int(seconds * fs)) / fs
    aa = 0.5 * np.sin(2 * np.pi * 10 * tt) + 0.02
    np.savetxt(TMP, np.c_[tt, aa], delimiter=",", header="t,a", comments="")
    ww = wf.build(TMP, col_value=1, col_time=0, units="m/s2", limit_mm=150, taper_s=0.5)
    n = int(2 * fs)
    return abs(float(np.mean(ww.mm[-n:])) - float(np.mean(ww.mm[:n])))

# Suruklenme demek, kaymanin kayit uzadikca BUYUMESI demek. Sabit kalan kucuk
# bir artik FFT'nin kenar etkisidir, birikmez; asil sinanmasi gereken bu.
d20, d80 = _drift(20), _drift(80)
ok(d20 < 0.05 * want_mm, "sabit ivme kaymasi yutuldu",
   "%.2e mm (tepe %.4f mm)" % (d20, want_mm))
ok(d80 < 2.0 * d20 + 1e-12,
   "SURUKLENME YOK — kayit 4 katina cikinca kayma buyumuyor",
   "20 s: %.2e   80 s: %.2e" % (d20, d80))

# --- 4. güvenlik kontrolleri gerçekten reddediyor mu ---
big = 200 * np.sin(2 * np.pi * 1 * t)                   # ±200 mm, sinir ±150
np.savetxt(TMP, np.c_[t, big], delimiter=",", header="t,mm", comments="")
w4 = wf.build(TMP, col_value=1, col_time=0, units="mm", limit_mm=150)
ok(not w4.ok, "asiri strok REDDEDILDI")
ok(any(c.name == "Strok" and not c.ok for c in w4.checks), "reddeden kontrol: Strok")

fast = 3.0 * np.sin(2 * np.pi * 40 * t)                 # 40 Hz x 3 mm cok hizli
np.savetxt(TMP, np.c_[t, fast], delimiter=",", header="t,mm", comments="")
w5 = wf.build(TMP, col_value=1, col_time=0, units="mm", limit_mm=150)
ok(not w5.ok, "asiri hiz REDDEDILDI")
ok(any(c.name == "Hiz" and not c.ok for c in w5.checks)
   or any(c.name == "Hız" and not c.ok for c in w5.checks), "reddeden kontrol: Hiz")

# --- 5. zaman kolonu olmadan, fs verilerek ---
np.savetxt(TMP, 1.5 * np.sin(2 * np.pi * 5 * t), delimiter=",")
w6 = wf.build(TMP, col_value=0, col_time=None, fs_in=1000, units="mm", limit_mm=150)
ok(abs(w6.peak_mm - 1.5) < 0.05, "zaman kolonsuz, fs elle verildi",
   "%.3f mm" % w6.peak_mm)

# --- 6. adim donusumu ---
ok(wf.STEPS_PER_MM == 80.0, "80 adim/mm (3200 adim/tur, 40 mm/tur)")
ok(int(np.rint(10.0 * wf.STEPS_PER_MM)) == 800, "10 mm = 800 adim")

os.remove(TMP)
print("\n%d KONTROL BASARISIZ" % fails if fails else "\nhepsi gecti")
sys.exit(1 if fails else 0)
