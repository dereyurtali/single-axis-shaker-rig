"""Sarsma tablası — masaüstü kontrol uygulaması.

    ./.venv/bin/python app.py

Seri port kendi iş parçacığında okunuyor, ama Tkinter tek iş parçacıklıdır ve
başka bir iş parçacığından çağrılırsa sebebi günlerce bulunamayan çökmeler
üretir. Bu yüzden gelen her şey bir kuyruğa bırakılıyor, arayüz onu `after()`
ile kendi iş parçacığında boşaltıyor.
"""

from __future__ import annotations

import math
import os
import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np

import link as lk
import ui
import waveform as wf

# Tavana yaklaşmamak için sinüs ve süpürmede kullanılan pay. Sinüs tablasının
# yuvarlama artıkları tepe eğiminin üstüne ±1 adım bindiriyor; tavanın hemen
# dibinde çalışmak tek tük kırpma üretir ve koşuyu şaibeli gösterir.
RATE_HEADROOM = 0.75
V_MAX_MM_S = wf.MAX_STEPS_PER_TICK * wf.TICK_HZ / wf.STEPS_PER_MM   # 250 mm/s


def sine_rate(hz: float, amp_mm: float) -> float:
    """Sinüsün tepe adım hızı, adım/ms."""
    return amp_mm * wf.STEPS_PER_MM * 2 * math.pi * hz / wf.TICK_HZ


def safe_amp(hz: float) -> float:
    """Bu frekansta pay bırakarak izin verilen en büyük genlik, mm."""
    if hz <= 0:
        return 150.0
    return RATE_HEADROOM * V_MAX_MM_S / (2 * math.pi * hz)


