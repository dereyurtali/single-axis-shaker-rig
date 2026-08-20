"""Arayüzün görsel dili — ölçüm laboratuvarı yazılımı.

Referans: Zeiss ZEN / CALYPSO gibi cihaz yazılımları. O arayüzlerin ortak
mantığı şu:

    ARAYÜZ AÇIK VE SESSİZDİR, VERİ KOYU VE PARLAKTIR.

Çerçeve — paneller, etiketler, düğmeler — açık nötr gri üstünde ince çizgilerle
ayrılır ve hiç dikkat çekmez. Tek koyu bölge, ölçümün kendisinin göründüğü
görüntü alanıdır. Bakan kişinin gözü hiçbir zaman "acaba nereye bakmalıyım"
diye dolaşmaz: koyu olan yer veridir.

Baştan sona koyu bir arayüzde bu ayrım kaybolur; kumanda ile ölçüm aynı
düzlemde durur ve ikisi de eşit derecede bağırır.

İkinci kural: renk bilgi taşır, süs değildir.

    mavi      etkin denetim, seçim
    kehribar  hareket   — konum, kasnak, taşıyıcı
    camgöbeği ölçüm     — tabla, ivmeölçer, dalga formu
    kırmızı   arıza     — sadece gerçekten bozukken

Sayılar her yerde sabit genişlikli ve sağa hizalı. Değişen bir sayı, basamak
sayısı değiştiğinde sıçramamalı; laboratuvarda sayıya bakılır, sayının yerine
değil.
"""

from __future__ import annotations

import tkinter as tk

# ------------------------------------------------------------ arayüz (açık)
BG        = "#e8eaec"      # uygulama zemini
CARD      = "#f7f8f9"      # panel yüzeyi
CARD_HEAD = "#eef0f2"      # panel başlığı
FIELD     = "#ffffff"      # giriş alanı
RULE      = "#ccd1d6"      # panel kenarı
RULE_S    = "#dfe3e6"      # iç ayraç
HOVER     = "#e2e6ea"

INK       = "#1b2227"      # birincil yazı
INK_2     = "#586167"      # ikincil
INK_3     = "#8b949a"      # üçüncül / birim
DISABLED  = "#69737a"      # devre dışı yazı — sönük ama okunur

BLUE      = "#1a6cae"      # etkin denetim
BLUE_DK   = "#12507f"
BLUE_LT   = "#dceaf5"

OKC       = "#1f7a45"
BADC      = "#b3271c"
WARNC     = "#8a6410"

# ------------------------------------------------------ görüntü alanı (açık)
# Teknik çizim mantığı: beyaz kâğıt, ince çizgi, taralı kesit. Metroloji
# yazılımlarında (CALYPSO gibi) parça görünümü böyledir; koyu zemin mikroskop
# görüntüsünün mantığıdır ve burada ölçtüğümüz şey bir görüntü değil, bir
# mekanizma. Ayrıca arayüzün geri kalanı açıkken tek bir koyu dikdörtgen,
# ekranda sebepsiz bir delik gibi duruyordu.
VIEW      = "#ffffff"      # kâğıt
VIEW_GRID = "#eaeef1"      # ızgara
VIEW_AXIS = "#c3cace"      # eksen / zemin çizgisi
VIEW_INK  = "#414b51"      # alan üstü yazı
VIEW_INK2 = "#828c92"

MOTION    = "#b0631a"      # hareket
MEAS      = "#12788f"    # ölçüm
STRUCT    = "#d3dade"      # sabit yapı dolgusu
STRUCT_2  = "#e7ebee"      # ikincil dolgu
STRUCT_LN = "#78848a"      # yapı kenarı — ince çizgi, 3:1 altına inmemeli
VIEW_OK   = "#1f7a45"
VIEW_BAD  = "#b3271c"
VIEW_WARN = "#96702a"

# eski adlarla uyum
PANEL, PANEL_2 = CARD, "#e9ecef"
ACC, DISP = BLUE, "#0f6b84"

# ------------------------------------------------------------------- yazı
UI      = ("Helvetica Neue", 12)
UI_S    = ("Helvetica Neue", 11)
UI_B    = ("Helvetica Neue", 11, "bold")
LEGEND  = ("Helvetica Neue", 10, "bold")
LABEL   = ("Helvetica Neue", 9, "bold")
MONO    = ("Menlo", 11)
MONO_S  = ("Menlo", 10)
MONO_XS = ("Menlo", 9)
NUM     = ("Menlo", 14)
NUM_L   = ("Menlo", 19)


