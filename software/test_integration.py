"""Uçtan uca sınama: masaüstü tarafı ↔ firmware, kart olmadan.

Firmware'in bilgisayarda derlenmiş sürümü bir alt süreç olarak çalıştırılıyor ve
`link.py` ona boru üzerinden bağlanıyor. Yani sınanan şey iki tarafın kendi içi
değil, ARALARINDAKİ anlaşma: paket çerçeveleme, bayt sırası, kredi hesabı,
akışın gerçek zamanda yetişip yetişmediği.

Bu ayrımın bedeli var: iki taraf ayrı ayrı doğru olup birlikte yanlış olabiliyor.
Bayt sırasını ters yazmak, krediyi fazla saymak ya da 'D' paketini yanlış
bölmek — üçü de tek taraflı testlerden geçer, sadece uçlar birleşince patlar.

    ./.venv/bin/python test_integration.py
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import time

import numpy as np

import link as lk
import waveform as wf

HERE = os.path.dirname(os.path.abspath(__file__))
SIMDIR = os.path.normpath(os.path.join(HERE, "..", "firmware", "test"))
SIM = os.path.join(SIMDIR, "sim_serial")

fails = 0


def ok(cond, msg, got=""):
    global fails
    if not cond:
        fails += 1
    print("%s%s%s%s" % ("  ok  " if cond else "FAIL  ", msg,
                        "   -> " if got != "" else "", got))


class PipeTransport:
    """link.Link'in beklediği read/write/close arayüzünü bir alt sürece bağlar."""

    def __init__(self, proc):
        self.p = proc
        self.is_open = True

    def read(self, n):
        # firmware sürekli durum yolluyor; kısa okuma normal
        import fcntl
        fd = self.p.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        try:
            data = os.read(fd, n)
        except BlockingIOError:
            time.sleep(0.002)
            return b""
        return data or b""

    def write(self, data):
        self.p.stdin.write(data)
        self.p.stdin.flush()
        return len(data)

    def close(self):
        self.is_open = False
        try:
            self.p.stdin.close()
            self.p.terminate()
            self.p.wait(timeout=2)
        except Exception:
            pass


def build_sim():
    src = os.path.join(SIMDIR, "sim_serial.cpp")
    cmd = ["c++", "-std=c++11", "-O2", "-I" + os.path.join(SIMDIR, "stub"),
           "-o", SIM, src]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[:3000])
        sys.exit("sim_serial derlenemedi")


def start():
    p = subprocess.Popen([SIM], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         bufsize=0)
    link = lk.Link(on_message=lambda m: msgs.append(m))
    link.attach(PipeTransport(p))
    return link


def wait_for(pred, timeout=10.0, poll=0.02):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(poll)
    return False


msgs: list[str] = []