# ======================================================================
class RigView(tk.Canvas):
    """Düzeneğin şematik yandan görünüşü.

    Bu bir imalat resmi değil; koşarken bakılan bir gösterge. O yüzden sadece
    hareketi anlatan dört şey var: kasnağın dönüşü, kayış, taşıyıcı ve üstündeki
    makine. Taban plakası, takozlar, ölçü okları, kopuk gösterim gibi imalat
    ayrıntıları çıkarıldı — koşu sırasında hiçbiri okunmuyordu, sadece
    kalabalık yapıyordu.

    Yatay eksen gerçek ölçekte: strok, sınırlar ve taşıyıcının yeri doğru.
    Makinenin yüksekliği şematik; gerçek boyu 465 mm ve tam ölçekte çizilince
    bütün resmi ezip geri kalanı okunmaz hâle getiriyor.
    """

    RAIL_LEN   = 500.0
    RAIL_Y     = 0.0         # ray ekseni
    CARR_W     = 78.0
    TABLE_W    = 320.0
    PULLEY_R   = 6.366
    MACHINE_W  = 440.0
    # Şematik yükseklik. Gerçeği 465 mm; o boyda çizilince kutu bütün alanı
    # kaplıyor ve asıl bakılan yer — kasnak, kayış, taşıyıcı — dipte ezilip
    # okunmaz hâle geliyor. Koşarken izlenen şey mekanizma, kutu değil.
    MACHINE_H  = 105.0

    def __init__(self, master, **kw):
        super().__init__(master, bg=ui.VIEW, highlightthickness=0, **kw)
        self.pos_mm = 0.0
        self.lo_mm, self.hi_mm = -50.0, 50.0
        self.show_printer = True
        self.show_adxl = True
        self.trail: list[float] = []
        self.bind("<Configure>", lambda e: self.redraw())

    def set_position(self, mm: float) -> None:
        if abs(mm - self.pos_mm) > 1e-6:
            self.pos_mm = mm
            self.trail.append(mm)
            if len(self.trail) > 60:
                del self.trail[:-60]
            self.redraw()

    def set_limits(self, lo: float, hi: float) -> None:
        self.lo_mm, self.hi_mm = lo, hi
        self.redraw()

    def _fit(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return None
        top = 34 + (self.MACHINE_H if self.show_printer else 26) + 16
        # Rayın altındaki her şey (sınır çentikleri, etiketler) piksel cinsinden
        # sabit; mm gibi ölçeklenirse ölçek büyüdükçe altta gereksiz boşluk
        # açılıyor ve çizim yukarı kaçıyor.
        BOT_PX = 44
        span_x = self.RAIL_LEN + self.MACHINE_W * 0.5
        m = 22
        s = min((w - 2 * m) / span_x, (h - 2 * m - BOT_PX) / top)
        free = h - (top * s + BOT_PX)
        return s, w / 2, h - free / 2 - BOT_PX

    def redraw(self) -> None:
        self.delete("all")
        f = self._fit()
        if not f:
            return
        s, cx, y0 = f
        P = lambda x, y: (cx + x * s, y0 - y * s)
        half = self.RAIL_LEN / 2
        x = self.pos_mm

        def rect(x0, ylo, x1, yhi, **kw):
            a, b = P(x0, yhi)
            c, d = P(x1, ylo)
            self.create_rectangle(a, b, c, d, **kw)

        # ---- ray ----
        a, b = P(-half, 0)
        c, d = P(half, 0)
        self.create_line(a, b + 9, c, d + 9, fill=ui.STRUCT_LN, width=3)

        # ---- kayış: iki kol, kasnaklara teğet ----
        px = half - 20
        for dy in (-self.PULLEY_R, self.PULLEY_R):
            a, b = P(-px, dy)
            c, d = P(px, dy)
            self.create_line(a, b, c, d, fill=ui.VIEW_INK, width=2)

        # ---- kasnaklar: soldaki tahrik, dönüşü işaretli ----
        r = max(9.0, self.PULLEY_R * s * 1.6)
        for sx, col in ((-1, ui.MOTION), (1, ui.STRUCT_LN)):
            a, b = P(sx * px, 0)
            self.create_oval(a - r, b - r, a + r, b + r, outline=col, width=2,
                             fill=ui.VIEW)
            if sx < 0:
                th = self.pos_mm / 40.0 * 2 * math.pi
                for k in (0, 1):                      # iki kollu işaret
                    t = th + k * math.pi
                    self.create_line(a, b, a + r * .82 * math.cos(-t),
                                     b + r * .82 * math.sin(-t),
                                     fill=ui.MOTION, width=2)
        a, b = P(-px, -20)
        self.create_text(a, b + 14, text="motor", fill=ui.VIEW_INK2,
                         font=ui.MONO_XS)

        # ---- strok ----
        # Makine 440 mm, ray 500 mm, strok 100 mm. Yalnızca iki çentik
        # koyunca bu oran görünmüyordu: çizim makinenin ray boyunca
        # gezebileceğini ima ediyordu, oysa gezdiği yer kendi boyunun dörtte
        # biri kadar. Ölçü çizgisi bunu açıkça söylüyor.
        yl = P(0, 0)[1] + 24
        a1, _ = P(self.lo_mm, 0)
        a2, _ = P(self.hi_mm, 0)
        self.create_line(a1, yl, a2, yl, fill=ui.VIEW_WARN, width=1.5)
        for xx in (a1, a2):
            self.create_line(xx, P(0, 0)[1] + 9, xx, yl + 5, fill=ui.VIEW_WARN,
                             width=1.5)
        self.create_text((a1 + a2) / 2, yl + 13,
                         text="strok %g mm" % (self.hi_mm - self.lo_mm),
                         fill=ui.VIEW_WARN, font=ui.MONO_XS)
        # makinenin uç konumlardaki yeri — kaplanan alan
        for v in (self.lo_mm, self.hi_mm):
            if self.show_printer:
                c1, d1 = P(v - self.MACHINE_W / 2, 34)
                c2, d2 = P(v + self.MACHINE_W / 2, 34 + self.MACHINE_H)
                self.create_rectangle(c1, d2, c2, d1, outline="#e3e7ea", dash=(3, 3))

        # ---- gezilen aralık ----
        if len(self.trail) > 3:
            lo, hi = min(self.trail), max(self.trail)
            if hi - lo > 0.05:
                a, b = P(lo, 0)
                c, d = P(hi, 0)
                self.create_line(a, b + 17, c, d + 17, fill=ui.MOTION, width=2)

        # ---- taşıyıcı ----
        rect(x - self.CARR_W / 2, 4, x + self.CARR_W / 2, 26,
             fill=ui.STRUCT, outline=ui.STRUCT_LN)

        # ---- tabla ----
        rect(x - self.TABLE_W / 2, 26, x + self.TABLE_W / 2, 34,
             fill=ui.MEAS, outline="")

        # ---- makine ----
        if self.show_printer:
            m0, mh, mw = 34.0, self.MACHINE_H, self.MACHINE_W / 2
            rect(x - mw, m0, x + mw, m0 + mh, fill="#f4f6f7",
                 outline=ui.STRUCT_LN)
            a, b = P(x, m0 + mh / 2)
            self.create_text(a, b, text="Ender-3 V2", fill=ui.VIEW_INK2,
                             font=ui.MONO_S)

        if self.show_adxl:
            # İşaretler yerinde, adları köşedeki açıklamada. Satır içine
            # yazılınca "tabla" camgöbeği çubuğun üstüne düşüyor ve yeşil yazı
            # orada okunmuyordu; konum değiştikçe hangi yazının neyin üstüne
            # geleceği de önceden kestirilemiyor.
            for xx, yy, lab in ((x - self.TABLE_W / 2 + 22, 30, "tabla"),
                                (x + 46, 34 + self.MACHINE_H * .58, "kafa")):
                if lab == "kafa" and not self.show_printer:
                    continue
                a, b = P(xx, yy)
                rr = max(3.0, 7 * s)
                self.create_rectangle(a - rr, b - rr * .55, a + rr, b + rr * .55,
                                      fill=ui.VIEW_OK, outline="")
            self._legend()

        # ---- konum ----
        self.create_text(14, 12, anchor="nw", font=("Menlo", 15),
                         fill=ui.MOTION, text="%+.2f mm" % self.pos_mm)

    def _legend(self):
        """İvmeölçer adları — çizimin içinde değil, sağ üst köşede."""
        w = self.winfo_width()
        rows = [("tabla", ui.VIEW_OK), ("kafa", ui.VIEW_OK)]
        if not self.show_printer:
            rows = rows[:1]
        for i, (lab, col) in enumerate(rows):
            y = 16 + i * 15
            self.create_rectangle(w - 74, y - 4, w - 64, y + 3, fill=col,
                                  outline="")
            self.create_text(w - 58, y, anchor="w", text=lab, fill=ui.INK_2,
                             font=ui.MONO_XS)


# ======================================================================
class PlotView(tk.Canvas):
    """Dalga formu grafiği: zaman ekseni, ızgara, tepe/etkin değerler.

    Eksensiz bir eğri "bir şeyler oynuyor" der ve orada biter. Zaman ekseni ve
    yanındaki Min/Maks/RMS, bakan kişinin dosyanın gerçekten beklediği sinyal
    olup olmadığını ekrandan anlamasını sağlıyor — yanlış kolonu seçmiş olmak
    en sık yapılan hata ve tek belirtisi grafiğin "tuhaf" görünmesi.
    """

    PAD_L, PAD_R, PAD_T, PAD_B = 46, 12, 10, 22

    def __init__(self, master, **kw):
        super().__init__(master, bg=ui.VIEW, highlightthickness=0, **kw)
        self.y = None
        self.fs = wf.TICK_HZ
        self.cursor = None
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, y, fs=None):
        self.y = None if y is None or len(y) == 0 else np.asarray(y, dtype=float)
        if fs:
            self.fs = fs
        self.cursor = None
        self.redraw()

    def set_cursor(self, frac):
        self.cursor = frac
        self.redraw()

    def stats(self):
        if self.y is None:
            return None
        y = self.y
        return (float(y.min()), float(y.max()),
                float(np.sqrt(np.mean(y ** 2))), len(y) / self.fs)

    def redraw(self):
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 60 or H < 40:
            return
        x0, x1 = self.PAD_L, W - self.PAD_R
        y0, y1 = self.PAD_T, H - self.PAD_B
        if x1 <= x0 or y1 <= y0:
            return

        if self.y is None:
            self.create_text(W / 2, H / 2, text="dalga formu yüklenmedi",
                             fill=ui.VIEW_INK2, font=ui.UI_S)
            return

        y = self.y
        peak = max(abs(float(y.min())), abs(float(y.max()))) or 1.0
        peak = self._nice(peak)
        dur = len(y) / self.fs

        sy = lambda v: y1 - (v + peak) / (2 * peak) * (y1 - y0)
        sx = lambda t: x0 + t / dur * (x1 - x0)

        # ---- ızgara ve eksen ----
        for frac in (-1, -0.5, 0, 0.5, 1):
            v = peak * frac
            yy = sy(v)
            self.create_line(x0, yy, x1, yy,
                             fill=ui.VIEW_AXIS if frac == 0 else ui.VIEW_GRID)
            self.create_text(x0 - 6, yy, anchor="e", text="%g" % round(v, 3),
                             fill=ui.VIEW_INK2, font=ui.MONO_XS)
        nt = max(2, min(10, int((x1 - x0) / 90)))
        for k in range(nt + 1):
            t = dur * k / nt
            xx = sx(t)
            self.create_line(xx, y0, xx, y1, fill=ui.VIEW_GRID)
            self.create_text(xx, y1 + 11, text=("%.4g" % t),
                             fill=ui.VIEW_INK2, font=ui.MONO_XS)
        self.create_text((x0 + x1) / 2, H - 4, text="saniye",
                         fill=ui.VIEW_INK2, font=ui.MONO_XS)

        # ---- eğri: piksel başına min/max, tepe değerler kaybolmasın ----
        cols = max(2, int(x1 - x0))
        idx = np.linspace(0, len(y), cols + 1).astype(int)
        hi, lo = [], []
        for i in range(cols):
            seg = y[idx[i]:max(idx[i] + 1, idx[i + 1])]
            if not len(seg):
                continue
            hi += [x0 + i, sy(seg.max())]
            lo += [x0 + i, sy(seg.min())]
        if len(hi) >= 4:
            self.create_line(*hi, fill=ui.MEAS)
            self.create_line(*lo, fill=ui.MEAS)

        if self.cursor is not None:
            xx = sx(self.cursor * dur)
            self.create_line(xx, y0, xx, y1, fill=ui.MOTION, width=2)
            self.create_text(xx, y0 + 2, anchor="n",
                             text="%.2f s" % (self.cursor * dur),
                             fill=ui.MOTION, font=ui.MONO_XS)

    @staticmethod
    def _nice(v):
        """Eksen ucunu okunur bir sayıya yuvarla."""
        import math as _m
        e = _m.floor(_m.log10(v)) if v > 0 else 0
        b = v / (10 ** e)
        return (1 if b <= 1 else 2 if b <= 2 else 5 if b <= 5 else 10) * 10 ** e