# ======================================================================
def card(parent, title, hint=""):
    """Başlıklı panel: ince kenar, açık gri başlık şeridi."""
    box = tk.Frame(parent, bg=CARD, highlightbackground=RULE,
                   highlightthickness=1, bd=0)
    box.pack(fill="x", pady=(0, 8))

    head = tk.Frame(box, bg=CARD_HEAD)
    head.pack(fill="x")
    tk.Label(head, text=title, bg=CARD_HEAD, fg=INK, font=LEGEND,
             anchor="w").pack(side="left", padx=12, pady=6)
    if hint:
        tk.Label(head, text=hint, bg=CARD_HEAD, fg=INK_3, font=MONO_XS,
                 anchor="e").pack(side="right", padx=12)
    tk.Frame(box, bg=RULE_S, height=1).pack(fill="x")

    inner = tk.Frame(box, bg=CARD)
    inner.pack(fill="x", padx=12, pady=(10, 12))
    return inner


def label(parent, text, fg=INK_2, font=UI_S, **kw):
    return tk.Label(parent, text=text, bg=CARD, fg=fg, font=font, **kw)


def entry(parent, value="", width=7):
    """Sayı alanı: sağa hizalı, sabit genişlikli."""
    e = tk.Entry(parent, width=width, font=MONO_S, bg=FIELD, fg=INK,
                 insertbackground=BLUE, relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=RULE,
                 highlightcolor=BLUE, justify="right")  # odak rengi mavi
    e.insert(0, value)
    return e


