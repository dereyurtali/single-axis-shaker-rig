"""Arduino Nano step üreteci ile seri bağlantı.

Protokolün bilgisayar tarafı. Firmware'in `firmware/shaker/shaker.ino`
başındaki açıklamasıyla birlikte okunmalı.

Akıştaki tek zor mesele akış denetimi. Nano'nun halka tamponu 256 örnek; biz
saniyede 1000 örnek gönderiyoruz. Fazla göndermek tamponu taşırır (örnek
kaybolur), az göndermek boşaltır (tabla durur). İkisi de sessizdir.

Bu yüzden kredi, kartın bildirdiği boş yer üzerinden yürütülür ve **gönderdiğimiz
ama kartın henüz saymadığı** örnekler düşülür:

    kullanilabilir = son_durumdaki_bos - o_durumdan_beri_gonderilen

Bu bilerek karamsar bir hesap: durum satırı yola çıktıktan sonra tampon boşalmaya
devam ediyor, yani gerçekte daha çok yer var. Az göndermenin bedeli yok (bir
sonraki turda gönderiyoruz), fazla göndermenin bedeli sessiz veri kaybı.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import serial
from serial.tools import list_ports

BAUD = 250000
TICK_HZ = 1000
STEPS_PER_MM = 80.0          # 3200 adım/tur ÷ 40 mm/tur
MAX_CHUNK = 64               # firmware'in 'D' komutu için üst sınır
MAX_STEPS_PER_TICK = 20      # firmware ile aynı olmalı

MODE_NAMES = {0: "boşta", 1: "sürüş", 2: "git", 3: "sinüs", 4: "akış"}


def mm_to_steps(mm: float) -> int:
    return int(round(mm * STEPS_PER_MM))


def steps_to_mm(steps: float) -> float:
    return steps / STEPS_PER_MM


SIM_PORT = "benzetim (kart yok)"


def available_ports() -> list[str]:
    """Gerçek portlar; benzetim en SONDA.

    Benzetim, firmware'in bilgisayarda derlenmiş sürümüne bağlanıyor: aynı kod,
    aynı protokol, sadece adım darbeleri bir motora değil bir sayaca gidiyor.
    Arayüzü kart olmadan görmek ve bir CSV'nin gerçekten oynayıp oynamayacağını
    laboratuvara gitmeden anlamak için.

    Listenin sonunda duruyor ve hiçbir zaman kendiliğinden seçilmiyor: başta
    olsaydı, gerçek kartına bağlandığını sanan biri Bağlan'a basınca benzetime
    bağlanır, tabla kımıldamadığı için donanımda arıza arardı."""
    return [p.device for p in list_ports.comports()] + [SIM_PORT]


class _SimTransport:
    """Firmware'in bilgisayarda çalışan sürümüne giden boru."""

    def __init__(self, proc):
        self.p = proc
        self.is_open = True
        import fcntl
        fd = self.p.stdout.fileno()
        fcntl.fcntl(fd, fcntl.F_SETFL,
                    fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

    def read(self, n):
        try:
            return os.read(self.p.stdout.fileno(), n) or b""
        except BlockingIOError:
            time.sleep(0.002)
            return b""
        except (ValueError, OSError):
            return b""

    def write(self, data):
        self.p.stdin.write(data)
        self.p.stdin.flush()
        return len(data)

    def close(self):
        self.is_open = False
        for step in (self.p.stdin.close, self.p.terminate):
            try:
                step()
            except Exception:
                pass
        try:
            self.p.wait(timeout=2)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass


def build_sim(quiet: bool = True) -> str:
    """sim_serial'i gerekiyorsa derle, yolunu döndür."""
    here = os.path.dirname(os.path.abspath(__file__))
    d = os.path.normpath(os.path.join(here, "..", "firmware", "test"))
    exe, src = os.path.join(d, "sim_serial"), os.path.join(d, "sim_serial.cpp")
    ino = os.path.normpath(os.path.join(here, "..", "firmware", "shaker", "shaker.ino"))
    if not os.path.exists(src):
        raise RuntimeError("sim_serial.cpp bulunamadı: " + src)
    # firmware değiştiyse yeniden derle — yoksa eski davranışı sınarsınız
    fresh = (os.path.exists(exe)
             and os.path.getmtime(exe) > os.path.getmtime(src)
             and os.path.getmtime(exe) > os.path.getmtime(ino))
    if not fresh:
        r = subprocess.run(["c++", "-std=c++11", "-O2", "-I" + os.path.join(d, "stub"),
                            "-o", exe, src], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("benzetim derlenemedi:\n" + r.stderr[-800:])
    return exe


@dataclass
class Status:
    pos: int = 0
    mode: int = 0
    free: int = 0
    under: int = 0
    clip: int = 0
    target: int = 0
    t: float = field(default_factory=time.time)

    @property
    def pos_mm(self) -> float:
        return steps_to_mm(self.pos)

    @property
    def mode_name(self) -> str:
        return MODE_NAMES.get(self.mode, "?")


class Link:
    def __init__(self,
                 on_status: Optional[Callable[[Status], None]] = None,
                 on_message: Optional[Callable[[str], None]] = None) -> None:
        self._ser: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._tx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self.on_status = on_status
        self.on_message = on_message
        self.status = Status()

        # akış durumu
        self._wave: Optional[list[int]] = None
        self._sent = 0
        self._free_at_status = 0
        self._sent_since_status = 0
        self._streaming = False
        self.stream_done_cb: Optional[Callable[[bool], None]] = None

    # ---------------- bağlantı ----------------

    @property
    def is_open(self) -> bool:
        return self._ser is not None and getattr(self._ser, "is_open", True)

    def connect(self, port: str) -> None:
        self.close()
        if port == SIM_PORT:
            exe = build_sim()
            proc = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, bufsize=0)
            self.attach(_SimTransport(proc))
            self._emit("benzetim başladı — firmware bilgisayarda çalışıyor, "
                       "motor yok")
            return
        ser = serial.Serial(port, BAUD, timeout=0.1, write_timeout=2.0)
        # Nano DTR ile resetleniyor; önyükleyici bitene kadar hiçbir şey gönderme.
        time.sleep(1.8)
        ser.reset_input_buffer()
        self.attach(ser)
        self._emit("bağlandı: %s @ %d" % (port, BAUD))

    def attach(self, stream) -> None:
        """Açık bir taşıyıcıyı devral.

        Gerçek kullanımda bu bir `serial.Serial`. Sınamada ise firmware'in
        bilgisayarda çalışan sürümüne giden bir boru oluyor; böylece protokolün
        iki ucu, kart olmadan, gerçekten birbirine konuşturulabiliyor. Aynı
        `read`/`write`/`close` üçlüsünü sunan her nesne çalışır.
        """
        self._stop.clear()
        self._ser = stream
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self._rx_thread.start()
        self._tx_thread.start()

    def close(self) -> None:
        self._stop.set()
        for t in (self._rx_thread, self._tx_thread):
            if t and t.is_alive():
                t.join(timeout=1.0)
        self._rx_thread = self._tx_thread = None
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self._streaming = False

    def _emit(self, msg: str) -> None:
        if self.on_message:
            self.on_message(msg)

    # ---------------- düşük seviye ----------------

    def _write(self, data: bytes) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.write(data)

    def send_line(self, line: str) -> None:
        self._write((line + "\n").encode("ascii"))

    # ---------------- komutlar ----------------

    def home(self) -> None:
        self.send_line("H")

    def set_limits_mm(self, lo_mm: float, hi_mm: float) -> None:
        self.send_line("L %d %d" % (mm_to_steps(lo_mm), mm_to_steps(hi_mm)))

    def jog(self, mm_per_s: float) -> None:
        self.send_line("J %d" % mm_to_steps(mm_per_s))

    def goto(self, mm: float, speed_mm_s: float) -> None:
        sp = max(1, mm_to_steps(abs(speed_mm_s)))
        self.send_line("G %d %d" % (mm_to_steps(mm), sp))

    def sine(self, hz: float, amp_mm: float) -> None:
        self.send_line("N %d %d" % (int(round(hz * 1000)), mm_to_steps(amp_mm)))

    def sine_stop(self) -> None:
        self.send_line("N 0 0")

    def stop(self) -> None:
        self._streaming = False
        self._wave = None
        self.send_line("X")

    def estop(self) -> None:
        self._streaming = False
        self._wave = None
        self.send_line("!")

    # ---------------- akış ----------------

    def start_stream(self, steps: list[int],
                     done_cb: Optional[Callable[[bool], None]] = None) -> None:
        """`steps` mutlak konumlar (adım), 1 kHz'de, sıfır noktasına göre."""
        if not self.is_open:
            raise RuntimeError("bağlı değil")
        self._wave = list(steps)
        self._sent = 0
        self._free_at_status = 0
        self._sent_since_status = 0
        self.stream_done_cb = done_cb
        self._streaming = True
        self.send_line("R %d" % len(self._wave))
        self._emit("akış başlıyor: %d örnek (%.1f s)" % (len(self._wave),
                                                          len(self._wave) / TICK_HZ))

    @property
    def streaming(self) -> bool:
        return self._streaming

    @property
    def stream_progress(self) -> tuple[int, int]:
        return self._sent, (len(self._wave) if self._wave else 0)

    def _tx_loop(self) -> None:
        """Kredi elverdiği sürece dalga formunu parça parça yolla."""
        while not self._stop.is_set():
            if not self._streaming or self._wave is None:
                time.sleep(0.005)
                continue

            room = self._free_at_status - self._sent_since_status
            n = min(room, MAX_CHUNK, len(self._wave) - self._sent)
            if n <= 0:
                if self._sent >= len(self._wave):
                    # hepsi gitti; kartın bitirmesini bekle
                    if self.status.mode != 4:
                        self._finish()
                time.sleep(0.005)
                continue

            chunk = self._wave[self._sent:self._sent + n]
            payload = bytearray()
            for v in chunk:
                v = max(-32768, min(32767, int(v)))
                payload += (v & 0xFFFF).to_bytes(2, "little")
            try:
                self._write(("D %d\n" % n).encode("ascii") + bytes(payload))
            except Exception as exc:                      # pragma: no cover
                self._emit("yazma hatası: %s" % exc)
                self._streaming = False
                continue
            self._sent += n
            self._sent_since_status += n

    def _finish(self) -> None:
        self._streaming = False
        clean = self.status.under == 0 and self.status.clip == 0
        self._emit("akış bitti — underrun %d, kırpma %d" %
                   (self.status.under, self.status.clip))
        if self.stream_done_cb:
            self.stream_done_cb(clean)
        self._wave = None

    # ---------------- alım ----------------

    def _rx_loop(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                data = self._ser.read(256) if self._ser else b""
            except Exception:
                break
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("ascii", "replace").strip()
                if not line:
                    continue
                if line.startswith("S "):
                    self._parse_status(line)
                else:
                    self._emit(line)

    def _parse_status(self, line: str) -> None:
        parts = line.split()
        if len(parts) != 7:
            return
        try:
            st = Status(pos=int(parts[1]), mode=int(parts[2]), free=int(parts[3]),
                        under=int(parts[4]), clip=int(parts[5]), target=int(parts[6]))
        except ValueError:
            return
        self.status = st
        # kredi penceresini yenile
        self._free_at_status = st.free
        self._sent_since_status = 0
        if self.on_status:
            self.on_status(st)
