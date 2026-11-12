#!/usr/bin/env python3
"""Генератор YouTube Shorts: «Какие бывают нейросети» (9:16, 1080x1920, 30 fps).

Запуск:
    python3 make_short.py            # полный рендер -> shorts_neural_networks.mp4
    python3 make_short.py --stills   # только контрольные кадры

Чтобы сделать другой ролик, меняйте список SCENES (текст, заголовок, цвет)
и функции-иллюстрации ILL_* ниже.
"""
import math, random, subprocess, sys, os, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import json, tempfile, shutil

CAPTION_HIGHLIGHT_WORD = False   # True — подсветка произносимого слова, False — подсветка всей фразы

VOICE_DIR = r"D:\Projects\video-generator-01\assets\voice_trimmed"
VOICE_EXT = ".wav"
SR        = 44100        # целевая частота для микса
DUCK_DB   = -7.0         # насколько тише музыка под голосом
TARGET_LUFS = -14.0
TARGET_TP   = -1.4

W, H, FPS = 1080, 1920, 30
S = 2                                   # supersampling для иллюстраций
PROJECT = Path(r"D:\Projects\video-generator-01")
OUT_DIR = str(PROJECT / "output")
FONTS   = PROJECT / "assets" / "fonts" / "otf"
F_XB = str(FONTS / "Inter-ExtraBold.otf")
F_B  = str(FONTS / "Inter-Bold.otf")
F_SB = str(FONTS / "Inter-SemiBold.otf")

# ----------------------------------------------------------------- сценарий
SCENES = [
    dict(key="intro", title="НЕЙРОСЕТИ", tag="5 главных типов за минуту", color=(34, 211, 238),
         text="Какие бывают нейросети? Разберём пять главных типов всего за минуту!"),
    dict(key="mlp", title="ПОЛНОСВЯЗНЫЕ", tag="MLP · Fully Connected", color=(77, 163, 255),
         text="Первая: полносвязная сеть. Это слои нейронов, где каждый связан с каждым. "
              "Самая простая архитектура, подходит для таблиц, оценок и прогнозов."),
    dict(key="cnn", title="СВЁРТОЧНЫЕ", tag="CNN · Convolutional", color=(46, 216, 163),
         text="Свёрточные сети умеют видеть. Они ищут на картинке линии и формы, а затем целые объекты. "
              "Распознают медицинский снимок, лица людей, помогают беспилотным авто."),
    dict(key="rnn", title="РЕКУРРЕНТНЫЕ", tag="RNN · LSTM", color=(255, 181, 71),
         text="Рекуррентные сети работают с последовательностями: речь, музыка, курсы валют. "
              "Они запоминают предыдущие шаги, но плохо справляются с длинными текстами."),
    dict(key="trf", title="ТРАНСФОРМЕРЫ", tag="Transformer · Attention", color=(255, 92, 138),
         text="Трансформеры: основа ChatGPT и Claude. Механизм внимания смотрит на все слова сразу "
              "и понимает контекст. На них построены почти все современные языковые модели."),
    dict(key="gen", title="ГЕНЕРАТИВНЫЕ", tag="GAN · Diffusion", color=(182, 109, 255),
         text="Генеративные модели, GAN и диффузия, создают новое: картинки, видео, музыку. "
              "На диффузии работают Midjourney и Stable Diffusion."),
    dict(key="outro", title="ПОДПИШИСЬ", tag="разберём каждый тип подробнее", color=(255, 216, 77),
         text="Подписывайся, дальше разберём каждый тип подробнее!"),
]
LEAD, TAIL = 0.35, 0.5          # пауза перед первой фразой / после последней, сек