# ======================================================================
class App(tk.Tk):
    """Pencere düzeni, ölçüm yazılımlarının yerleşimi:

        menü çubuğu
        araç çubuğu          birincil eylemler, işlevine göre kümelenmiş
        ┌──────────────┬────────────────────────────────┐
        │ parametreler │  ÖLÇÜM ALANI (baskın)          │
        │ (ızgara)     ├────────────────────────────────┤
        │              │  dalga formu                   │
        │              ├────────────────────────────────┤
        │              │  koşu kaydı  |  günlük         │
        └──────────────┴────────────────────────────────┘
        durum çubuğu         ince, bölmeli

    Baskın olan ölçüm alanı; parametreler yanda dar bir sütunda, sürekli değişen
    sayılar en altta ince bir şeritte duruyor. Önceki düzende bu sayılar ana
    alanda büyük kutulardaydı: hem yer yiyorlardı hem de gözü kendilerine
    çekiyorlardı, oysa arada bir bakılan değerler.
    """

    def __init__(self):
        super().__init__()
        self.title("Sarsma tablası — kontrol")
        self.configure(bg=ui.BG)
        self.geometry("1320x880")
        self.minsize(1100, 720)

        self.q: queue.Queue = queue.Queue()
        self.link = lk.Link(on_status=lambda s: self.q.put(("status", s)),
                            on_message=lambda m: self.q.put(("msg", m)))
        self.wave: wf.Waveform | None = None
        self.csv_path: str | None = None
        self.sweep = None
        self._jog_stop_id = None
        self._pump_id = None
        self._sweep_id = None
        self._closing = False
        self._run_no = 0
        self._run_t0 = 0.0
        self._run_kind = None
        self._run_dur = None
        self.runs: list[dict] = []
        self._csv_cols: list[str] = []
        self._vel = 0.0
        self._last_pos = None
        self._last_t = 0.0
        self.pg_csv_widgets: dict = {}

        self._menu()
        self._build()
        self._kill_focus_rings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._pump_id = self.after(30, self._pump)
        for k in ("<Escape>", "<space>"):
            self.bind(k, lambda e: self._estop())
        self.bind("<Left>",  lambda e: self._jog_key(-1))
        self.bind("<Right>", lambda e: self._jog_key(+1))
        self.bind("<KeyRelease-Left>",  lambda e: self._jog_key_release())
        self.bind("<KeyRelease-Right>", lambda e: self._jog_key_release())
        self._sine_changed()

    def _kill_focus_rings(self):
        """Odak halkası rengini her bileşende zemine çek.

        Tk'de `highlightcolor` verilmezse macOS varsayılanı systemTextColor,
        yani siyah. Odak bir bileşene geldiğinde çevresine siyah bir çerçeve
        çiziliyor; dar bileşenlerde bu, kutunun içinde duran bir dikey/yatay
        siyah çizgi gibi görünüyor."""
        def walk(w):
            for ch in w.winfo_children():
                try:
                    if int(ch.cget("highlightthickness")) > 0:
                        ch.config(highlightcolor=ch.cget("highlightbackground"))
                except Exception:
                    pass
                walk(ch)
        walk(self)

    # ================================================== menü
    def _menu(self):
        bar = tk.Menu(self)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="CSV aç…", accelerator="⌘O", command=self._pick_csv)
        m.add_command(label="Dalga formunu hazırla", command=self._prepare)
        m.add_separator()
        m.add_command(label="Koşu kaydını temizle", command=lambda: self.table.clear())
        bar.add_cascade(label="Dosya", menu=m)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="Bağlan / kes", command=self._toggle_conn)
        m.add_command(label="Portları tara", command=self._refresh_ports)
        m.add_separator()
        m.add_command(label="Sıfır kabul et", command=self._home)
        m.add_command(label="Sınırları uygula", command=self._apply_limits)
        m.add_separator()
        m.add_command(label="ACİL DUR", accelerator="Esc", command=self._estop)
        bar.add_cascade(label="Cihaz", menu=m)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="Sinüs başlat", command=self._sine_start)
        m.add_command(label="Sinüs durdur", command=self._sine_stop)
        m.add_command(label="Süpürme başlat / durdur", command=self._sweep_toggle)
        m.add_separator()
        m.add_command(label="Kaydı oynat", command=self._play)
        bar.add_cascade(label="Ölçüm", menu=m)

        m = tk.Menu(bar, tearoff=0)
        self.v_printer = tk.BooleanVar(value=True)
        self.v_adxl = tk.BooleanVar(value=True)
        m.add_checkbutton(label="Yazıcı", variable=self.v_printer,
                          command=self._toggle)
        m.add_checkbutton(label="İvmeölçerler", variable=self.v_adxl,
                          command=self._toggle)
        bar.add_cascade(label="Görünüm", menu=m)

        self.config(menu=bar)
        self.bind("<Command-o>", lambda e: self._pick_csv())

    # ================================================== iskelet
    def _build(self):
        self._build_header()
        # Günlük gövdeden ÖNCE paketleniyor. Tk paketleyicisi sırayla yer
        # ayırıyor: expand=True olan gövde önce gelirse boşluğun tamamını alıyor
        # ve alttaki şeride sıfır piksel kalıyor — günlük 1x1 çiziliyordu.
        self._build_log()

        body = tk.Frame(self, bg=ui.BG)
        body.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        left = ui.ScrollColumn(body, width=280)
        left.pack(side="left", fill="y", padx=(0, 9))
        right = ui.ScrollColumn(body, width=336)
        right.pack(side="right", fill="y", padx=(9, 0))
        mid = tk.Frame(body, bg=ui.BG)
        mid.pack(side="left", fill="both", expand=True)

        # Her sütunun tek işi var. Karışık dağıtıldığında orta sütun dört
        # paneli birden taşımak zorunda kalıyor, düzenek çizimi 125 piksele
        # düşüyor ve sinüs panelinin alt satırları kesiliyordu.
        #   sol    kumanda
        #   orta   izleme
        #   sağ    veri
        self._build_status(left.body)
        self._build_limits(left.body)
        self._build_manual(left.body)
        self._build_sine(left.body)

        self._build_tiles(mid)
        self._build_plot(mid)
        self._build_rig(mid)

        self._build_csv(right.body)
        self._build_runstate(right.body)
        self._build_runs(right.body)

    # -------------------------------------------------- başlık
    def _build_header(self):
        h = tk.Frame(self, bg=ui.CARD, highlightbackground=ui.RULE,
                     highlightthickness=1)
        h.pack(fill="x")
        r = tk.Frame(h, bg=ui.CARD)
        r.pack(fill="x", padx=14, pady=8)

        tk.Label(r, text="SARSMA TABLASI", bg=ui.CARD, fg=ui.INK,
                 font=("Helvetica Neue", 14, "bold")).pack(side="left")
        tk.Frame(r, bg=ui.RULE, width=1, height=20).pack(side="left", padx=14)

        self.lamp_conn = ui.Lamp(r, d=10, bg=ui.CARD)
        self.lamp_conn.pack(side="left", padx=(0, 6))
        self.lb_conn = tk.Label(r, text="BAĞLI DEĞİL", bg=ui.CARD, fg=ui.INK_3,
                                font=ui.LEGEND)
        self.lb_conn.pack(side="left")
        self.lb_port = tk.Label(r, text="—", bg=ui.CARD, fg=ui.INK_2,
                                font=ui.MONO_S)
        self.lb_port.pack(side="left", padx=(14, 0))
        tk.Label(r, text="%d bps" % lk.BAUD, bg=ui.CARD, fg=ui.INK_3,
                 font=ui.MONO_S).pack(side="left", padx=(14, 0))

        ui.button(r, "ACİL DUR", self._estop, "danger",
                  font=("Helvetica Neue", 12, "bold"),
                  padx=18).pack(side="right")

        self.v_port = tk.StringVar()
        ports = lk.available_ports()
        real = [p for p in ports if p != lk.SIM_PORT]
        self.v_port.set(real[0] if real else (ports[0] if ports else ""))
        self.btn_conn = ui.button(r, "Bağlan", self._toggle_conn, "primary",
                                  padx=16)
        self.btn_conn.pack(side="right", padx=(0, 8))
        self.om = ui.option(r, self.v_port, ports or ["—"], width=20)
        self.om.pack(side="right", padx=(0, 6))
        ui.button(r, "Tara", self._refresh_ports).pack(side="right", padx=(0, 6))

    # -------------------------------------------------- sol sütun
    def _build_status(self, p):
        c = ui.card(p, "Sistem durumu")
        self.kv = ui.KeyValue(c, [
            ("pos",   "Konum",           "mm"),
            ("vel",   "Hız",             "mm/s"),
            ("rpm",   "Motor devri",     "d/dk"),
            ("mode",  "Kip",             ""),
            ("buf",   "Veri tamponu",    "%"),
            ("under", "Underrun",        ""),
            ("clip",  "Kırpma",          ""),
        ])
        self.kv.pack(fill="x")
        self.bar_buf = ui.Bar(c, height=6)
        self.bar_buf.pack(fill="x", pady=(8, 0))

    def _build_limits(self, p):
        c = ui.card(p, "Yazılım sınırları")
        g = ui.PropertyGrid(c)
        g.pack(fill="x")
        self.e_lo, self.e_hi = g.pair("lo", "hi", "Strok", -50, 50, "mm")
        g.readonly("vmax", "Hız tavanı", "mm/s", "%.0f" % V_MAX_MM_S)
        g.readonly("res", "Çözünürlük", "µm", "%.1f" % (1000 / wf.STEPS_PER_MM))
        ui.button(c, "Sınırları uygula", self._apply_limits).pack(fill="x",
                                                                  pady=(9, 0))

    def _build_manual(self, p):
        c = ui.card(p, "Elle sürüş")
        g = ui.PropertyGrid(c)
        g.pack(fill="x")
        self.v_speed, self._lb_speed = g.slider(
            "speed", "Hız", 1, 150, 20, "mm/s",
            lambda v: self._lb_speed.config(text="%g" % float(v)), 1.0, "%g")
        self.e_goto = g.entry("goto", "Hedef konum", "0", "mm")

        jg = tk.Frame(c, bg=ui.CARD)
        jg.pack(fill="x", pady=(10, 0))
        for txt, sign, kind in (("◀◀", -1, "fast"), ("◀", -1, "slow"),
                                ("■", 0, "stop"),
                                ("▶", +1, "slow"), ("▶▶", +1, "fast")):
            b = ui.button(jg, txt, None, padx=8, font=("Helvetica Neue", 12))
            b.pack(side="left", fill="x", expand=True, padx=1)
            if kind == "stop":
                b.command = lambda: self._jog(0)
            else:
                mul = 3.0 if kind == "fast" else 1.0
                b.bind("<ButtonPress-1>", lambda e, s=sign, m=mul: self._jog(s, m))
                b.bind("<ButtonRelease-1>", lambda e: self._jog(0))

        r = tk.Frame(c, bg=ui.CARD)
        r.pack(fill="x", pady=(9, 0))
        ui.button(r, "Git", self._goto).pack(side="left", fill="x", expand=True,
                                             padx=(0, 3))
        ui.button(r, "Sıfır kabul et", self._home).pack(side="left", fill="x",
                                                        expand=True, padx=(3, 0))

    # -------------------------------------------------- orta sütun
    def _build_tiles(self, p):
        row = tk.Frame(p, bg=ui.BG)
        row.pack(fill="x")
        self.tiles = {}
        for key, lab, unit in (("pos", "Konum", "mm"), ("vel", "Hız", "mm/s"),
                               ("mode", "Kip", ""), ("buf", "Tampon", "%")):
            t = ui.StatTile(row, lab, unit)
            t.pack(side="left", fill="both", expand=True,
                   padx=(0, 8) if key != "buf" else 0)
            self.tiles[key] = t

    def _build_plot(self, p):
        shell = tk.Frame(p, bg=ui.CARD, highlightbackground=ui.RULE,
                         highlightthickness=1)
        shell.pack(fill="x", pady=(9, 0))
        head = tk.Frame(shell, bg=ui.CARD_HEAD)
        head.pack(fill="x")
        tk.Label(head, text="Dalga formu", bg=ui.CARD_HEAD, fg=ui.INK,
                 font=ui.LEGEND).pack(side="left", padx=12, pady=5)
        self.lb_plot = tk.Label(head, text="", bg=ui.CARD_HEAD, fg=ui.INK_2,
                                font=ui.MONO_XS)
        self.lb_plot.pack(side="right", padx=12)
        tk.Frame(shell, bg=ui.RULE_S, height=1).pack(fill="x")
        self.plot = PlotView(shell, height=118)
        self.plot.pack(fill="x")

    def _build_rig(self, p):
        shell = tk.Frame(p, bg=ui.CARD, highlightbackground=ui.RULE,
                         highlightthickness=1)
        shell.pack(fill="both", expand=True, pady=(9, 0))
        head = tk.Frame(shell, bg=ui.CARD_HEAD)
        head.pack(fill="x")
        tk.Label(head, text="Düzenek izleme", bg=ui.CARD_HEAD, fg=ui.INK,
                 font=ui.LEGEND).pack(side="left", padx=12, pady=5)
        self.v_printer = tk.BooleanVar(value=True)
        self.v_adxl = tk.BooleanVar(value=True)
        for var, txt in ((self.v_adxl, "ivmeölçer"), (self.v_printer, "makine")):
            tk.Checkbutton(head, text=txt, variable=var, command=self._toggle,
                           bg=ui.CARD_HEAD, fg=ui.INK_2, selectcolor=ui.FIELD,
                           activebackground=ui.CARD_HEAD, font=ui.MONO_XS,
                           highlightthickness=0, bd=0).pack(side="right", padx=(0, 8))
        tk.Frame(shell, bg=ui.RULE_S, height=1).pack(fill="x")

        body = tk.Frame(shell, bg=ui.CARD)
        body.pack(fill="both", expand=True)
        # İki yan kutu ÖNCE paketleniyor, tuval en son. Ters sırada tuval
        # expand=True ile yeri kapıyor ve dar pencerede en son paketlenen kutu
        # eziliyor — "TAŞIYICI" başlığı kırpılıyordu. Daralması gereken şey
        # tuval; sayılar okunur kalmalı.
        self.kv_motor = self._mini(body, "Motor", [("rpm", "Devir", "d/dk"),
                                                   ("dir", "Yön", "")])
        self.kv_motor.master.pack(side="left", fill="y", padx=10, pady=10)
        self.kv_carr = self._mini(body, "Taşıyıcı", [("pos", "Konum", "mm"),
                                                     ("vel", "Hız", "mm/s")])
        self.kv_carr.master.pack(side="right", fill="y", padx=10, pady=10)
        self.rig = RigView(body)
        self.rig.pack(side="left", fill="both", expand=True)

    def _mini(self, parent, title, rows):
        # Sabit genişlik: dar pencerede bu kutular sıkışıp başlıklarını
        # kırpıyordu. Daralan şey çizim tuvali olmalı, sayılar değil.
        box = tk.Frame(parent, bg=ui.CARD, highlightbackground=ui.RULE_S,
                       highlightthickness=1, width=152)
        box.pack_propagate(False)
        tk.Label(box, text=title.upper(), bg=ui.CARD, fg=ui.INK_3,
                 font=ui.LABEL, anchor="w").pack(fill="x", padx=10, pady=(7, 3))
        kv = ui.KeyValue(box, rows, width=8)
        kv.pack(fill="x", padx=10, pady=(0, 9))
        return kv

    def _build_sine(self, p):
        c = ui.card(p, "Sinüs / süpürme", "geçirgenlik")
        g = ui.PropertyGrid(c)
        g.pack(fill="x")
        self.v_hz, self.lb_hz = g.slider(
            "hz", "Frekans", 0, 1000, self._hz_to_slider(20.0), "Hz",
            lambda v: self._sine_changed(), 1.0)
        self.v_amp, self.lb_amp = g.slider(
            "amp", "Genlik", 0.01, 20.0, 1.0, "mm",
            lambda v: self._sine_changed(), 0.01, "%.2f")
        self.lb_v = g.readonly("v", "Tepe hız", "mm/s")
        self.lb_a = g.readonly("a", "Tepe ivme", "m/s²")
        self.lb_g = g.readonly("g", "Tepe ivme", "g")
        self.bar_r, self.lb_r = g.bar("rate", "Adım hızı", "/20")
        self.e_f1, self.e_f2 = g.pair("f1", "f2", "Süpürme", 2, 80, "Hz")
        self.e_dur = g.entry("dur", "Süre", "90", "s")

        b = tk.Frame(c, bg=ui.CARD)
        b.pack(fill="x", pady=(10, 0))
        self.btn_sine = ui.button(b, "Sinüs", self._sine_toggle)
        self.btn_sine.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_sweep = ui.button(b, "Süpür", self._sweep_toggle)
        self.btn_sweep.pack(side="left", fill="x", expand=True, padx=(3, 0))

    # -------------------------------------------------- sağ sütun
    def _build_runstate(self, p):
        c = ui.card(p, "Koşu durumu")
        self.kv_run = ui.KeyValue(c, [("state", "Durum", ""),
                                      ("elapsed", "Geçen süre", ""),
                                      ("left", "Kalan süre", ""),
                                      ("prog", "İlerleme", "%")], width=9)
        self.kv_run.pack(fill="x")
        self.bar_run = ui.Bar(c, height=6)
        self.bar_run.pack(fill="x", pady=(8, 0))
        ui.button(c, "Durdur", self._estop).pack(fill="x", pady=(10, 0))

    def _build_csv(self, p):
        c = ui.card(p, "Veri dosyası", "CSV")
        r = tk.Frame(c, bg=ui.CARD)
        r.pack(fill="x")
        self.lb_file = tk.Label(r, text="dosya seçilmedi", bg=ui.FIELD,
                                fg=ui.INK_2, font=ui.MONO_XS, anchor="w",
                                padx=8, pady=5, highlightthickness=1,
                                highlightbackground=ui.RULE)
        self.lb_file.pack(side="left", fill="x", expand=True)
        ui.button(r, "Seç…", self._pick_csv, padx=10).pack(side="left", padx=(6, 0))

        g = ui.PropertyGrid(c)
        g.pack(fill="x", pady=(9, 0))
        self.v_tcol = g.choice("tcol", "Zaman kolonu", ["—"], width=13)
        self.v_vcol = g.choice("vcol", "Değer kolonu", ["—"], width=13)
        # Menüleri sonradan doldurabilmek için widget'ları sakla
        self.pg_csv_widgets[id(self.v_tcol)] = g.widgets["tcol"]
        self.pg_csv_widgets[id(self.v_vcol)] = g.widgets["vcol"]
        self.v_unit = g.choice("unit", "Birim", ["mm", "m", "m/s2", "g"], width=13)
        self.e_fs = g.entry("fs", "Örnekleme", "1000", "Hz")
        self.e_gain = g.entry("gain", "Kazanç", "1", "×")

        ui.button(c, "Dosyayı yükle", self._prepare, "primary").pack(
            fill="x", pady=(10, 0))

        tk.Label(c, text="GÜVENLİK KONTROLLERİ", bg=ui.CARD, fg=ui.INK_3,
                 font=ui.LABEL, anchor="w").pack(fill="x", pady=(12, 4))
        self.f_checks = tk.Frame(c, bg=ui.CARD)
        self.f_checks.pack(fill="x")
        tk.Label(self.f_checks, text="dosya yüklenmedi", bg=ui.CARD,
                 fg=ui.INK_3, font=ui.MONO_XS).pack(anchor="w")

        self.btn_play = ui.button(c, "Oynat", self._play, "primary",
                                  state="disabled")
        self.btn_play.pack(fill="x", pady=(10, 0))

    def _build_runs(self, p):
        c = ui.card(p, "Koşu kayıtları")
        self.table = ui.Table(c, ("#", "tür", "süre", "und", "kır", "ok"),
                              (3, 10, 8, 4, 4, 3))
        self.table.pack(fill="both", expand=True)
        ui.button(c, "Tabloyu dışa aktar", self._export_runs).pack(
            fill="x", pady=(9, 0))

    # -------------------------------------------------- günlük
    def _build_log(self):
        shell = tk.Frame(self, bg=ui.CARD, highlightbackground=ui.RULE,
                         highlightthickness=1)
        shell.pack(fill="x", side="bottom", padx=10, pady=10)
        head = tk.Frame(shell, bg=ui.CARD_HEAD)
        head.pack(fill="x")
        tk.Label(head, text="Olay günlüğü", bg=ui.CARD_HEAD, fg=ui.INK,
                 font=ui.LEGEND).pack(side="left", padx=12, pady=5)
        ui.button(head, "Temizle", lambda: self.log.clear(), padx=9,
                  pady=2).pack(side="right", padx=(0, 8), pady=3)
        ui.button(head, "Kaydet", self._save_log, padx=9,
                  pady=2).pack(side="right", padx=(0, 6), pady=3)
        tk.Frame(shell, bg=ui.RULE_S, height=1).pack(fill="x")
        self.log = ui.LogView(shell, height=5)
        self.log.pack(fill="both", expand=True)

    # ================================================== bağlantı
    def _refresh_ports(self):
        ports = lk.available_ports() or ["—"]
        m = self.om["menu"]
        m.delete(0, "end")
        for p in ports:
            m.add_command(label=p, command=lambda v=p: self.v_port.set(v))
        real = [p for p in ports if p != lk.SIM_PORT]
        self.v_port.set(real[0] if real else ports[0])
        self._log("%d port bulundu" % len(ports))

    def _toggle_conn(self):
        if self.link.is_open:
            self.link.close()
            self.btn_conn.config(text="Bağlan")
            self.lb_conn.config(text="BAĞLI DEĞİL", fg=ui.INK_3)
            self.lb_port.config(text="—")
            self.lamp_conn.set(ui.INK_3)
            self._log("bağlantı kapatıldı")
            return
        port = self.v_port.get()
        if not port or port == "—":
            return messagebox.showwarning("Port yok", "Önce bir seri port seçin.")
        try:
            self.link.connect(port)
        except Exception as exc:
            self._log("bağlanamadı: %s" % exc, "hata")
            return messagebox.showerror("Bağlanamadı", str(exc))
        self.btn_conn.config(text="Kes")
        self.lb_conn.config(text="BAĞLI", fg=ui.OKC)
        self.lb_port.config(text=port)
        self.lamp_conn.set(ui.OKC)
        self._apply_limits()

    # ================================================== elle sürüş
    def _home(self):
        if self._need():
            self.link.home()
            self.rig.trail.clear()
            self._log("konum sıfırlandı")

    def _apply_limits(self):
        if not self.link.is_open:
            return
        try:
            lo, hi = float(self.e_lo.get()), float(self.e_hi.get())
        except ValueError:
            return messagebox.showwarning("Sınır", "Sayı girin.")
        if lo >= hi:
            return messagebox.showwarning("Sınır", "min < max olmalı.")
        self.link.set_limits_mm(lo, hi)
        self.rig.set_limits(lo, hi)
        self._log("sınırlar okundu: [%+g, %+g] mm · hız tavanı %.0f mm/s"
                  % (lo, hi, V_MAX_MM_S))

    def _jog(self, sign, mul=1.0):
        if self.link.is_open:
            self.link.jog(sign * self.v_speed.get() * mul)

    def _jog_key(self, sign):
        """Ok tuşu. Klavye tekrarı basma/bırakma çifti ürettiği için bırakma
        anında hemen durdurmuyoruz; 130 ms içinde yeni basma gelirse sürüş
        kesintisiz devam ediyor, gelmezse duruyor."""
        if self._jog_stop_id:
            self.after_cancel(self._jog_stop_id)
            self._jog_stop_id = None
        self._jog(sign)

    def _jog_key_release(self):
        if self._jog_stop_id:
            self.after_cancel(self._jog_stop_id)
        self._jog_stop_id = self.after(130, lambda: self._jog(0))

    def _goto(self):
        if not self._need():
            return
        try:
            self.link.goto(float(self.e_goto.get()), self.v_speed.get())
        except ValueError:
            messagebox.showwarning("Git", "Sayı girin.")

    # ================================================== sinüs
    @staticmethod
    def _hz_to_slider(hz):
        return 1000 * math.log(max(0.5, hz) / 0.5) / math.log(200 / 0.5)

    @staticmethod
    def _slider_to_hz(v):
        return 0.5 * (200 / 0.5) ** (v / 1000.0)

    def _sine_changed(self, *_):
        hz = self._slider_to_hz(self.v_hz.get())
        amp = self.v_amp.get()
        cap = safe_amp(hz)
        # Genliği frekansa göre kıs: tarama sırasında istenen frekansı
        # gezdirmek, genliği elle kovalamak değil.
        if amp > cap:
            amp = round(cap, 2)
            self.v_amp.set(amp)

        self.lb_hz.config(text="%.4g" % hz)
        self.lb_amp.config(text="%.2f" % amp)
        v = amp * 2 * math.pi * hz
        acc = amp / 1000 * (2 * math.pi * hz) ** 2
        rate = sine_rate(hz, amp)
        self.lb_v.config(text="%.1f" % v)
        self.lb_a.config(text="%.2f" % acc)
        self.lb_g.config(text="%.3f" % (acc / 9.80665))
        self.lb_r.config(text="%.1f" % rate,
                         fg=ui.BADC if rate > wf.MAX_STEPS_PER_TICK else ui.INK)
        self.bar_r.set(rate / wf.MAX_STEPS_PER_TICK)

        if self.link.is_open and self.link.status.mode == 3 and not self.sweep:
            self.link.sine(hz, amp)

    def _sine_toggle(self):
        if self.link.is_open and self.link.status.mode == 3:
            self._sine_stop()
        else:
            self._sine_start()

    def _sine_start(self):
        if not self._need():
            return
        hz, amp = self._slider_to_hz(self.v_hz.get()), self.v_amp.get()
        self.link.sine(hz, amp)
        self.plot.set_data(wf.sine_preview(hz, amp,
                                           min(2.0, max(0.4, 4 / max(hz, .5)))))
        self._plot_caption("sinüs %.4g Hz" % hz)
        self.btn_sine.config(text="Sinüsü durdur")
        self._run_t0 = time.time()
        self._run_kind, self._run_dur = "Sinüs", None
        self.kv_run.set("state", "SİNÜS", ui.OKC)
        self._log("sinüs %.4g Hz · ±%.2f mm · %.1f adım/ms"
                  % (hz, amp, sine_rate(hz, amp)))

    def _sine_stop(self):
        self._sweep_end()
        self.btn_sine.config(text="Sinüs")
        if self.link.is_open:
            self.link.sine_stop()
        self._finish_run("Sinüs")

    # ================================================== süpürme
    def _sweep_toggle(self):
        if self.sweep:
            self._sweep_end()
            if self.link.is_open:
                self.link.sine_stop()
            self._finish_run("Süpürme")
            return
        if not self._need():
            return
        try:
            f1, f2, dur = (float(self.e_f1.get()), float(self.e_f2.get()),
                           float(self.e_dur.get()))
        except ValueError:
            return messagebox.showwarning("Süpürme", "Sayı girin.")
        if f1 <= 0 or f2 <= f1 or dur < 5:
            return messagebox.showwarning("Süpürme",
                                          "0 < f1 < f2 ve süre ≥ 5 s olmalı.")
        self.sweep = {"f1": f1, "f2": f2, "dur": dur, "t0": time.time(),
                      "amp0": self.v_amp.get()}
        self.btn_sweep.config(text="Süpürmeyi durdur")
        self._run_t0, self._run_kind, self._run_dur = time.time(), "Süpürme", dur
        self.kv_run.set("state", "SÜPÜRME", ui.OKC)
        self._log("süpürme %.4g → %.4g Hz, %.0f s" % (f1, f2, dur))
        self._sweep_tick()

    def _sweep_tick(self):
        if not self.sweep:
            return
        s = self.sweep
        u = (time.time() - s["t0"]) / s["dur"]
        if u >= 1.0 or not self.link.is_open:
            self._log("süpürme bitti")
            self._sweep_end()
            if self.link.is_open:
                self.link.sine_stop()
            self._finish_run("Süpürme")
            return
        # logaritmik: her onda kuşağa eşit süre. Doğrusal süpürmede zamanın
        # neredeyse tamamı yüksek frekanslarda geçer, düşük uç hiç örneklenmez.
        hz = s["f1"] * (s["f2"] / s["f1"]) ** u
        amp = min(s["amp0"], safe_amp(hz))
        self.link.sine(hz, amp)
        self.v_hz.set(self._hz_to_slider(hz))
        self.v_amp.set(round(amp, 2))
        self.lb_hz.config(text="%.4g" % hz)
        self.lb_amp.config(text="%.2f" % amp)
        rate = sine_rate(hz, amp)
        self.lb_r.config(text="%.1f" % rate)
        self.bar_r.set(rate / wf.MAX_STEPS_PER_TICK)
        self._plot_caption("süpürme %.4g Hz · ±%.2f mm" % (hz, amp))
        self._sweep_id = self.after(200, self._sweep_tick)

    def _sweep_end(self):
        if self._sweep_id:
            self.after_cancel(self._sweep_id)
            self._sweep_id = None
        self.sweep = None
        self.btn_sweep.config(text="Süpür")

    # ================================================== CSV
    def _pick_csv(self):
        path = filedialog.askopenfilename(
            title="Dalga formu CSV",
            filetypes=[("CSV / metin", "*.csv *.txt *.tsv *.dat"), ("hepsi", "*.*")])
        if not path:
            return
        self.csv_path = path
        self.lb_file.config(text=os.path.basename(path), fg=ui.INK)
        try:
            names, _ = wf.sniff_columns(path)
        except Exception as exc:
            self._log("kolon okunamadı: %s" % exc, "hata")
            return
        # Kolonlar numarayla değil ADIYLA seçiliyor: yanlış kolonu seçmek en
        # sık yapılan hata ve tek belirtisi grafiğin tuhaf görünmesi.
        self._csv_cols = names
        self._fill_choice(self.v_tcol, ["yok"] + names,
                          names[0] if names else "yok")
        self._fill_choice(self.v_vcol, names,
                          names[1] if len(names) > 1 else (names[0] if names else "—"))
        self._log("%s · %d kolon: %s" % (os.path.basename(path), len(names),
                                          ", ".join(names[:6])))

    def _fill_choice(self, var, values, default):
        w = self.pg_csv_widgets[id(var)]
        m = w["menu"]
        m.delete(0, "end")
        for v in values:
            m.add_command(label=v, command=lambda x=v, vr=var: vr.set(x))
        var.set(default)

    def _prepare(self):
        if not self.csv_path:
            return messagebox.showwarning("CSV", "Önce bir dosya seçin.")
        cols = getattr(self, "_csv_cols", [])
        try:
            tname = self.v_tcol.get()
            tcol = cols.index(tname) if tname in cols else None
            vcol = cols.index(self.v_vcol.get()) if self.v_vcol.get() in cols else 0
            w = wf.build(self.csv_path, col_value=vcol, col_time=tcol,
                         fs_in=float(self.e_fs.get()) if tcol is None else None,
                         units=self.v_unit.get(),
                         gain=float(self.e_gain.get()),
                         limit_mm=min(abs(float(self.e_lo.get())),
                                      abs(float(self.e_hi.get()))))
        except Exception as exc:
            self._log("hazırlanamadı: %s" % exc, "hata")
            return messagebox.showerror("Hazırlanamadı", str(exc))

        self.wave = w
        self.plot.set_data(w.mm, wf.TICK_HZ)
        self._plot_caption(os.path.basename(self.csv_path))
        self._show_checks(w)
        self.btn_play.config(state=("normal" if w.ok else "disabled"))
        if w.ok:
            self._log("güvenlik kontrolleri geçti, oynatma kullanılabilir")
        else:
            self._log("güvenlik kontrolleri GEÇMEDİ — oynatma kapalı", "uyarı")
        self._log("hazır: %d örnek · %.1f s · kaynak %.0f Hz · tepe ±%.2f mm"
                  % (len(w.steps), w.duration_s, w.fs_in, w.peak_mm))

    def _plot_caption(self, prefix=""):
        st = self.plot.stats()
        if not st:
            self.lb_plot.config(text=prefix)
            return
        mn, mx, rms, dur = st
        self.lb_plot.config(text="%s   min %.3f   maks %.3f   RMS %.3f mm   %.1f s"
                                 % (prefix, mn, mx, rms, dur))

    def _show_checks(self, w):
        for x in self.f_checks.winfo_children():
            x.destroy()
        for ch in w.checks:
            row = tk.Frame(self.f_checks, bg=ui.CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text="✓" if ch.ok else "✕", bg=ui.CARD, width=2,
                     fg=(ui.OKC if ch.ok else ui.BADC),
                     font=("Menlo", 10, "bold")).pack(side="left")
            tk.Label(row, text=ch.name, bg=ui.CARD, fg=ui.INK, font=ui.UI_S,
                     width=6, anchor="w").pack(side="left")
            tk.Label(row, text=ch.detail, bg=ui.CARD, fg=ui.INK_3,
                     font=ui.MONO_XS, anchor="w", justify="left",
                     wraplength=190).pack(side="left", fill="x")

    def _play(self):
        if not self._need() or self.wave is None:
            return
        if not self.wave.ok:
            return messagebox.showwarning("Kontroller geçmedi",
                                          "Kırmızı satırlar düzelmeden oynatılmaz.")
        self._sweep_end()
        self._run_t0 = time.time()
        self._run_kind = "Veri oynatma"
        self._run_dur = self.wave.duration_s
        self.kv_run.set("state", "OYNATILIYOR", ui.OKC)
        self._log("oynatma başladı: %.1f s" % self.wave.duration_s)
        self.link.start_stream([int(v) for v in self.wave.steps],
                               done_cb=lambda clean: self.q.put(("done", clean)))

    # ================================================== koşu kaydı
    def _finish_run(self, kind):
        if not self._run_kind:
            return
        st = self.link.status
        dur = time.time() - self._run_t0
        clean = st.under == 0 and st.clip == 0
        self._run_no += 1
        rec = dict(n=self._run_no, kind=kind, dur=dur, under=st.under,
                   clip=st.clip, ok=clean)
        self.runs.append(rec)
        self.table.add((rec["n"], kind, _hms(dur), st.under, st.clip,
                        "✓" if clean else "✕"),
                       ui.INK if clean else ui.BADC)
        self._run_kind = None
        self.kv_run.set("state", "HAZIR", ui.INK)
        self.kv_run.set("elapsed", "—")
        self.kv_run.set("left", "—")
        self.kv_run.set("prog", "—")
        self.bar_run.set(0)
        return clean

    def _export_runs(self):
        if not self.runs:
            return messagebox.showinfo("Kayıt yok", "Henüz koşu kaydı yok.")
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="kosu_kayitlari.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="") as fh:
            fh.write("no,tur,sure_s,underrun,kirpma,gecerli\n")
            for r in self.runs:
                fh.write("%d,%s,%.2f,%d,%d,%s\n" % (r["n"], r["kind"], r["dur"],
                                                     r["under"], r["clip"],
                                                     "evet" if r["ok"] else "hayir"))
        self._log("koşu kayıtları yazıldı: %s" % os.path.basename(path))

    def _save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile="olay_gunlugu.txt")
        if not path:
            return
        with open(path, "w") as fh:
            fh.write(self.log.dump())
        self._log("günlük yazıldı: %s" % os.path.basename(path))

    # ================================================== kuyruk
    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self._on_status(payload)
                elif kind == "msg":
                    self._log(payload)
                elif kind == "done":
                    self._on_done(payload)
        except queue.Empty:
            pass
        self._tick_run()
        if not self._closing:
            self._pump_id = self.after(30, self._pump)

    def _on_status(self, st):
        # hız ve devir konumdan türetiliyor; kartta hız sensörü yok
        now = time.time()
        if self._last_pos is not None and now > self._last_t:
            v = (st.pos_mm - self._last_pos) / (now - self._last_t)
            self._vel = 0.6 * self._vel + 0.4 * v      # ölçüm gürültüsünü yumuşat
        self._last_pos, self._last_t = st.pos_mm, now
        rpm = abs(self._vel) / 40.0 * 60.0
        free_pct = 100.0 * st.free / 255.0
        fill_pct = 100.0 - free_pct

        self.rig.set_position(st.pos_mm)
        self.tiles["pos"].set("%+.3f" % st.pos_mm)
        self.tiles["vel"].set("%+.2f" % self._vel)
        self.tiles["mode"].set(st.mode_name.upper(),
                               fg=ui.INK if st.mode else ui.INK_3)
        self.tiles["buf"].set("%.0f" % fill_pct)

        self.kv.set("pos", "%+.3f" % st.pos_mm)
        self.kv.set("vel", "%+.2f" % self._vel)
        self.kv.set("rpm", "%.0f" % rpm)
        self.kv.set("mode", st.mode_name)
        self.kv.set("buf", "%.0f" % fill_pct)
        self.kv.set("under", str(st.under), ui.BADC if st.under else ui.INK)
        self.kv.set("clip", str(st.clip), ui.BADC if st.clip else ui.INK)
        self.bar_buf.set(1.35 * fill_pct / 100)

        self.kv_motor.set("rpm", "%.0f" % rpm)
        self.kv_motor.set("dir", "—" if abs(self._vel) < 0.05
                          else ("saat yönü" if self._vel > 0 else "ters"))
        self.kv_carr.set("pos", "%+.3f" % st.pos_mm)
        self.kv_carr.set("vel", "%+.2f" % self._vel)

        if self.link.streaming:
            sent, total = self.link.stream_progress
            if total:
                self.plot.set_cursor(min(1.0, sent / total))

    def _tick_run(self):
        """Geçen ve kalan süre — koşu sürerken."""
        if not self._run_kind:
            return
        el = time.time() - self._run_t0
        self.kv_run.set("elapsed", _hms(el))
        if self._run_dur:
            left = max(0.0, self._run_dur - el)
            self.kv_run.set("left", _hms(left))
            frac = min(1.0, el / self._run_dur)
            self.kv_run.set("prog", "%.0f" % (frac * 100))
            self.bar_run.set(1.35 * frac)
        else:
            self.kv_run.set("left", "—")
            self.kv_run.set("prog", "—")

    def _on_done(self, clean):
        self.plot.set_cursor(None)
        st = self.link.status
        self._finish_run("Veri oynatma")
        if clean:
            self._log("koşu TEMİZ — underrun 0, kırpma 0")
        else:
            self._log("koşu ŞAİBELİ — underrun %d, kırpma %d — kullanmayın"
                      % (st.under, st.clip), "hata")
            messagebox.showwarning(
                "Koşu şaibeli",
                "Underrun %d, kırpma %d.\n\n"
                "Underrun: bilgisayar veriyi yetiştiremedi, tabla dalga formunun "
                "ortasında bir süre durdu.\nKırpma: hedef, sınırın ya da hız "
                "tavanının dışına çıktı.\n\nBu koşuyu analize sokmayın."
                % (st.under, st.clip))

    def _log(self, msg, level="bilgi"):
        self.log.add(msg, level, time.strftime("%H:%M:%S"))

    # ================================================== muhtelif
    def _toggle(self):
        self.rig.show_printer = self.v_printer.get()
        self.rig.show_adxl = self.v_adxl.get()
        self.rig.redraw()

    def _need(self):
        if not self.link.is_open:
            messagebox.showwarning("Bağlı değil", "Önce karta bağlanın.")
            return False
        return True

    def _estop(self):
        self._sweep_end()
        self.btn_sine.config(text="Sinüs")
        if self.link.is_open:
            self.link.estop()
            self._log("ACİL DUR", "uyarı")
        if self._run_kind:
            self._finish_run(self._run_kind)
        self.plot.set_cursor(None)

    def _on_close(self):
        """Bekleyen after() geri çağrılarını iptal et, sonra kapan. Edilmezse
        pencere yok edildikten sonra zamanlayıcı bir kez daha ateşleniyor ve Tk
        `invalid command name` diye bağırıyor."""
        self._closing = True
        for aid in (self._pump_id, self._sweep_id, self._jog_stop_id):
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
        try:
            if self.link.is_open:
                self.link.estop()
        finally:
            self.link.close()
            self.destroy()


def _hms(sec):
    sec = max(0, int(round(sec)))
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


if __name__ == "__main__":
    App().mainloop()
