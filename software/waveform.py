"""CSV → tablanın izleyeceği adım konumları.

Girdi iki biçimde gelebiliyor ve ikisi farklı iş gerektiriyor:

  yer değiştirme (mm)   doğrudan ölçeklenip adıma çevrilir
  ivme (m/s² veya g)    iki kez integre edilmesi gerekir

İvme integrali zaman ekseninde yapılmıyor. Ölçülen bir ivme kaydında her zaman
küçük bir sabit bileşen ve düşük frekanslı gürültü olur; zamanda iki kez toplarsan
bunlar parabolik bir kaymaya dönüşür ve tabla yavaşça sınıra doğru yürür. Frekans
ekseninde −ω²'ye bölmek, üstüne bant sınırlaması, bu kaymayı baştan yok eder.

Çıkışın iki ucu raised-cosine ile yumuşatılıyor. Yumuşatılmasa dalga formunun ilk
örneği sıfırdan farklıysa tabla ilk tick'te oraya sıçramaya çalışır; bu hem
mekanik bir şok hem de ölçüme karışan yapay bir darbe.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Optional

import numpy as np

TICK_HZ = 1000
STEPS_PER_MM = 80.0
MAX_STEPS_PER_TICK = 20
G = 9.80665


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Waveform:
    steps: np.ndarray            # int32, mutlak adım konumu, 1 kHz
    mm: np.ndarray               # aynı sinyal, mm
    fs_in: float                 # kaynak örnekleme hızı
    n_in: int
    checks: list[Check]

    @property
    def duration_s(self) -> float:
        return len(self.steps) / TICK_HZ

    @property
    def peak_mm(self) -> float:
        return float(np.max(np.abs(self.mm))) if len(self.mm) else 0.0

    @property
    def pp_mm(self) -> float:
        return float(np.ptp(self.mm)) if len(self.mm) else 0.0

    @property
    def peak_step_rate(self) -> int:
        if len(self.steps) < 2:
            return 0
        return int(np.max(np.abs(np.diff(self.steps))))

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def sniff_columns(path: str, max_rows: int = 40) -> tuple[list[str], int]:
    """Başlık satırlarını ve kolon adlarını çıkar. (adlar, atlanacak_satır)"""
    with open(path, "r", newline="") as fh:
        sample = fh.read(8192)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t ")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = [r for r in sample.splitlines() if r.strip()][:max_rows]
    if not rows:
        return [], 0
    first = [c.strip() for c in rows[0].split(delim)]
    numeric = all(_is_num(c) for c in first if c != "")
    if numeric:
        return ["kolon %d" % (i + 1) for i in range(len(first))], 0
    return first, 1


def _is_num(s: str) -> bool:
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False


def load_columns(path: str) -> np.ndarray:
    """Sayısal tabloyu oku; ayraç ve başlık kendiliğinden bulunur."""
    names, skip = sniff_columns(path)
    for delim in (",", ";", "\t", None):
        try:
            a = np.genfromtxt(path, delimiter=delim, skip_header=skip,
                              dtype=float, invalid_raise=False)
        except Exception:
            continue
        if a.ndim == 1:
            a = a.reshape(-1, 1)
        if a.size and not np.all(np.isnan(a)):
            keep = ~np.all(np.isnan(a), axis=1)
            return a[keep]
    raise ValueError("CSV sayısal olarak okunamadı")


def accel_to_disp(a: np.ndarray, fs: float,
                  f_lo: float = 0.5, f_hi: float = 200.0) -> np.ndarray:
    """İvme (m/s²) → yer değiştirme (m), frekans ekseninde çift integral."""
    a = a - np.mean(a)
    n = len(a)
    A = np.fft.rfft(a)
    f = np.fft.rfftfreq(n, 1.0 / fs)
    w = 2.0 * np.pi * f
    D = np.zeros_like(A)
    band = (f >= f_lo) & (f <= f_hi)
    # -1/ω² : iki kez integral. Bant dışı sıfır — DC ve sürüklenme burada ölüyor.
    D[band] = A[band] / (-(w[band] ** 2))
    d = np.fft.irfft(D, n)
    return d - np.mean(d)


def _resample(x: np.ndarray, n_out: int) -> np.ndarray:
    """Bant sınırlı yeniden örnekleme, frekans ekseninde.

    Doğrusal ara değer (np.interp) burada kullanılamaz. 50 Hz'lik bir kaydı
    1 kHz'e doğrusal çıkarmak, örnek noktalarında kırıklı bir yol üretir; yolun
    kendisi düzgün görünse de İVMESİ o kırıklarda ani sıçramalar yapar. Bunun
    iki sonucu var: tork ihtiyacı olduğundan kat kat büyük hesaplanır (bu
    dosyada 1722 mN·m yerine gerçekte çok daha azı), ve tabla o sıçramaları
    gerçekten uygulamaya çalışıp kayda bizim ürettiğimiz bir titreşim katar.

    Spektrumu sıfırla doldurmak, ara değerleri kaynağın bant genişliğine sadık
    kalarak üretir — ivme sürekli kalır.
    """
    n_in = len(x)
    if n_out == n_in:
        return x.astype(float)
    X = np.fft.rfft(x)
    n_new = n_out // 2 + 1
    Y = np.zeros(n_new, dtype=complex)
    m = min(len(X), n_new)
    Y[:m] = X[:m]
    if m < len(X):                       # aşağı örnekleme: en üst bini yarıla
        Y[m - 1] *= 0.5
    return np.fft.irfft(Y, n_out) * (float(n_out) / float(n_in))


def _detrend(x: np.ndarray) -> np.ndarray:
    """Doğrusal eğilimi at. Çift integralden artan çok yavaş kayma burada ölür."""
    if len(x) < 3:
        return x
    t = np.arange(len(x), dtype=float)
    a, b = np.polyfit(t, x, 1)
    return x - (a * t + b)


def _taper(x: np.ndarray, n_edge: int) -> np.ndarray:
    if n_edge <= 0 or 2 * n_edge >= len(x):
        return x
    w = np.ones(len(x))
    r = 0.5 * (1 - np.cos(np.pi * np.arange(n_edge) / n_edge))
    w[:n_edge] = r
    w[-n_edge:] = r[::-1]
    return x * w


def build(path: str,
          col_value: int,
          col_time: Optional[int] = None,
          fs_in: Optional[float] = None,
          units: str = "mm",
          gain: float = 1.0,
          limit_mm: float = 150.0,
          taper_s: float = 0.3,
          f_lo: float = 0.5,
          f_hi: float = 200.0) -> Waveform:
    """CSV'den 1 kHz mutlak adım konumu dizisi üret.

    units: "mm" | "m"  | "m/s2" | "g"
    """
    data = load_columns(path)
    if col_value >= data.shape[1]:
        raise ValueError("değer kolonu yok")
    y = np.asarray(data[:, col_value], dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 8:
        raise ValueError("çok az örnek")

    # örnekleme hızı
    if col_time is not None and col_time < data.shape[1]:
        t = np.asarray(data[:, col_time], dtype=float)[:len(y)]
        dt = np.diff(t)
        dt = dt[np.isfinite(dt) & (dt > 0)]
        if len(dt) == 0:
            raise ValueError("zaman kolonu artmıyor")
        fs = 1.0 / float(np.median(dt))
    elif fs_in:
        fs = float(fs_in)
    else:
        raise ValueError("örnekleme hızı bilinmiyor")

    # birimi metreye getir, gerekiyorsa integre et
    if units == "mm":
        disp_m = y / 1000.0
    elif units == "m":
        disp_m = y.copy()
    elif units in ("m/s2", "g"):
        acc = y * (G if units == "g" else 1.0)
        disp_m = accel_to_disp(acc, fs, f_lo, f_hi)
    else:
        raise ValueError("bilinmeyen birim: %s" % units)

    mm = disp_m * 1000.0 * gain
    mm = mm - np.mean(mm)

    # 1 kHz'e yeniden örnekle
    n_out = max(2, int(round(len(mm) / fs * TICK_HZ)))
    mm = _resample(mm, n_out)

    mm = _detrend(mm)
    mm = _taper(mm, int(taper_s * TICK_HZ))
    steps = np.rint(mm * STEPS_PER_MM).astype(np.int32)

    checks = _checks(mm, steps, limit_mm)
    return Waveform(steps=steps, mm=mm, fs_in=fs, n_in=len(y), checks=checks)


def _checks(mm: np.ndarray, steps: np.ndarray, limit_mm: float) -> list[Check]:
    out: list[Check] = []

    peak = float(np.max(np.abs(mm))) if len(mm) else 0.0
    out.append(Check("Strok", peak <= limit_mm,
                     "tepe ±%.1f mm · sınır ±%.0f mm" % (peak, limit_mm)))

    rate = int(np.max(np.abs(np.diff(steps)))) if len(steps) > 1 else 0
    v_mm_s = rate / STEPS_PER_MM * TICK_HZ
    out.append(Check("Hız", rate <= MAX_STEPS_PER_TICK,
                     "%d adım/ms = %.0f mm/s · sınır %d adım/ms (%.0f mm/s)"
                     % (rate, v_mm_s, MAX_STEPS_PER_TICK,
                        MAX_STEPS_PER_TICK / STEPS_PER_MM * TICK_HZ)))

    fits = bool(np.all(np.abs(steps) <= 32767))
    out.append(Check("int16", fits,
                     "en büyük |konum| %d adım · sınır 32767" % int(np.max(np.abs(steps)))
                     if len(steps) else "boş"))

    # İvme → tork. Sallanan kütle 10,56 kg, kasnak yarıçapı 6,366 mm.
    # Sürücü 1,04 A'e kurulduğunda dinamik tork ~890 mN·m. İki kat pay istiyoruz;
    # kalan payı sürtünme, kayış ön yükü ve rulman direnci yiyor.
    if len(steps) > 2:
        acc = np.diff(mm, 2) * (TICK_HZ ** 2) / 1000.0     # m/s²
        a_pk = float(np.max(np.abs(acc)))
        torque = 10.56 * a_pk * 0.006366                    # N·m
        out.append(Check("Tork", torque <= 0.445,
                         "tepe ivme %.1f m/s² → %.0f mN·m · mevcut 890, sınır 445 (2× pay)"
                         % (a_pk, torque * 1000)))

    ends = abs(float(mm[0])) + abs(float(mm[-1])) if len(mm) else 0.0
    out.append(Check("Uçlar", ends < 0.05,
                     "başlangıç %.3f mm, bitiş %.3f mm — sıçrama yok"
                     % (float(mm[0]) if len(mm) else 0, float(mm[-1]) if len(mm) else 0)))
    return out


def sine_preview(hz: float, amp_mm: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(seconds * TICK_HZ)) / TICK_HZ
    return amp_mm * np.sin(2 * np.pi * hz * t)