# ----------------------------------------------------------------- утилиты
_fc = {}
def font(path, size):
    k = (path, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, int(size))
    return _fc[k]

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out(x): return 1 - (1 - clamp(x)) ** 3
def smooth(x): x = clamp(x); return x * x * (3 - 2 * x)
def mix(a, b, k): return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def build_timeline():
    """Тайминги сцен по длительности озвучки. Слова растягиваются пропорционально."""
    t = 0.0
    for sc in SCENES:
        sc["start"] = t
        vp = voice_path(sc["key"])
        vdur = (len(decode_audio(vp)) / SR) if os.path.exists(vp) else None

        words, cur = [], 0.0
        for tok in sc["text"].split():
            letters = len([ch for ch in tok if ch.isalnum()])
            d = 0.09 + 0.034 * letters
            words.append(dict(text=tok, start=cur, end=cur + d))
            cur += d
            if tok[-1] in ",:;":
                cur += 0.17
            elif tok[-1] in ".!?":
                cur += 0.33
        text_dur = cur

        k = (vdur / text_dur) if vdur else 1.0
        for w in words:
            w["start"] = sc["start"] + LEAD + w["start"] * k
            w["end"]   = sc["start"] + LEAD + w["end"]   * k
        sc["words"]     = words
        sc["voice_dur"] = vdur
        sc["end"]       = sc["start"] + LEAD + (vdur if vdur else text_dur) + TAIL
        t = sc["end"]
    return t

# ----------------------------------------------------------------- аудио
def decode_audio(path, sr=SR):
    """mp3/wav → (mono float32 numpy, sr)."""
    cmd = ["ffmpeg", "-v", "error", "-i", path,
           "-f", "s16le", "-acodec", "pcm_s16le",
           "-ac", "1", "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def voice_path(key):
    return os.path.join(VOICE_DIR, key + VOICE_EXT)

# ----------------------------------------------------------------- субтитры
CAPF = font(F_XB, 74)
CAP_MAXW = 860
CAP_BASE = 1388
GAP = 16                       # доп. расстояние между словами

def layout_caption(sc):
    words = sc["words"]

    def nlines(idxs):
        lines = [[]]
        for i in idxs:
            trial = " ".join(words[j]["text"] for j in lines[-1] + [i])
            if lines[-1] and CAPF.getlength(trial) > CAP_MAXW:
                lines.append([i])
            else:
                lines[-1].append(i)
        return lines

    chunks, cur = [], []
    for i, w in enumerate(words):
        test = cur + [i]
        if cur and (len(nlines(test)) > 2 or len(test) > 5):
            chunks.append(cur)
            cur = [i]
        else:
            cur = test
        if w["text"][-1] in ".,!?:;":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    out = []
    for ci, idxs in enumerate(chunks):
        lines = nlines(idxs)
        n = len(lines)
        items = []
        for li, line in enumerate(lines):
            base = CAP_BASE + (li - (n - 1) / 2) * 96
            lw = CAPF.getlength(" ".join(words[j]["text"] for j in line)) + GAP * (len(line) - 1)
            x0 = (W - lw) / 2
            for k, j in enumerate(line):
                prefix = " ".join(words[m]["text"] for m in line[:k]) + (" " if k else "")
                items.append((j, words[j]["text"], x0 + CAPF.getlength(prefix) + GAP * k, base))
        t0 = sc["start"] if ci == 0 else words[idxs[0]]["start"]
        out.append(dict(idxs=idxs, items=items, t0=t0))
    for ci in range(len(out)):
        out[ci]["t1"] = out[ci + 1]["t0"] if ci + 1 < len(out) else sc["end"]
    sc["chunks"] = out


def draw_caption(fr, sc, t):
    ch = sc["chunks"][-1]
    for c in sc["chunks"]:
        if c["t0"] <= t < c["t1"]:
            ch = c
            break

    d = ImageDraw.Draw(fr)
    col = sc["color"]
    items = ch["items"]

    if CAPTION_HIGHLIGHT_WORD:
        # --- режим «по словам» ---
        cur = ch["idxs"][0]
        for j in ch["idxs"]:
            if sc["words"][j]["start"] <= t:
                cur = j
        for j, txt, x, b in items:
            if j == cur:
                d.rounded_rectangle([x - 14, b - 66, x + CAPF.getlength(txt) + 14, b + 22],
                                    radius=18, fill=col)
        for j, txt, x, b in items:
            if j == cur:
                d.text((x, b), txt, font=CAPF, fill=(10, 12, 26), anchor="ls")
            else:
                d.text((x, b), txt, font=CAPF, fill=(255, 255, 255), anchor="ls",
                       stroke_width=8, stroke_fill=(8, 9, 20))
    else:
        # --- режим «по фразе» ---
        xs0 = min(x for _, _, x, _ in items)
        xs1 = max(x + CAPF.getlength(txt) for _, txt, x, _ in items)
        ys0 = min(b for _, _, _, b in items) - 66
        ys1 = max(b for _, _, _, b in items) + 22
        d.rounded_rectangle([xs0 - 18, ys0, xs1 + 18, ys1], radius=20, fill=col)
        for _, txt, x, b in items:
            d.text((x, b), txt, font=CAPF, fill=(10, 12, 26), anchor="ls")

# ----------------------------------------------------------------- фон и заголовок
def make_bg(color):
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    top, bot = np.array([13, 15, 34], np.float32), np.array([5, 6, 14], np.float32)
    base = np.broadcast_to(top * (1 - yy) + bot * yy, (H, W, 3)).copy()
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    g = np.clip(1 - np.sqrt(((X - 540) / 620) ** 2 + ((Y - 830) / 560) ** 2), 0, 1) ** 2
    base += g[..., None] * np.array(color, np.float32) * 0.20
    g2 = np.clip(1 - np.sqrt(((X - 540) / 700) ** 2 + ((Y - 120) / 380) ** 2), 0, 1) ** 2
    base += g2[..., None] * np.array(color, np.float32) * 0.12
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    for y in range(40, H, 64):
        for x in range(40, W, 64):
            dr.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=(40, 44, 76))
    return img