# ----------------------------------------------------------------------
build_sim()
link = start()
try:
    ok(wait_for(lambda: link.status.t > 0 and any(m.startswith("K shaker") for m in msgs), 5),
       "kart acilis mesaji geldi", next((m for m in msgs if m.startswith("K shaker")), "-"))

    # --- 1. temel komutlar ---
    link.home()
    link.set_limits_mm(-150, 150)
    ok(wait_for(lambda: link.status.pos == 0, 3), "H konumu sifirladi",
       str(link.status.pos))

    # --- 2. GOTO: 10 mm ---
    link.goto(10.0, 40.0)
    ok(wait_for(lambda: abs(link.status.pos_mm - 10.0) < 0.02 and link.status.mode == 0, 5),
       "GOTO 10 mm", "%.3f mm" % link.status.pos_mm)
    ok(link.status.pos == 800, "10 mm tam 800 adim", str(link.status.pos))

    # --- 3. JOG ve DUR ---
    link.home()
    link.jog(-30.0)
    time.sleep(0.4)
    moved = link.status.pos_mm
    link.jog(0)
    ok(moved < -5, "JOG negatif yone gitti", "%.2f mm" % moved)
    time.sleep(0.2)
    rest = link.status.pos_mm
    time.sleep(0.3)
    ok(abs(link.status.pos_mm - rest) < 0.02, "J 0 durdurdu",
       "%.3f mm" % link.status.pos_mm)

    # --- 4. yazilim siniri gercekten tutuyor mu ---
    link.home()
    link.set_limits_mm(-5, 5)
    link.jog(80.0)
    time.sleep(0.8)
    link.jog(0)
    ok(link.status.pos_mm <= 5.001, "sinir asilmadi", "%.3f mm" % link.status.pos_mm)
    ok(link.status.clip > 0, "kirpma raporlandi", str(link.status.clip))

    # --- 5. AKIS: sinus dalga formu, uctan uca ---
    link.set_limits_mm(-150, 150)
    link.home()
    time.sleep(0.2)

    N = 3000                                   # 3 saniye
    t = np.arange(N) / wf.TICK_HZ
    mm = 2.0 * np.sin(2 * np.pi * 4.0 * t)
    mm = wf._taper(mm, 300)
    steps = np.rint(mm * wf.STEPS_PER_MM).astype(int)

    seen: list[tuple[float, int]] = []
    link.on_status = lambda st: seen.append((time.time(), st.pos))

    done = {}
    t0 = time.time()
    link.start_stream(list(steps), done_cb=lambda clean: done.update(clean=clean))
    ok(wait_for(lambda: "clean" in done, 20), "akis tamamlandi")
    dur = time.time() - t0

    ok(abs(dur - N / wf.TICK_HZ) < 1.0,
       "sure gercek zamanla uyumlu (%.1f s beklenen 3.0)" % dur, "")
    ok(link.status.under == 0, "UNDERRUN YOK", str(link.status.under))
    ok(link.status.clip == 0, "kirpma yok", str(link.status.clip))
    ok(done.get("clean") is True, "kosu TEMIZ isaretlendi")

    sent, total = link.stream_progress
    ok(sent == N, "butun ornekler gonderildi", "%d/%d" % (sent, N))

    # --- 6. hareket gercekten dalga formu muydu ---
    pk = max(abs(p) for _, p in seen) if seen else 0
    want_pk = int(max(abs(steps)))
    ok(abs(pk - want_pk) <= 8, "tepe konum dalga formuyla ayni",
       "%d adim / beklenen %d" % (pk, want_pk))

    zc = sum(1 for i in range(1, len(seen))
             if seen[i - 1][1] < 0 <= seen[i][1])
    #  4 Hz x 3 s = 12 cevrim; durum 20 Hz orneklendigi icin bir kismi kacar,
    #  ama tamamen yanlis bir frekans burada acikca gorunur.
    ok(6 <= zc <= 12, "hareket ~4 Hz (durum orneklemesiyle sinirli)", str(zc))

    ok(abs(link.status.pos - int(steps[-1])) <= 1, "son konum dalganin sonu",
       "%d / %d" % (link.status.pos, int(steps[-1])))

    # --- 7. bayt sirasi: negatif deger dogru gidiyor mu ---
    link.on_status = None
    link.home()
    time.sleep(0.15)
    neg = [-800] * 300                          # -10 mm'de sabit dur
    d2 = {}
    link.start_stream(neg, done_cb=lambda c: d2.update(clean=c))
    ok(wait_for(lambda: "clean" in d2, 10), "negatif dalga formu oynatildi")
    ok(abs(link.status.pos - (-800)) <= 1,
       "little-endian NEGATIF deger dogru cozuldu", str(link.status.pos))

    # --- 8. acil dur ---
    link.jog(50)
    time.sleep(0.2)
    link.estop()
    time.sleep(0.2)
    p1 = link.status.pos
    time.sleep(0.3)
    ok(link.status.pos == p1, "acil dur sonrasi hareket yok", str(link.status.pos))

finally:
    link.close()

print("\n%d KONTROL BASARISIZ" % fails if fails else "\nhepsi gecti")
sys.exit(1 if fails else 0)
