"""Yerleşim denetimi: hiçbir şey eziliyor, kırpılıyor ya da taşıyor mu.

Önceki denetim `Frame` sınıfını atlıyordu — LogView bir Frame alt sınıfı olduğu
için 1×1 piksele ezildiği hâlde testten geçmişti ve olay günlüğü ekranda hiç
görünmüyordu. Burada sınıf adına göre eleme yok; her bileşen isteği kadar yer
alıp almadığına bakılıyor.

    ./.venv/bin/python test_layout.py
"""

from __future__ import annotations

import sys
import tkinter.font as tkfont

import app as A
import ui

SIZES = ["1440x880", "1180x760", "1680x1020"]
MIN_PANEL = 40          # bir panelin altına inmemesi gereken piksel

fails = 0


def ok(c, msg, got=""):
    global fails
    if not c:
        fails += 1
    print("  %s%s%s%s" % ("ok  " if c else "FAIL", msg, "   -> " if got else "", got))


def audit(a, geom):
    a.geometry(geom)
    a.update()
    a.update_idletasks()
    problems = []

    def walk(w, depth=0):
        for ch in w.winfo_children():
            if not ch.winfo_ismapped():
                continue
            aw, ah = ch.winfo_width(), ch.winfo_height()
            rw, rh = ch.winfo_reqwidth(), ch.winfo_reqheight()
            name = ch.winfo_class()
            try:
                t = str(ch.cget("text"))[:18]
            except Exception:
                t = ""
            # Kasten 1 piksel olan ayraç çizgileri elenir: onların İSTEDİĞİ
            # boy da 1'dir. Ezilme, isteği büyük olup verileni küçük olmaktır.
            hairline = (rw <= 2 or rh <= 2)
            if not hairline and (aw <= 2 or ah <= 2):
                problems.append("YOK OLMUS  %-12s %-18s %dx%d" % (name, t, aw, ah))
            # metni kırpılmış
            elif t and name in ("Label", "Button"):
                try:
                    f = tkfont.Font(font=ch.cget("font"))
                    need = f.measure(t) + 2 * int(ch.cget("padx"))
                    if aw < need - 1:
                        problems.append("KIRPIK    %-12s %-18s %d < %d"
                                        % (name, t, aw, need))
                except Exception:
                    pass
            # istediğinden belirgin küçük kalmış panel
            elif depth <= 3 and rh > MIN_PANEL and ah < rh * 0.6:
                problems.append("EZIK      %-12s %-18s %d < %d"
                                % (name, t, ah, rh))
            walk(ch, depth + 1)

    walk(a)
    return problems


a = A.App()
for geom in SIZES:
    p = audit(a, geom)
    ok(not p, "%-10s temiz" % geom, "%d sorun" % len(p))
    for x in p[:8]:
        print("        " + x)

a.geometry("1440x880")
a.update()
a.update_idletasks()

print("\nANA BOLGELER (1440x880):")
for name, w in (("düzenek çizimi", a.rig), ("dalga formu", a.plot),
                ("koşu tablosu", a.table), ("olay günlüğü", a.log)):
    vis = w.winfo_width() > 2 and w.winfo_height() > 2
    ok(vis, "%-16s %4dx%-4d" % (name, w.winfo_width(), w.winfo_height()))

print("\nODAK HALKASI (siyah çizgi):")
bad = []


def rings(w):
    for ch in w.winfo_children():
        try:
            if int(ch.cget("highlightthickness")) > 0:
                hc = str(ch.cget("highlightcolor"))
                if "system" in hc.lower() or hc.lower() in ("black", "#000000"):
                    bad.append("%s %r" % (ch.winfo_class(), str(ch.cget("text"))[:14]))
        except Exception:
            pass
        rings(ch)


rings(a)
ok(not bad, "sistem/siyah odak rengi kullanan bileşen", "%d" % len(bad))
for x in bad[:6]:
    print("        " + x)

# Düğmelerde halkanın seçenek değeri doğru olsa bile Aqua onu yok sayıp sistem
# rengiyle çiziyordu: renkli düğmenin içinde duran siyah bir çerçeve. Kenarlık
# artık dış Frame'in zeminiyle çiziliyor; halka hiç kullanılmıyor olmalı.
print("\nDUGME KENARLIGI:")
ring = []


def btns(w):
    for ch in w.winfo_children():
        if isinstance(ch, ui.Btn):
            for x in (ch, ch.lb):
                if int(x.cget("highlightthickness")) > 0:
                    ring.append("%r" % str(ch.cget("text"))[:14])
            if str(ch.cget("bg")) != str(ch.KINDS[ch.kind][2]) and ch["state"] != "disabled":
                ring.append("kenar rengi yanlis %r" % str(ch.cget("text"))[:14])
        btns(ch)


btns(a)
ok(not ring, "düğmelerde odak halkası / yanlış kenar", "%d" % len(ring))
for x in ring[:6]:
    print("        " + x)

a.destroy()
print("\n%d SORUN" % fails if fails else "\nYERLESIM TEMIZ")
sys.exit(1 if fails else 0)