def build_title(si):
    sc = SCENES[si]
    col = sc["color"]
    L = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    cur = si - 1 if 1 <= si <= 5 else (-1 if si == 0 else 5)
    for i in range(5):
        x = W / 2 + (i - 2) * 58
        if i == cur:
            d.ellipse([x - 15, 25, x + 15, 55], fill=col)
        elif i < cur:
            d.ellipse([x - 10, 30, x + 10, 50], fill=(*col, 130))
        else:
            d.ellipse([x - 10, 30, x + 10, 50], fill=(58, 64, 100, 255))
    if 1 <= si <= 5:
        d.text((W / 2, 125), f"ТИП {si} ИЗ 5", font=font(F_B, 38), fill=col, anchor="ms")
    size = 112
    while font(F_XB, size).getlength(sc["title"]) > 940:
        size -= 4
    d.text((W / 2, 250), sc["title"], font=font(F_XB, size), fill=(255, 255, 255), anchor="ms")
    d.text((W / 2, 312), sc["tag"], font=font(F_SB, 42), fill=(170, 178, 210), anchor="ms")
    return L


# ----------------------------------------------------------------- холст иллюстраций
CW, CH, CY = 900, 740, 370
ILL_POS = (90, 462)

class Cv:
    def __init__(s):
        s.img = Image.new("RGBA", (CW * S, CH * S), (0, 0, 0, 0))
        s.d = ImageDraw.Draw(s.img)
    def line(s, a, b, col, w=2):
        s.d.line([a[0] * S, a[1] * S, b[0] * S, b[1] * S], fill=col, width=max(1, round(w * S)))
    def circle(s, c, r, fill=None, outline=None, w=0):
        s.d.ellipse([(c[0] - r) * S, (c[1] - r) * S, (c[0] + r) * S, (c[1] + r) * S],
                    fill=fill, outline=outline, width=round(w * S))
    def rrect(s, box, r, fill=None, outline=None, w=0):
        s.d.rounded_rectangle([box[0] * S, box[1] * S, box[2] * S, box[3] * S], radius=r * S,
                              fill=fill, outline=outline, width=round(w * S))
    def poly(s, pts, fill):
        s.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def text(s, xy, t, f, fill, anchor="mm"):
        s.d.text((xy[0] * S, xy[1] * S), t, font=font(f[0], f[1] * S), fill=fill, anchor=anchor)
    def out(s):
        return s.img.convert("RGBa").reduce(S).convert("RGBA")

def arrow(cv, a, b, col, w=4, head=14):
    cv.line(a, b, col, w)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    p1 = (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45))
    p2 = (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))
    cv.poly([b, p1, p2], col)

def glow(cv, c, r, col, k=1.0):
    for m, a in ((2.6, 0.10), (2.0, 0.16), (1.5, 0.26)):
        cv.circle(c, r * m, fill=(*col, int(255 * a * k)))

DARK = (18, 24, 48)
GRAY = (140, 148, 182)