class Btn(tk.Frame):
    """Düğme — tk.Button yerine, kenarlığı elle çizilen bir Label.

    macOS'ta Tk'nin yerel düğmesi `bg` ayarını yok sayıyor: arka planı sistemin
    açık gri düğmesi olarak çiziyor ama `fg` ne verdiyseniz onu kullanıyor.
    Sonuç, açık zeminde beyaz yazı — yani okunmayan bir düğme. Etiket tabanlı
    düğmede iki rengi de biz veriyoruz, dolayısıyla kontrast garanti.

    Kenarlık neden `highlightthickness` ile çizilmiyor: Aqua'da odak halkası
    bileşenin İÇİNE, bir piksel içeriden çiziliyor ve verdiğimiz
    `highlightbackground`/`highlightcolor` değerleri yok sayılıp sistem rengiyle
    — yani koyu/siyah — boyanıyor. Düğmenin renkli zemininde bu, "içeride duran
    siyah bir çerçeve" olarak görünüyordu. Seçenek değerlerini düzeltmek işe
    yaramaz (test_layout.py hepsini doğru okuyor, ekranda yine siyah çıkıyor);
    tek güvenilir yol halkayı hiç kullanmamak. Burada dış Frame'in zemini
    kenarlık rengi, iç Label 1 piksel boşlukla onun üstüne oturuyor — Frame'in
    `bg`'si her zaman ne dersek o.

    tk.Button'ın kullandığımız kadarını taklit ediyor: text, state, command.
    """

    KINDS = {
        "normal":  (FIELD, INK,       RULE,    HOVER),
        "primary": (BLUE,  "#ffffff", BLUE_DK, BLUE_DK),
        "danger":  ("#b3271c", "#ffffff", "#8d1e15", "#8d1e15"),
    }
    EDGE = 1                      # kenarlık kalınlığı (piksel)

    def __init__(self, master, text, command=None, kind="normal", width=None,
                 padx=14, pady=7, font=None, state="normal", **kw):
        """`width` KARAKTER değil piksel olarak yorumlanıyor.

        Tk'de Label'ın `width` seçeneği karakter sayısıdır ve genişliği '0'
        karakterinin enine göre hesaplar. Helvetica gibi orantılı bir yazıda
        gerçek harfler bundan geniş olduğu için "Bağlan" yazısı 7 karakterlik
        kutuya sığmıyor ve kırpılıyordu. Burada istenen en az piksel genişliği
        yazı tipiyle ölçülüp dolguya çevriliyor; metin her zaman sığıyor.
        """
        self.kind = kind
        self.command = command
        self._state = state
        bg, fg, edge, hover = self.KINDS[kind]
        self.hover_bg = hover
        fnt = font or (UI_B if kind != "normal" else UI_S)
        super().__init__(master, bg=edge, bd=0, highlightthickness=0)
        opts = dict(text=text, bg=bg, fg=fg, font=fnt, padx=padx, pady=pady,
                    bd=0, highlightthickness=0, takefocus=0, anchor="center")
        opts.update(kw)
        self.lb = tk.Label(self, **opts)
        self.lb.pack(fill="both", expand=True,
                     padx=self.EDGE, pady=self.EDGE)
        # `width` bilerek yok sayılıyor. Her düğmeye metnine göre farklı dolgu
        # vermek (13'ten 31 piksele) düğmeleri düzensiz gösteriyordu; dolgu
        # sabit, genişliği metin belirliyor.
        for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave),
                        ("<Button-1>", self._press),
                        ("<ButtonRelease-1>", self._release)):
            self.lb.bind(seq, fn)
        self._apply()

    # ---- görünüm ----
    def _apply(self):
        bg, fg, edge, _ = self.KINDS[self.kind]
        if self._state == "disabled":
            # Zemin beyaz kalıyor, sadece yazı sönüyor. CARD_HEAD verildiğinde
            # araç çubuğunun zeminiyle birebir aynı renk oluyor: düğme
            # kayboluyor, yerinde havada duran bir yazı kalıyordu.
            # Yazı için INK_3 de 2.7:1'de okunmuyordu; DISABLED 4.2:1 veriyor.
            self.lb.config(bg=FIELD, fg=DISABLED)
            super().config(bg=RULE)
        else:
            self.lb.config(bg=bg, fg=fg)
            super().config(bg=edge)

    def _enter(self, _=None):
        if self._state != "disabled":
            self.lb.config(bg=self.hover_bg,
                           fg="#ffffff" if self.kind != "normal" else INK)

    def _leave(self, _=None):
        self._apply()

    def _press(self, _=None):
        if self._state != "disabled":
            self.lb.config(bg=self.KINDS[self.kind][2],
                           fg="#ffffff" if self.kind != "normal" else INK)

    def _release(self, _=None):
        self._leave()
        if self._state != "disabled" and self.command:
            self.command()

    # ---- tk.Button uyumu ----
    # Olaylar iç Label'a bağlanmalı: dış Frame'i tamamen o kaplıyor, Frame'e
    # bağlanan bir <ButtonPress-1> hiç ateşlenmez (jog düğmeleri böyle
    # basılı-tut ile çalışıyor).
    def bind(self, *a, **kw):
        return self.lb.bind(*a, **kw)

    LABEL_OPTS = ("text", "font", "fg", "foreground", "anchor", "padx", "pady",
                  "image", "compound", "justify", "wraplength")

    def config(self, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            self._apply()
        if "command" in kw:
            self.command = kw.pop("command")
        lab = {k: kw.pop(k) for k in list(kw) if k in self.LABEL_OPTS}
        if lab:
            self.lb.config(**lab)
        if kw:
            super().config(**kw)
    configure = config

    def cget(self, key):
        if key == "state":
            return self._state
        if key in self.LABEL_OPTS:
            return self.lb.cget(key)
        return super().cget(key)

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.config(**{key: value})


def button(parent, text, cmd, kind="normal", **kw):
    return Btn(parent, text, cmd, kind, **kw)


def option(parent, var, values, width=16):
    m = tk.OptionMenu(parent, var, *values)
    m.config(bg=FIELD, fg=INK, font=MONO_S, relief="flat", bd=0,
             highlightthickness=1, highlightbackground=RULE, highlightcolor=RULE,
             activebackground=HOVER, anchor="w", width=width, pady=0, padx=8)
    m["menu"].config(bg=FIELD, fg=INK, font=MONO_S, activebackground=BLUE_LT,
                     activeforeground=INK, bd=0)
    return m


def scale(parent, frm, to, var, cmd, resolution=1.0, length=150):
    return tk.Scale(parent, from_=frm, to=to, orient="horizontal", variable=var,
                    command=cmd, resolution=resolution, showvalue=False,
                    bg=CARD, troughcolor="#dde2e6", fg=INK,
                    highlightthickness=0, bd=0, relief="flat",
                    sliderrelief="flat", activebackground=BLUE_DK,
                    sliderlength=14, width=6, length=length)


# ======================================================================
class Lamp(tk.Canvas):
    """Küçük durum noktası. Söndüğünde nötr, yandığında dolu renk."""

    def __init__(self, master, d=9, bg=CARD):
        super().__init__(master, width=d + 4, height=d + 4, bg=bg,
                         highlightthickness=0)
        self.d = d
        self.set(INK_3)

    def set(self, color):
        self.delete("all")
        d = self.d
        self.create_oval(2, 2, 2 + d, 2 + d, fill=color, outline="")


class Readout(tk.Frame):
    """Durum şeridindeki sayı: küçük etiket, sabit genişlikli değer."""

    def __init__(self, master, key, unit="", w=7, color=INK, bg=CARD):
        super().__init__(master, bg=bg)
        self.bg = bg
        top = tk.Frame(self, bg=bg)
        top.pack(anchor="w")
        self.lamp = Lamp(top, bg=bg)
        self.lamp.pack(side="left", padx=(0, 5))
        tk.Label(top, text=key, bg=bg, fg=INK_3, font=LABEL,
                 anchor="w").pack(side="left")
        row = tk.Frame(self, bg=bg)
        row.pack(anchor="w", pady=(2, 0))
        self.v = tk.Label(row, text="—", bg=bg, fg=color, font=NUM_L,
                          width=w, anchor="w")
        self.v.pack(side="left")
        if unit:
            tk.Label(row, text=unit, bg=bg, fg=INK_3,
                     font=MONO_XS).pack(side="left", pady=(6, 0))

    def set(self, text, fg=INK, lamp=None):
        self.v.config(text=text, fg=fg)
        self.lamp.set(lamp if lamp else INK_3)


class Pill(tk.Label):
    def __init__(self, master, bg=BG):
        super().__init__(master, text="bağlı değil", bg=bg, fg=INK_3,
                         font=MONO_S, padx=9, pady=3)

    def set(self, text, color=INK_3):
        self.config(text=text, fg=color)


class Bar(tk.Canvas):
    """Doluluk çubuğu: sayının yanına konur, yerine değil.

    '16 / 20 adım/ms' okunabilir bir sayıdır ama tavana ne kaldığı bakışta
    anlaşılmaz; çubuk onu veriyor."""

    def __init__(self, master, height=7, bg=CARD, **kw):
        super().__init__(master, height=height, bg="#dde2e6",
                         highlightthickness=1, highlightbackground=RULE, **kw)
        self.frac = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, frac):
        self.frac = max(0.0, min(1.35, float(frac)))
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        for f in (0.75, 1.0):
            x = w * f / 1.35
            self.create_line(x, 0, x, h, fill=RULE)
        col = OKC if self.frac <= .75 else (WARNC if self.frac <= 1 else BADC)
        self.create_rectangle(0, 0, w * self.frac / 1.35, h, fill=col,
                              outline="")