# ----------------------------------------------------------------- 0. интро
_r0 = random.Random(7)
PARTS = [(_r0.uniform(80, 820), _r0.uniform(90, 650), _r0.uniform(20, 60), _r0.uniform(20, 60),
          _r0.uniform(0, 6.28), _r0.uniform(0, 6.28), _r0.uniform(0.4, 1.0), _r0.uniform(4, 9))
         for _ in range(28)]

def ill_intro(cv, t, col):
    cv.text((450, CY), "?", (F_XB, 420), (*col, 55))
    pts = [(bx + ax * math.sin(sp * t + px), by + ay * math.cos(sp * 0.8 * t + py), r)
           for bx, by, ax, ay, px, py, sp, r in PARTS]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
            if d < 210:
                cv.line(pts[i][:2], pts[j][:2], (*col, int(150 * (1 - d / 210))), 2)
    for k, (x, y, r) in enumerate(pts):
        pulse = 0.5 + 0.5 * math.sin(t * 2 + k)
        cv.circle((x, y), r * 2.2, fill=(*col, int(30 + 30 * pulse)))
        cv.circle((x, y), r, fill=(*col, 235))


# ----------------------------------------------------------------- 1. MLP
LAYERS, LX = [4, 5, 5, 3], [130, 343, 557, 770]
_rm = random.Random(3)
MW = {(l, i, j): _rm.uniform(0.35, 1) for l in range(3) for i in range(LAYERS[l]) for j in range(LAYERS[l + 1])}

def ill_mlp(cv, t, col):
    f = (t % 3.0) * 1.4 - 0.4
    pos = [[(LX[l], CY - 20 + (i - (n - 1) / 2) * 105) for i in range(n)] for l, n in enumerate(LAYERS)]
    for l in range(3):
        bl = max(0, 1 - abs(f - (l + 0.5)) * 1.25)
        for i, a in enumerate(pos[l]):
            for j, b in enumerate(pos[l + 1]):
                w = MW[(l, i, j)]
                cv.line(a, b, (*col, min(255, int(34 + 30 * w + 195 * bl * w))), 1.6 + 3.2 * bl * w)
    for l in range(4):
        b = max(0, 1 - abs(f - l) * 1.1)
        for (x, y) in pos[l]:
            if b > 0.05:
                glow(cv, (x, y), 22, col, b)
            cv.circle((x, y), 22, fill=(*mix(DARK, col, b), 255), outline=(*col, 210), w=3)
    for x, s in ((130, "вход"), (450, "скрытые слои"), (770, "выход")):
        cv.text((x, 660), s, (F_SB, 30), (*GRAY, 255))


# ----------------------------------------------------------------- 2. CNN
HOUSE = ["....#....", "...###...", "..#####..", ".#######.", "#########",
         ".#.....#.", ".#.###.#.", ".#.###.#.", ".#######."]
INP = np.array([[1.0 if ch == "#" else 0.0 for ch in row] for row in HOUSE])
OUTV = np.zeros((7, 7))
for _r in range(7):
    for _c in range(7):
        _w = INP[_r:_r + 3, _c:_c + 3]
        OUTV[_r, _c] = _w.max() - _w.min()

def ill_cnn(cv, t, col):
    C, gx, gy, ox, oy = 44, 48, CY - 198, 548, CY - 154
    rate = 10
    cyc = 49 / rate + 1.4
    k = min(int((t % cyc) * rate), 49)
    for r in range(9):
        for c in range(9):
            fill = mix((24, 30, 58), (226, 236, 255), INP[r, c])
            cv.rrect((gx + c * C + 2, gy + r * C + 2, gx + c * C + C - 2, gy + r * C + C - 2), 6, fill=(*fill, 255))
    for r in range(7):
        for c in range(7):
            fill = mix((24, 30, 58), col, 0.16 + 0.84 * OUTV[r, c]) if r * 7 + c < k else (20, 25, 48)
            cv.rrect((ox + c * C + 2, oy + r * C + 2, ox + c * C + C - 2, oy + r * C + C - 2), 6, fill=(*fill, 255))
    if k < 49:
        r0, c0 = divmod(k, 7)
        cv.rrect((gx + c0 * C, gy + r0 * C, gx + (c0 + 3) * C, gy + (r0 + 3) * C), 8, outline=(*col, 255), w=5)
        cv.rrect((ox + c0 * C, oy + r0 * C, ox + (c0 + 1) * C, oy + (r0 + 1) * C), 6, outline=(255, 255, 255, 255), w=4)
    arrow(cv, (462, CY), (534, CY), (*col, 230), 5, 16)
    cv.text((498, CY - 38), "фильтр", (F_SB, 26), (*GRAY, 255))
    cv.text((gx + 198, CY + 235), "изображение", (F_SB, 30), (*GRAY, 255))
    cv.text((ox + 154, CY + 235), "карта признаков", (F_SB, 30), (*GRAY, 255))
    cv.text((450, CY + 295), "окно 3×3 скользит по картинке", (F_SB, 30), (*col, 255))


# ----------------------------------------------------------------- 3. RNN
TOK = ["Я", "иду", "в", "кино", "!"]

def ill_rnn(cv, t, col):
    f = ((t % 5.0) / 3.8) * 5.4 - 0.3
    xs = [90 + i * 180 for i in range(5)]
    cy = CY - 10
    for i in range(4):
        x0, x1 = xs[i] + 66, xs[i + 1] - 66
        arrow(cv, (x0, cy), (x1, cy), (*col, 110), 4, 14)
        p = (f - (i + 0.55)) / 0.9
        if 0 < p < 1:
            cv.circle((x0 + (x1 - x0) * p, cy), 11, fill=(*col, 255))
    for i, x in enumerate(xs):
        act = f - i
        flash = max(0.0, 1 - act * 0.9) if act >= 0 else 0.0
        level = (0.28 + 0.72 * flash) if act >= 0 else 0.0
        arrow(cv, (x, cy + 128), (x, cy + 70), (*GRAY, 170), 3, 11)
        cv.text((x, cy + 160), TOK[i], (F_B, 44), (255, 255, 255, 255))
        arrow(cv, (x, cy - 64), (x, cy - 106), (*col, 120 + int(135 * flash)), 3, 11)
        if flash > 0.05:
            glow(cv, (x, cy - 128), 16, col, flash)
        cv.circle((x, cy - 128), 16, fill=(*mix(DARK, col, flash), 255), outline=(*col, 200), w=3)
        if flash > 0.05:
            glow(cv, (x, cy), 50, col, flash * 0.8)
        cv.rrect((x - 62, cy - 62, x + 62, cy + 62), 28, fill=(*mix(DARK, col, level), 255),
                 outline=(*col, 255 if act >= 0 else 90), w=4)
        cv.text((x, cy), f"h{i + 1}", (F_B, 40), (255, 255, 255, 255) if act >= 0 else (*GRAY, 255))
    cv.text((450, CY + 275), "память о предыдущих шагах", (F_SB, 32), (*col, 255))


# ----------------------------------------------------------------- 4. Transformer
TT = ["Кот", "сел", "на", "мягкий", "диван"]
_rt = random.Random(11)
AW = []
for _i in range(5):
    row = [0.0 if _i == _j else _rt.uniform(0.15, 1.0) for _j in range(5)]
    m = max(row)
    AW.append([v / m for v in row])
TPOS = [(450 + 270 * math.cos(math.radians(-90 + 72 * i)), CY - 15 + 255 * math.sin(math.radians(-90 + 72 * i)))
        for i in range(5)]

def ill_trf(cv, t, col):
    k = int(t / 1.2) % 5
    blend = smooth(((t % 1.2) / 1.2) / 0.35)
    for i in range(5):
        for j in range(i + 1, 5):
            cv.line(TPOS[i], TPOS[j], (*col, 28), 2)
    for j in range(5):
        if j == k:
            continue
        w = AW[k][j] * blend
        cv.line(TPOS[k], TPOS[j], (*col, int(60 + 195 * w)), 3 + 11 * w)
    for i, (x, y) in enumerate(TPOS):
        w = 1.0 if i == k else AW[k][i] * blend
        wd = max(150, font(F_B, 36).getlength(TT[i]) + 64)
        if w > 0.5:
            cv.rrect((x - wd / 2 - 8, y - 43, x + wd / 2 + 8, y + 43), 30, fill=(*col, int(60 * w)))
        cv.rrect((x - wd / 2, y - 35, x + wd / 2, y + 35), 26, fill=(*mix(DARK, col, 0.9 * w), 255),
                 outline=(*col, 230), w=3)
        cv.text((x, y), TT[i], (F_B, 36), (255, 255, 255, 255))
    cv.text((450, CY + 330), "каждое слово смотрит на все остальные", (F_SB, 30), (*GRAY, 255))