class Tabs(tk.Frame):
    """Sinüs ve CSV aynı anda kullanılmıyor: biri geçirgenlik taraması, diğeri
    kayıt oynatma. İkisini alt alta koymak sütunu ekrana sığmayacak kadar
    uzatıyordu. Bağlantı ve elle sürüş sekme dışında; onlar her kipte lazım."""

    def __init__(self, master, names):
        super().__init__(master, bg=BG)
        self.strip = tk.Frame(self, bg=BG)
        self.strip.pack(fill="x")
        self.pages, self.buttons, self.marks = {}, {}, {}
        for n in names:
            holder = tk.Frame(self.strip, bg=BG)
            holder.pack(side="left")
            b = tk.Label(holder, text=n, bg=BG, fg=INK_3, font=LEGEND,
                         padx=14, pady=7)
            b.pack()
            mark = tk.Frame(holder, bg=BG, height=2)
            mark.pack(fill="x")
            b.bind("<Button-1>", lambda e, k=n: self.show(k))
            self.buttons[n], self.marks[n] = b, mark
            self.pages[n] = tk.Frame(self, bg=BG)
        tk.Frame(self.strip, bg=RULE, height=1).pack(fill="x", side="bottom")
        self.holder = tk.Frame(self, bg=BG)
        self.holder.pack(fill="both", expand=True, pady=(9, 0))
        self.current = names[0]
        self.show(names[0])

    def page(self, name):
        return self.pages[name]

    def show(self, name):
        """Görünmeyen sayfa yerleşimden tamamen çıkarılıyor. `lift()` yetmiyor:
        gizli sayfa hâlâ yerleştirilmiş sayıldığı için sütunun istediği yükseklik
        iki sayfanın büyüğü kadar kalıyor ve kısa sayfadayken boşuna kaydırma
        çıkıyor."""
        self.current = name
        for n, b in self.buttons.items():
            on = (n == name)
            b.config(fg=BLUE if on else INK_3)
            self.marks[n].config(bg=BLUE if on else BG)
            if on:
                self.pages[n].pack(in_=self.holder, fill="both", expand=True)
            else:
                self.pages[n].pack_forget()