# ----------------------------------------------------------------- 5. Генеративные (диффузия)
GW = 140

def make_target():
    yy, xx = np.mgrid[0:GW, 0:GW].astype(np.float32) / (GW - 1)
    img = np.array([40, 28, 112], np.float32) * (1 - yy[..., None]) + np.array([255, 140, 120], np.float32) * yy[..., None]
    d = np.hypot(xx - 0.66, yy - 0.55)
    img += np.clip(1 - d / 0.45, 0, 1)[..., None] ** 2 * np.array([120, 70, 20], np.float32)
    img[d < 0.13] = (255, 232, 160)
    far = 0.68 + 0.07 * np.sin(6 * xx + 1) + 0.04 * np.sin(13 * xx)
    img[yy > far] = (66, 42, 120)
    near = 0.82 + 0.05 * np.sin(5 * xx + 3) + 0.03 * np.sin(17 * xx)
    img[yy > near] = (26, 18, 62)
    return np.clip(img, 0, 255)

TARGET = make_target()
_rng = np.random.default_rng(5)
NOISE = [_rng.integers(0, 256, (GW, GW, 3)).astype(np.float32) for _ in range(6)]
GMASK = Image.new("L", (560 * S, 560 * S), 0)
ImageDraw.Draw(GMASK).rounded_rectangle([0, 0, 560 * S - 1, 560 * S - 1], radius=36 * S, fill=255)

def ill_gen(cv, t, col):
    ph = t % 7.0
    q = smooth(ph / 4.6) if ph < 4.6 else (1.0 if ph < 6.4 else 1 - (ph - 6.4) / 0.6)
    arr = TARGET * q + NOISE[int(t * 12) % 6] * (1 - q)
    im = Image.fromarray(arr.astype(np.uint8)).resize((560 * S, 560 * S), Image.NEAREST)
    cv.img.paste(im, (170 * S, 30 * S), GMASK)
    cv.rrect((170, 30, 730, 590), 36, outline=(*col, 255), w=4)
    cv.rrect((170, 622, 730, 636), 7, fill=(30, 36, 66, 255))
    if q > 0.01:
        cv.rrect((170, 622, 170 + 560 * q, 636), 7, fill=(*col, 255))
    cv.text((170, 676), "шум", (F_SB, 30), (*GRAY, 255), anchor="lm")
    cv.text((730, 676), "картинка", (F_SB, 30), (*GRAY, 255), anchor="rm")
    cv.text((450, 676), f"шаг {int(q * 50)} / 50", (F_B, 30), (*col, 255))


# ----------------------------------------------------------------- 6. Финал
SHORT = ["MLP", "CNN", "RNN", "Transformer", "GAN · Diffusion"]

def ill_outro(cv, t, col):
    for i in range(5):
        sc = SCENES[i + 1]
        e = ease_out((t - (0.3 + 0.28 * i)) / 0.45)
        if e <= 0:
            continue
        a = int(255 * e)
        c = sc["color"]
        x0, y0 = 90 + (1 - e) * 120, 60 + i * 132
        cv.rrect((x0, y0, x0 + 720, y0 + 100), 30, fill=(22, 27, 54, a), outline=(*c, a), w=3)
        cv.circle((x0 + 50, y0 + 50), 30, fill=(*c, a))
        cv.text((x0 + 50, y0 + 50), str(i + 1), (F_XB, 34), (10, 12, 26, a))
        cv.text((x0 + 100, y0 + 50), sc["title"].capitalize(), (F_XB, 44), (255, 255, 255, a), anchor="lm")
        cv.text((x0 + 700, y0 + 50), SHORT[i], (F_SB, 28), (*GRAY, a), anchor="rm")


ILL = [ill_intro, ill_mlp, ill_cnn, ill_rnn, ill_trf, ill_gen, ill_outro]


# ----------------------------------------------------------------- кадр
BG, TITLE = [], []

def scene_at(t):
    for i, sc in enumerate(SCENES):
        if t < sc["end"]:
            return i
    return len(SCENES) - 1