class ScrollColumn(tk.Frame):
    """Sabit genişlikte, dikeyde kaydırılabilir sütun.

    Kartlar sabit bir çerçeveye doğrudan yerleştirilirse, pencere kısaldığında en
    alttaki kart ezilir: Tk onu silmiyor, yüksekliğini 1 piksele indiriyor.
    Ekranda düğme hâlâ duruyor gibi görünür ama tıklanamaz."""

    def __init__(self, master, width=352, **kw):
        super().__init__(master, bg=BG, width=width, **kw)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0,
                                width=width - 8)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rail = tk.Canvas(self, bg=BG, width=6, highlightthickness=0)
        self.rail.pack(side="right", fill="y")

        self.body = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.body, anchor="nw",
                                  width=width - 12)
        self.body.bind("<Configure>", self._resize)
        self.canvas.bind("<Configure>", self._resize)
        for w in (self.canvas, self.body):
            w.bind("<MouseWheel>", self._wheel)
        self.bind_all("<MouseWheel>", self._wheel_global, add="+")

    def _resize(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._rail()

    def _wheel(self, e):
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        self._rail()

    def _wheel_global(self, e):
        x, y = self.winfo_rootx(), self.winfo_rooty()
        if x <= e.x_root <= x + self.winfo_width() and \
           y <= e.y_root <= y + self.winfo_height():
            self._wheel(e)

    def _rail(self):
        self.rail.delete("all")
        h, need = self.winfo_height(), self.body.winfo_reqheight()
        if need <= h or h < 10:
            return
        lo, hi = self.canvas.yview()
        self.rail.create_rectangle(1, lo * h, 5, hi * h, fill=RULE, outline="")


def viewport(parent):
    """Koyu ölçüm alanı: ince kenar, açık zeminden net ayrılır."""
    shell = tk.Frame(parent, bg=RULE, highlightthickness=0)
    return shell


# ======================================================================
#  Profesyonel ölçüm yazılımının yapı taşları
# ======================================================================
class Toolbar(tk.Frame):
    """Üst araç çubuğu: birincil eylemler, işlevine göre kümelenmiş.

    Şeridin yüksekliği sabit ve içindeki her öğe dikeyde onu dolduruyor. Serbest
    bırakıldığında açılır liste 22, düğmeler 27, DUR 29 piksel geliyordu ve
    hepsi farklı y'de oturuyordu — şerit gözle bakınca kaymış görünüyordu.
    Ölçü aleti arayüzünde bu tür bir kayma, yazılımın geri kalanına duyulan
    güveni de düşürüyor.
    """

    H = 27

    def __init__(self, master):
        super().__init__(master, bg=CARD_HEAD, highlightbackground=RULE,
                         highlightthickness=1)
        self.row = tk.Frame(self, bg=CARD_HEAD, height=self.H)
        self.row.pack(fill="x", padx=9, pady=5)
        self.row.pack_propagate(False)

    def add(self, text, cmd, kind="normal", width=None, **kw):
        # padx her düğmede aynı; simgeler biraz daha geniş dursun diye tek
        # istisna, metni tek karakter olanlar.
        # Acil dur ve birincil eylem daha geniş: şeritte gözle bulunmaları
        # gereken iki düğme bunlar.
        pad = 15 if len(text) <= 2 else (26 if kind != "normal" else 13)
        b = Btn(self.row, text, cmd, kind, padx=pad, pady=0, **kw)
        b.pack(side="left", padx=(0, 5), fill="y")
        return b

    def sep(self):
        tk.Frame(self.row, bg=RULE, width=1).pack(side="left", fill="y",
                                                  padx=8, pady=3)

    def spacer(self):
        tk.Frame(self.row, bg=CARD_HEAD).pack(side="left", fill="x", expand=True)

    def note(self, text):
        lb = tk.Label(self.row, text=text, bg=CARD_HEAD, fg=INK_3, font=MONO_XS)
        lb.pack(side="left", padx=(2, 6))
        return lb


class PropertyGrid(tk.Frame):
    """Hizalanmış parametre ızgarası — etiket | değer | birim.

    Bu, arayüzü 'uygulama' değil 'cihaz yazılımı' yapan asıl unsur. Serbest
    yerleştirilmiş form alanlarında her satırın değeri farklı bir sütunda başlar;
    göz otuz parametreyi tek tek okumak zorunda kalır. Sabit sütunlarda değerler
    alt alta dizilir ve yanlış girilmiş bir sayı hizadan taşarak kendini belli
    eder.

    Birimler ayrı sütunda: sayı ile birimi aynı hücreye koymak sayıların
    hizasını bozuyor.
    """

    LBL_W, UNIT_W = 132, 44

    def __init__(self, master, **kw):
        super().__init__(master, bg=CARD, **kw)
        self.columnconfigure(1, weight=1)
        self._row = 0
        self.widgets: dict[str, object] = {}
        self.vars: dict[str, object] = {}

    # ---- yapı ----
    def section(self, title):
        f = tk.Frame(self, bg=CARD_HEAD, highlightbackground=RULE_S,
                     highlightthickness=1)
        f.grid(row=self._row, column=0, columnspan=3, sticky="ew",
               pady=(10 if self._row else 0, 0))
        tk.Label(f, text=title, bg=CARD_HEAD, fg=INK, font=LABEL,
                 anchor="w").pack(fill="x", padx=9, pady=4)
        self._row += 1

    def _cells(self, label):
        r = self._row
        tk.Label(self, text=label, bg=CARD, fg=INK_2, font=UI_S, anchor="w",
                 width=13).grid(row=r, column=0, sticky="w", padx=(9, 6), pady=2)
        self._row += 1
        return r

    def _unit(self, r, unit):
        tk.Label(self, text=unit, bg=CARD, fg=INK_3, font=MONO_XS, anchor="w",
                 width=5).grid(row=r, column=2, sticky="w", padx=(6, 9))

    # ---- satır tipleri ----
    def entry(self, key, label, value="", unit="", width=9):
        r = self._cells(label)
        e = entry(self, str(value), width)
        e.grid(row=r, column=1, sticky="e")
        self._unit(r, unit)
        self.widgets[key] = e
        return e

    def pair(self, key_a, key_b, label, a="", b="", unit="", width=6):
        """İki değerli satır — sınır min/max, süpürme f1/f2 gibi."""
        r = self._cells(label)
        box = tk.Frame(self, bg=CARD)
        box.grid(row=r, column=1, sticky="e")
        ea = entry(box, str(a), width); ea.pack(side="left")
        tk.Label(box, text="…", bg=CARD, fg=INK_3,
                 font=MONO_XS).pack(side="left", padx=4)
        eb = entry(box, str(b), width); eb.pack(side="left")
        self._unit(r, unit)
        self.widgets[key_a], self.widgets[key_b] = ea, eb
        return ea, eb

    def slider(self, key, label, frm, to, value, unit="", cmd=None,
               resolution=1.0, fmt="%.4g"):
        r = self._cells(label)
        box = tk.Frame(self, bg=CARD)
        box.grid(row=r, column=1, sticky="ew")
        var = tk.DoubleVar(value=value)
        val = tk.Label(box, text=fmt % value, bg=CARD, fg=INK, font=MONO_S,
                       width=8, anchor="e")
        val.pack(side="right")
        sc = scale(box, frm, to, var, cmd, resolution, length=118)
        sc.pack(side="right", fill="x", expand=True, padx=(0, 6))
        self._unit(r, unit)
        self.widgets[key] = val
        self.vars[key] = var
        return var, val

    def choice(self, key, label, values, value=None, width=7):
        r = self._cells(label)
        var = tk.StringVar(value=value or values[0])
        om = option(self, var, values, width=width)
        om.grid(row=r, column=1, sticky="e")
        self.widgets[key], self.vars[key] = om, var
        return var

    def spin(self, key, label, lo, hi, value, unit=""):
        r = self._cells(label)
        sp = tk.Spinbox(self, from_=lo, to=hi, width=9, font=MONO_S, bg=FIELD,
                        fg=INK, relief="flat", bd=0, justify="right",
                        highlightthickness=1, highlightbackground=RULE,
                        insertbackground=BLUE, buttonbackground=CARD_HEAD)
        sp.delete(0, "end"); sp.insert(0, str(value))
        sp.grid(row=r, column=1, sticky="e")
        self._unit(r, unit)
        self.widgets[key] = sp
        return sp

    def readonly(self, key, label, unit="", value="—", width=11):
        """Hesaplanan değer: girilemez, sönük yazı."""
        r = self._cells(label)
        lb = tk.Label(self, text=value, bg=CARD, fg=INK, font=MONO_S,
                      anchor="e", width=width)
        lb.grid(row=r, column=1, sticky="e")
        self._unit(r, unit)
        self.widgets[key] = lb
        return lb

    def bar(self, key, label, unit=""):
        r = self._cells(label)
        box = tk.Frame(self, bg=CARD)
        box.grid(row=r, column=1, sticky="ew")
        lb = tk.Label(box, text="—", bg=CARD, fg=INK, font=MONO_S, width=8,
                      anchor="e")
        lb.pack(side="right")
        b = Bar(box, height=7)
        b.pack(side="right", fill="x", expand=True, padx=(0, 6), pady=4)
        self._unit(r, unit)
        self.widgets[key] = lb
        self.widgets[key + ".bar"] = b
        return b, lb

    def widget_row(self, w, pady=(6, 0)):
        w.grid(row=self._row, column=0, columnspan=3, sticky="ew",
               padx=9, pady=pady)
        self._row += 1

    # ---- erişim ----
    def get(self, key):
        w = self.widgets[key]
        return w.get() if hasattr(w, "get") else w["text"]

    def set(self, key, text, fg=None):
        w = self.widgets[key]
        if hasattr(w, "delete") and not isinstance(w, tk.Label):
            w.delete(0, "end"); w.insert(0, text)
        else:
            w.config(text=text, **({"fg": fg} if fg else {}))


class StatusBar(tk.Frame):
    """Pencerenin en altında ince, bölmeli durum şeridi.

    Sürekli değişen sayılar buraya toplanıyor. Ana alanda büyük kutular hâlinde
    durduklarında hem yer yiyorlar hem de gözü sürekli çekiyorlardı; oysa bunlar
    arada bir bakılan, sorun çıkınca aranan değerler.
    """

    def __init__(self, master):
        super().__init__(master, bg=CARD_HEAD, highlightbackground=RULE,
                         highlightthickness=1)
        self.cells: dict[str, tk.Label] = {}
        self.lamps: dict[str, Lamp] = {}
        self._first = True

    def cell(self, key, label, width=12, lamp=False):
        if not self._first:
            tk.Frame(self, bg=RULE, width=1).pack(side="left", fill="y", pady=3)
        self._first = False
        box = tk.Frame(self, bg=CARD_HEAD)
        box.pack(side="left", padx=10, pady=4)
        if lamp:
            lp = Lamp(box, d=8, bg=CARD_HEAD)
            lp.pack(side="left", padx=(0, 5))
            self.lamps[key] = lp
        tk.Label(box, text=label, bg=CARD_HEAD, fg=INK_3,
                 font=LABEL).pack(side="left", padx=(0, 6))
        v = tk.Label(box, text="—", bg=CARD_HEAD, fg=INK, font=MONO_S,
                     width=width, anchor="w")
        v.pack(side="left")
        self.cells[key] = v
        return v

    def set(self, key, text, fg=INK, lamp=None):
        if key in self.cells:
            self.cells[key].config(text=text, fg=fg)
        if lamp is not None and key in self.lamps:
            self.lamps[key].set(lamp)


class Table(tk.Frame):
    """Ölçüm kaydı tablosu — koşular, süreleri, geçerli olup olmadıkları.

    Laboratuvar yazılımı yaptığı işi kaydeder. Günlük satırları akıp gidiyor;
    hangi koşunun temiz hangisinin şaibeli olduğu sonradan aranarak bulunmamalı.
    """

    def __init__(self, master, columns, widths):
        super().__init__(master, bg=CARD)
        self.columns, self.widths = columns, widths
        head = tk.Frame(self, bg=CARD_HEAD)
        head.pack(fill="x")
        for c, w in zip(columns, widths):
            tk.Label(head, text=c, bg=CARD_HEAD, fg=INK_2, font=LABEL, width=w,
                     anchor="w").pack(side="left", padx=(9, 0), pady=4)
        tk.Frame(self, bg=RULE_S, height=1).pack(fill="x")
        self.body = tk.Frame(self, bg=CARD)
        self.body.pack(fill="both", expand=True)
        self.n = 0

    def add(self, values, color=INK):
        bg = CARD if self.n % 2 == 0 else "#f1f3f4"
        row = tk.Frame(self.body, bg=bg)
        row.pack(fill="x")
        for v, w in zip(values, self.widths):
            tk.Label(row, text=str(v), bg=bg, fg=color, font=MONO_XS, width=w,
                     anchor="w").pack(side="left", padx=(9, 0), pady=2)
        self.n += 1
        return row

    def clear(self):
        for c in self.body.winfo_children():
            c.destroy()
        self.n = 0


# ======================================================================
#  Üç sütunlu düzenin parçaları
# ======================================================================
class StatTile(tk.Frame):
    """Büyük gösterge kutusu: etiket, iri sayı, birim, altında açıklama.

    Sürekli değişen az sayıda değer için. Hepsini küçük satırlara sıkıştırmak
    yerine dördünü öne çıkarmak, koşu sırasında ekrana bakış süresini kısaltıyor.
    """

    def __init__(self, master, label, unit="", sub=""):
        super().__init__(master, bg=CARD, highlightbackground=RULE,
                         highlightthickness=1)
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=13, pady=10)
        tk.Label(inner, text=label, bg=CARD, fg=INK_3, font=LABEL,
                 anchor="w").pack(anchor="w")
        row = tk.Frame(inner, bg=CARD)
        row.pack(anchor="w", pady=(4, 0))
        self.v = tk.Label(row, text="—", bg=CARD, fg=INK,
                          font=("Menlo", 21), anchor="w")
        self.v.pack(side="left")
        self.u = tk.Label(row, text=unit, bg=CARD, fg=INK_3, font=MONO_S)
        self.u.pack(side="left", padx=(4, 0), pady=(7, 0))
        self.s = tk.Label(inner, text=sub, bg=CARD, fg=INK_3, font=MONO_XS,
                          anchor="w")
        if sub:
            self.s.pack(anchor="w", pady=(3, 0))

    def set(self, value, sub=None, fg=INK):
        self.v.config(text=value, fg=fg)
        if sub is not None:
            self.s.config(text=sub)