def make_frame(t):
    si = scene_at(t)
    sc = SCENES[si]
    lt = t - sc["start"]
    fr = BG[si].copy()
    e = ease_out(lt / 0.45)
    L = TITLE[si]
    if e < 1:
        L = L.copy()
        L.putalpha(L.getchannel("A").point(lambda v, e=e: int(v * e)))
    fr.paste(L, (0, 130 + int((1 - e) * 45)), L)
    cv = Cv()
    ILL[si](cv, lt, sc["color"])
    im = cv.out()
    e2 = ease_out((lt - 0.1) / 0.5)
    if e2 < 1:
        im.putalpha(im.getchannel("A").point(lambda v, e2=e2: int(v * e2)))
    fr.paste(im, ILL_POS, im)
    draw_caption(fr, sc, t)
    return fr


# ----------------------------------------------------------------- звук
def make_music(total):
    """Возвращает numpy-буфер музыки (mono float32, SR). Переходы — 'колокольчик'."""
    n = int((total + 0.6) * SR)
    sig = np.zeros(n, dtype=np.float32)

    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63],
              [261.63, 329.63, 392.0], [196.0, 246.94, 293.66]]
    roots  = [110.0, 87.31, 130.81, 98.0]
    seg = 6.0

    # --- пад + бас ---
    for k in range(int(total / seg) + 2):
        s0, dur = k * seg - 0.8, 7.6
        a, b = max(0, int(s0 * SR)), min(n, int((s0 + dur) * SR))
        if b <= a:
            continue
        tt = np.arange(a, b) / SR - s0
        env = np.sin(np.pi * tt / dur) ** 2
        ch = chords[k % 4]
        for f in ch:
            sig[a:b] += env * 0.5 * (np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * f * 1.003 * tt))
        sig[a:b] += env * 0.8 * np.sin(2 * np.pi * roots[k % 4] * tt)

    # --- арпеджио-«капли» ---
    step = 0.5
    for i in range(int(total / step)):
        ts = i * step
        f = chords[int(ts // seg) % 4][i % 3] * 2
        a, b = int(ts * SR), min(n, int((ts + 0.6) * SR))
        tt = np.arange(a, b) / SR - ts
        sig[a:b] += 0.22 * np.exp(-tt * 7) * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt))

    # --- переход между сценами: 'колокольчик' ---
    for sc in SCENES[1:]:
        sig = _add_bell(sig, at=sc["start"] - 0.05, base_f=880.0, gain=0.55)
    return sig


def _add_bell(sig, at, base_f=880.0, gain=0.5, dur=0.9, sr=SR):
    """Колокольчик: сумма обертонов с быстрым затуханием. FM-модуляция для 'металла'."""
    n = len(sig)
    a = max(0, int(at * sr))
    b = min(n, a + int(dur * sr))
    if b <= a:
        return sig
    tt = np.arange(b - a) / sr
    env = np.exp(-tt * 4.5)
    f_mod = base_f * 2.4                       # несущая-модулятор
    mod   = np.sin(2 * np.pi * f_mod * tt) * 2.2 * np.exp(-tt * 6)
    car   = np.sin(2 * np.pi * base_f * tt + mod)
    tone  = car + 0.35 * np.sin(2 * np.pi * base_f * 2.01 * tt) \
                + 0.20 * np.sin(2 * np.pi * base_f * 3.02 * tt)
    sig[a:b] += (gain * env * tone).astype(np.float32)
    return sig


def mix_voice_and_music(total, music):
    """Музыка ровным тихим фоном + голос. Без ducking."""
    n = int(total * SR) + SR
    voice = np.zeros(n, dtype=np.float32)
    for sc in SCENES:
        vp = voice_path(sc["key"])
        if not os.path.exists(vp):
            continue
        v = decode_audio(vp)
        a = int((sc["start"] + LEAD) * SR)
        b = min(n, a + len(v))
        voice[a:b] += v[:b - a]

    m = np.zeros(n, dtype=np.float32)
    m[:min(n, len(music))] = music[:min(n, len(music))]

    # Музыка — ровный тихий фон. FLOOR_DB задаёт уровень относительно микса.
    MUSIC_GAIN = 0.20          # 70% от текущего уровня (−30%)
    FLOOR_DB   = -16.0
    m *= 10 ** (FLOOR_DB / 20.0) * MUSIC_GAIN

    mix = m + voice
    peak = np.abs(mix).max()
    if peak > 1.0:
        mix *= 0.99 / peak
    mix *= 0.85  # запас по True Peak под −14 LUFS / −1.4 dBTP
    return mix