class KeyValue(tk.Frame):
    """Etiket–değer satırlarından oluşan küçük durum bloğu."""

    def __init__(self, master, rows, width=9):
        super().__init__(master, bg=CARD)
        self.cells = {}
        for i, (key, label, unit) in enumerate(rows):
            tk.Label(self, text=label, bg=CARD, fg=INK_2, font=UI_S,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            v = tk.Label(self, text="—", bg=CARD, fg=INK, font=MONO_S,
                         width=width, anchor="e")
            v.grid(row=i, column=1, sticky="e", padx=(8, 0), pady=2)
            tk.Label(self, text=unit, bg=CARD, fg=INK_3, font=MONO_XS,
                     width=5, anchor="w").grid(row=i, column=2, sticky="w",
                                               padx=(5, 0))
            self.cells[key] = v
        self.columnconfigure(1, weight=1)

    def set(self, key, text, fg=INK):
        if key in self.cells:
            self.cells[key].config(text=text, fg=fg)


class LogView(tk.Frame):
    """Zaman | seviye | olay üçlüsüyle günlük.

    Seviye ayrı bir sütun: bir koşu bozulduğunda uyarı ve hata satırlarını
    düz metin içinde aramak zorunda kalmamak için.
    """

    LEVELS = {"bilgi": INK_3, "uyarı": WARNC, "hata": BADC}

    def __init__(self, master, height=6):
        super().__init__(master, bg=CARD)
        self.txt = tk.Text(self, height=height, bg=CARD, fg=INK_2,
                           font=MONO_XS, relief="flat", highlightthickness=0,
                           wrap="none", padx=12, pady=7, state="disabled")
        sb = tk.Scrollbar(self, command=self.txt.yview, width=11)
        self.txt.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        for name, col in self.LEVELS.items():
            self.txt.tag_config(name, foreground=col)
        self.txt.tag_config("t", foreground=INK_3)
        self.n = 0

    def add(self, msg, level="bilgi", stamp=""):
        self.txt.config(state="normal")
        self.txt.insert("end", stamp + "  ", "t")
        self.txt.insert("end", "%-6s" % level.upper(), level)
        self.txt.insert("end", "  " + msg + "\n")
        self.txt.see("end")
        self.n += 1
        if self.n > 500:
            self.txt.delete("1.0", "150.0")
            self.n -= 150
        self.txt.config(state="disabled")

    def clear(self):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")
        self.n = 0

    def dump(self):
        return self.txt.get("1.0", "end-1c")


def card_in(parent, title, hint=""):
    """`card` ile aynı, ama kendi kendine paketlenmiyor — satır içine
    yerleştirilecek kartlar için. Dönen çerçevenin `master`'ı kartın dışıdır."""
    box = tk.Frame(parent, bg=CARD, highlightbackground=RULE,
                   highlightthickness=1, bd=0)
    head = tk.Frame(box, bg=CARD_HEAD)
    head.pack(fill="x")
    tk.Label(head, text=title, bg=CARD_HEAD, fg=INK, font=LEGEND,
             anchor="w").pack(side="left", padx=12, pady=5)
    if hint:
        tk.Label(head, text=hint, bg=CARD_HEAD, fg=INK_3, font=MONO_XS
                 ).pack(side="right", padx=12)
    tk.Frame(box, bg=RULE_S, height=1).pack(fill="x")
    inner = tk.Frame(box, bg=CARD)
    inner.pack(fill="both", expand=True, padx=12, pady=(10, 12))
    return inner