def write_wav(path, x, sr=SR):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())


def normalize_lufs(in_wav, out_wav):
    """Двухпроходная нормализация под −14 LUFS / −1.4 dBTP (YouTube)."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", in_wav,
         "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True)
    txt = r.stderr
    js = json.loads(txt[txt.rfind("{"): txt.rfind("}") + 1])
    af = (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:"
          f"measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:"
          f"offset={js['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", in_wav,
                    "-af", af, "-c:a", "pcm_s16le", out_wav], check=True)


# ----------------------------------------------------------------- субтитры / сценарий в файлы
def srt_time(x):
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

def write_texts(total):
    n = 1
    with open(os.path.join(OUT_DIR, "captions.srt"), "w", encoding="utf-8") as f:
        for sc in SCENES:
            for c in sc["chunks"]:
                text = " ".join(sc["words"][j]["text"] for j in c["idxs"])
                f.write(f"{n}\n{srt_time(c['t0'])} --> {srt_time(c['t1'])}\n{text}\n\n")
                n += 1
    with open(os.path.join(OUT_DIR, "voiceover_script.txt"), "w", encoding="utf-8") as f:
        f.write(f"СЦЕНАРИЙ ОЗВУЧКИ (общая длительность ~{total:.0f} сек)\n")
        f.write("Темп: ~2.5 слова/сек. Тайминги ориентировочные.\n\n")
        for sc in SCENES:
            f.write(f"[{sc['start']:05.1f} - {sc['end']:05.1f}] {sc['title']}\n{sc['text']}\n\n")


# ----------------------------------------------------------------- main
def main():
    global OUT_DIR

    stills = "--stills" in sys.argv
    total = build_timeline()
    print(f"Длительность: {total:.1f} сек, слов: {sum(len(s['words']) for s in SCENES)}")

    # --- версионирование по timestamp ---------------------------------------
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if stills:
        OUT_DIR = os.path.join(OUT_DIR, ts + "_stills")
    else:
        OUT_DIR = os.path.join(OUT_DIR, ts)
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Папка вывода: {OUT_DIR}")
    # ------------------------------------------------------------------------

    for sc in SCENES:
        layout_caption(sc)
        BG.append(make_bg(sc["color"]))
    for si in range(len(SCENES)):
        TITLE.append(build_title(si))

    STILLS = os.path.join(OUT_DIR, "stills")

    if stills:
        os.makedirs(STILLS, exist_ok=True)
        thumbs = []
        for si, sc in enumerate(SCENES):
            frac = 0.85 if si == 6 else 0.7
            fr = make_frame(sc["start"] + (sc["end"] - sc["start"]) * frac)
            fr.save(os.path.join(STILLS, f"{si}_{sc['key']}.png"))
            thumbs.append(fr.resize((405, 720)))
        sheet = Image.new("RGB", (405 * 4, 720 * 2), (0, 0, 0))
        for i, th in enumerate(thumbs):
            sheet.paste(th, ((i % 4) * 405, (i // 4) * 720))
        sheet.save(os.path.join(STILLS, "sheet.png"))
        print("Кадры сохранены в:", STILLS)
        return

    # --- аудио: музыка + голос + нормализация ---
    music = make_music(total)
    mix   = mix_voice_and_music(total, music)
    raw   = os.path.join(OUT_DIR, "audio_raw.wav")
    wav   = os.path.join(OUT_DIR, "audio_final.wav")
    write_wav(raw, mix)
    normalize_lufs(raw, wav)
    print("Аудио:", wav)

    out = os.path.join(OUT_DIR, "shorts_neural_networks.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
           "-movflags", "+faststart", out]

    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nframes = int(total * FPS)
    for i in range(nframes):
        p.stdin.write(make_frame(i / FPS).tobytes())
        if i % 150 == 0:
            print(f"кадр {i}/{nframes}", flush=True)
    p.stdin.close()
    p.wait()
    write_texts(total)
    print("Готово:", out)

if __name__ == "__main__":
    main()
