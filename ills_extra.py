# ills_extra.py
"""Дополнительные иллюстрации для video_generator.py.

Подключаются в video_generator.build_registry() поверх shorts_creator.ILL.
Каждая функция: ill_xxx(cv, t, col, params=None) -> None
- cv   : shorts_creator.Cv (канвас CW*S x CH*S)
- t    : локальное время сцены (сек)
- col  : RGB-кортеж цвета сцены
- params: dict из scene["ill_params"]

Схемы params — см. PROMPT.md, блок «Реестр иллюстраций».
Если параметр отсутствует — берётся дефолт. Если данных недостаточно
для отрисовки — кидаем ValueError с понятным текстом (до рендера,
в момент вызова ill_*, чтобы было видно, какая сцена сломалась).
"""
import math
import numpy as np

import shorts_creator as sc
from shorts_creator import (
    Cv, arrow, glow, mix, ease_out, smooth, font,
    DARK, GRAY, CW, CH, CY, S, F_XB, F_B, F_SB,
)

WHITE = (255, 255, 255)
# допустимые значения
GRAPH_KINDS  = ("bar", "line", "area", "donut")
LAYOUTS      = ("horizontal", "vertical")
DIRECTIONS   = ("forward", "backward", "bidirectional")
TRF_MODES    = ("graph", "heatmap")
ICONS        = ("in", "proc", "out", "none")


# ===========================================================================
# 1. GRAPH — график (bar / line / area / donut)
# ===========================================================================
def ill_graph(cv, t, col, params=None):
    p = params or {}
    kind   = p.get("kind", "bar")
    series = p.get("series") or []
    labels = p.get("labels") or []
    axis_x = p.get("axis_x", "")
    axis_y = p.get("axis_y", "")
    hl     = p.get("highlight") or None

    if kind not in GRAPH_KINDS:
        raise ValueError(f"ill_graph: kind='{kind}' не из {GRAPH_KINDS}")
    if not (1 <= len(series) <= 3):
        raise ValueError(f"ill_graph: нужно 1–3 series, получено {len(series)}")
    n_vals = [len(s.get("values", [])) for s in series]
    if any(v < 2 or v > 10 for v in n_vals):
        raise ValueError(f"ill_graph: values должно быть 2–10, получено {n_vals}")
    if len(set(n_vals)) != 1:
        raise ValueError(f"ill_graph: у всех series должна быть одинаковая длина values")
    n = n_vals[0]
    if labels and len(labels) != n:
        raise ValueError(f"ill_graph: len(labels)={len(labels)} != len(values)={n}")

    # анимация появления
    prog = smooth(t / 0.8)

    if kind == "donut":
        _graph_donut(cv, col, series[0], prog)
        return

    # сетка
    pad_l, pad_r, pad_t, pad_b = 90, 60, 70, 110
    gx0, gx1 = pad_l, CW - pad_r
    gy0, gy1 = pad_t, CH - pad_b
    gw, gh = gx1 - gx0, gy1 - gy0

    # общий максимум по всем series
    vmax = max(max(s["values"]) for s in series) or 1
    vmin = 0

    # гориз. линии сетки (5 шт)
    for i in range(5):
        y = gy0 + gh * i / 4
        cv.line((gx0, y), (gx1, y), (*GRAY, 70), 1)

    # подпись оси Y
    if axis_y:
        cv.text((pad_l - 18, gy0 - 30), axis_y, (F_SB, 24), (*GRAY, 255), anchor="rm")

    # столбцы / линии
    step = gw / n
    x_centers = [gx0 + step * (i + 0.5) for i in range(n)]
    for si, s in enumerate(series):
        scol = tuple(s.get("color", col))
        vals = s["values"]
        if kind == "bar":
            bw = step * (0.7 / len(series))
            for i, v in enumerate(vals):
                h = (v - vmin) / (vmax - vmin) * gh * prog
                x0 = x_centers[i] - (bw * len(series)) / 2 + si * bw
                y0 = gy1 - h
                cv.rrect((x0 + 4, y0, x0 + bw - 4, gy1), 8,
                         fill=(*scol, 230))
        elif kind in ("line", "area"):
            pts = []
            for i, v in enumerate(vals):
                x = x_centers[i]
                y = gy1 - (v - vmin) / (vmax - vmin) * gh * prog
                pts.append((x, y))
            if kind == "area":
                poly = [(pts[0][0], gy1)] + pts + [(pts[-1][0], gy1)]
                cv.poly(poly, (*scol, 90))
            for i in range(len(pts) - 1):
                cv.line(pts[i], pts[i + 1], (*scol, 255), 5)
            for (x, y) in pts:
                cv.circle((x, y), 8, fill=(*scol, 255))

    # подписи X
    for i, lbl in enumerate(labels):
        cv.text((x_centers[i], gy1 + 30), str(lbl), (F_SB, 24), (*GRAY, 255))

    # подпись оси X
    if axis_x:
        cv.text(((gx0 + gx1) / 2, gy1 + 70), axis_x, (F_SB, 24), (*GRAY, 255))

    # подсветка точки
    if hl and isinstance(hl.get("index"), int) and 0 <= hl["index"] < n:
        i = hl["index"]
        x = x_centers[i]
        s0 = series[0]
        y = gy1 - (s0["values"][i] - vmin) / (vmax - vmin) * gh
        cv.circle((x, y), 18, fill=(*WHITE, 60))
        cv.circle((x, y), 11, fill=(*WHITE, 255))
        if hl.get("label"):
            cv.text((x, y - 40), str(hl["label"]), (F_B, 30), (*WHITE, 255))

    # легенда (если series > 1)
    if len(series) > 1:
        lx = gx0
        ly = pad_t - 34
        for s in series:
            scol = tuple(s.get("color", col))
            cv.circle((lx, ly), 9, fill=(*scol, 255))
            cv.text((lx + 20, ly), s.get("name", ""), (F_SB, 24), (*GRAY, 255), anchor="lm")
            lx += 30 + int(font(F_SB, 24).getlength(s.get("name", ""))) + 30


def _graph_donut(cv, col, series, prog):
    vals = series.get("values", [])
    if not vals:
        raise ValueError("ill_graph: donut требует series[0].values")
    scol = tuple(series.get("color", col))
    total = sum(vals) or 1
    cx, cy, r_out, r_in = 450, CY, 230, 130
    start = -90.0
    for i, v in enumerate(vals):
        sweep = 360.0 * (v / total) * prog
        if sweep <= 0:
            continue
        sh = 0.75 + 0.25 * math.cos(math.radians(i * 40 + start))
        col_i = mix((20, 24, 48), scol, sh)
        # рисуем сектор как многоугольник между r_in и r_out
        steps = max(6, int(sweep / 6))
        pts_out = []
        pts_in  = []
        for k in range(steps + 1):
            a = math.radians(start + sweep * k / steps)
            pts_out.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
            pts_in.append((cx + r_in * math.cos(a),  cy + r_in * math.sin(a)))
        poly = pts_out + pts_in[::-1]
        cv.poly(poly, (*col_i, 255))
        start += sweep
    # центр
    cv.circle((cx, cy), r_in - 4, fill=(*DARK, 255))
    cv.text((cx, cy - 10), str(total), (F_XB, 56), (*WHITE, 255))
    cv.text((cx, cy + 40), series.get("name", ""), (F_SB, 26), (*GRAY, 255))


# ===========================================================================
# 2. FLOW — блок-схема
# ===========================================================================
def ill_flow(cv, t, col, params=None):
    p = params or {}
    steps  = p.get("steps") or []
    layout = p.get("layout", "horizontal")
    hl     = p.get("highlight_step", None)
    arrows = p.get("arrows", "forward")
    icons  = p.get("icons") or []

    if not (2 <= len(steps) <= 6):
        raise ValueError(f"ill_flow: нужно 2–6 шагов, получено {len(steps)}")
    if layout not in LAYOUTS:
        raise ValueError(f"ill_flow: layout='{layout}' не из {LAYOUTS}")
    if arrows not in ("forward", "bidirectional"):
        raise ValueError(f"ill_flow: arrows='{arrows}' не из forward/bidirectional")
    for s in steps:
        if len(s) > 12:
            raise ValueError(f"ill_flow: шаг '{s}' длиннее 12 символов")
    if icons:
        if len(icons) != len(steps):
            raise ValueError(f"ill_flow: len(icons) != len(steps)")
        for ic in icons:
            if ic not in ICONS:
                raise ValueError(f"ill_flow: icon='{ic}' не из {ICONS}")

    n = len(steps)
    prog = smooth(t / 0.7)

    if layout == "horizontal":
        block_w = min(220, (CW - 120) / n - 20)
        block_h = 150
        total_w = n * block_w + (n - 1) * 40
        x_start = (CW - total_w) / 2
        y_cy = CY
        centers = [(x_start + i * (block_w + 40) + block_w / 2, y_cy) for i in range(n)]
    else:
        block_w = min(420, CW - 200)
        block_h = 90
        total_h = n * block_h + (n - 1) * 30
        y_start = (CH - total_h) / 2
        centers = [(CW / 2, y_start + i * (block_h + 30) + block_h / 2) for i in range(n)]

    # стрелки между блоками
    for i in range(n - 1):
        ax, ay = centers[i]
        bx, by = centers[i + 1]
        if layout == "horizontal":
            a = (ax + block_w / 2, ay)
            b = (bx - block_w / 2, by)
        else:
            a = (ax, ay + block_h / 2)
            b = (bx, by - block_h / 2)
        arrow(cv, a, b, (*GRAY, 200), 4, 14)
        if arrows == "bidirectional":
            arrow(cv, b, a, (*GRAY, 200), 4, 14)

    # блоки
    for i, (cx, cy) in enumerate(centers):
        appear = ease_out((t - i * 0.08) / 0.4)
        if appear <= 0:
            continue
        x0, y0 = cx - block_w / 2, cy - block_h / 2
        x1, y1 = cx + block_w / 2, cy + block_h / 2
        is_hl = (hl == i)
        fill_col = (*mix(DARK, col, 0.85 if is_hl else 0.18), int(255 * appear))
        out_col  = (*col, int(255 * appear)) if is_hl else (*GRAY, int(255 * appear))
        cv.rrect((x0, y0, x1, y1), 20, fill=fill_col, outline=out_col, w=4 if is_hl else 2)

        # иконка
        if icons and icons[i] != "none":
            ic_y = y0 + 30
            _draw_icon(cv, (cx, ic_y), icons[i], (*col, int(255 * appear)))
            ty = cy + 14
        else:
            ty = cy

        # текст — ужимаем, если длинно
        size = 28
        while font(F_B, size).getlength(steps[i]) > block_w - 20 and size > 14:
            size -= 2
        cv.text((cx, ty), steps[i], (F_B, size), (*WHITE, int(255 * appear)))

        # номер шага
        cv.circle((x0 + 22, y0 + 22), 16, fill=(*col, int(220 * appear)))
        cv.text((x0 + 22, y0 + 22), str(i + 1), (F_XB, 20), (*DARK, int(255 * appear)))


def _draw_icon(cv, c, kind, col):
    x, y = c
    if kind == "in":
        cv.line((x - 20, y), (x + 12, y), col, 4)
        cv.poly([(x + 20, y), (x + 6, y - 10), (x + 6, y + 10)], col)
    elif kind == "out":
        cv.line((x - 12, y), (x + 20, y), col, 4)
        cv.poly([(x + 20, y), (x + 6, y - 10), (x + 6, y + 10)], col)
    elif kind == "proc":
        cv.circle((x, y), 14, outline=col, w=4)
        cv.circle((x, y), 5, fill=col)


# ===========================================================================
# 3. TIMELINE — шкала времени
# ===========================================================================
def ill_timeline(cv, t, col, params=None):
    p = params or {}
    events = p.get("events") or []
    hl     = p.get("highlight_event", None)
    direction = p.get("direction", "horizontal")

    if not (2 <= len(events) <= 6):
        raise ValueError(f"ill_timeline: нужно 2–6 событий, получено {len(events)}")
    for e in events:
        if "label" not in e:
            raise ValueError("ill_timeline: у каждого event должен быть label")
    if direction not in ("horizontal", "vertical"):
        raise ValueError(f"ill_timeline: direction='{direction}' не из horizontal/vertical")

    n = len(events)
    prog = smooth(t / 0.9)

    if direction == "horizontal":
        x0, x1 = 120, CW - 120
        y_axis = CY
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        cv.line((x0, y_axis), (x0 + (x1 - x0) * prog, y_axis), (*col, 200), 5)
        for i, e in enumerate(events):
            if i / (n - 1) > prog + 0.05:
                break
            x = xs[i]
            is_hl = (hl == i)
            r = 22 if is_hl else 14
            cv.circle((x, y_axis), r + 6, fill=(*col, 60 if is_hl else 30))
            cv.circle((x, y_axis), r, fill=(*mix(DARK, col, 1.0 if is_hl else 0.4), 255),
                      outline=(*col, 255), w=3)
            cv.text((x, y_axis - 70), str(e["label"]), (F_XB, 34 if is_hl else 30), (*col, 255))
            if e.get("text"):
                cv.text((x, y_axis + 70), str(e["text"]), (F_SB, 24), (*WHITE, 255))
    else:
        y0, y1 = 90, CH - 90
        x_axis = CW / 2
        ys = [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]
        cv.line((x_axis, y0), (x_axis, y0 + (y1 - y0) * prog), (*col, 200), 5)
        for i, e in enumerate(events):
            if i / (n - 1) > prog + 0.05:
                break
            y = ys[i]
            is_hl = (hl == i)
            r = 22 if is_hl else 14
            cv.circle((x_axis, y), r + 6, fill=(*col, 60 if is_hl else 30))
            cv.circle((x_axis, y), r, fill=(*mix(DARK, col, 1.0 if is_hl else 0.4), 255),
                      outline=(*col, 255), w=3)
            cv.text((x_axis + 50, y), str(e["label"]), (F_XB, 32), (*col, 255), anchor="lm")
            if e.get("text"):
                cv.text((x_axis + 50, y + 32), str(e["text"]), (F_SB, 22), (*WHITE, 255), anchor="lm")


# ===========================================================================
# 4. TREE — дерево / иерархия
# ===========================================================================
def ill_tree(cv, t, col, params=None):
    p = params or {}
    root = p.get("root", "")
    branches = p.get("branches") or []
    hl_path = p.get("highlight_path") or []

    if not root or len(root) > 16:
        raise ValueError(f"ill_tree: root должен быть 1–16 символов, получено '{root}'")
    if not (2 <= len(branches) <= 8):
        raise ValueError(f"ill_tree: нужно 2–8 веток, получено {len(branches)}")
    for b in branches:
        if "label" not in b:
            raise ValueError("ill_tree: у каждой branch должен быть label")
        leaves = b.get("leaves") or []
        if len(leaves) > 3:
            raise ValueError(f"ill_tree: у ветки '{b['label']}' больше 3 листьев")
    if hl_path:
        if len(hl_path) >= 1:
            bi = hl_path[0]
            if not (0 <= bi < len(branches)):
                raise ValueError(f"ill_tree: highlight_path[0]={bi} вне диапазона веток")
        if len(hl_path) >= 2:
            bi, li = hl_path[0], hl_path[1]
            if bi < len(branches) and branches[bi].get("leaves"):
                if not (0 <= li < len(branches[bi]["leaves"])):
                    raise ValueError(f"ill_tree: highlight_path[1]={li} вне диапазона листьев")

    n = len(branches)
    has_leaves = any(b.get("leaves") for b in branches)
    prog = smooth(t / 0.9)

    # координаты
    root_y = 90
    br_y   = 300 if has_leaves else CH - 180
    lf_y   = br_y + 190
    root_cx = CW / 2
    margin = 70
    br_xs = [margin + (CW - 2 * margin) * (i + 0.5) / n for i in range(n)]

    def node_alpha(k):
        return ease_out((t - k * 0.1) / 0.4)

    # корень
    if node_alpha(0) > 0:
        _tree_node(cv, (root_cx, root_y), root, col, hl=(len(hl_path) == 0), a=node_alpha(0))

    # рёбра корень → ветки
    for i, bx in enumerate(br_xs):
        if prog < (i + 1) / (n + 1):
            continue
        is_hl = hl_path and hl_path[0] == i
        cv.line((root_cx, root_y + 40), (bx, br_y - 40),
                (*col, 220 if is_hl else 130), 3 if is_hl else 2)

    # ветки
    for i, b in enumerate(branches):
        if node_alpha(i + 1) <= 0:
            continue
        is_hl = hl_path and hl_path[0] == i
        _tree_node(cv, (br_xs[i], br_y), b["label"], col, hl=is_hl, a=node_alpha(i + 1))

    # листья
    if has_leaves:
        for i, b in enumerate(branches):
            leaves = b.get("leaves") or []
            if not leaves:
                continue
            is_branch_hl = hl_path and hl_path[0] == i
            sub_w = 110
            total_w = len(leaves) * sub_w
            for j, lf in enumerate(leaves):
                x = br_xs[i] - total_w / 2 + sub_w * (j + 0.5)
                a = node_alpha(n + i + j + 1)
                if a <= 0:
                    continue
                is_hl = is_branch_hl and len(hl_path) >= 2 and hl_path[1] == j
                cv.line((br_xs[i], br_y + 40), (x, lf_y - 30),
                        (*col, 200 if is_hl else 110), 3 if is_hl else 2)
                _tree_node(cv, (x, lf_y), str(lf), col, hl=is_hl, a=a, small=True)


def _tree_node(cv, c, text, col, hl=False, a=1.0, small=False):
    x, y = c
    if small:
        w, h = 100, 60
        size = 22
    else:
        w = max(160, int(font(F_B, 28).getlength(text)) + 60)
        h = 80
        size = 28
    fill = (*mix(DARK, col, 1.0 if hl else 0.25), int(255 * a))
    edge = (*col, int(255 * a)) if hl else (*GRAY, int(255 * a))
    cv.rrect((x - w / 2, y - h / 2, x + w / 2, y + h / 2), 18,
             fill=fill, outline=edge, w=4 if hl else 2)
    # ужимаем текст
    while font(F_B, size).getlength(text) > w - 20 and size > 12:
        size -= 2
    cv.text((x, y), text, (F_B, size), (*WHITE, int(255 * a)))


# ===========================================================================
# 5. COMPARE — A vs B
# ===========================================================================
def ill_compare(cv, t, col, params=None):
    p = params or {}
    left  = p.get("left") or {}
    right = p.get("right") or {}
    hl_side = p.get("highlight_side", "none")

    if not left.get("title") or not right.get("title"):
        raise ValueError("ill_compare: у left/right должен быть title")
    for side, name in ((left, "left"), (right, "right")):
        items = side.get("items") or []
        if not (1 <= len(items) <= 4):
            raise ValueError(f"ill_compare: {name}.items должно быть 1–4, получено {len(items)}")

    prog = smooth(t / 0.6)

    col_l = tuple(left.get("color", col))
    col_r = tuple(right.get("color", col))

    pad = 60
    gap = 80
    col_w = (CW - 2 * pad - gap) / 2
    y0, y1 = 100, CH - 100

    # левая колонка
    _compare_col(cv, (pad, y0, pad + col_w, y1), col_l, left, prog, hl_side == "left")
    # правая
    _compare_col(cv, (pad + col_w + gap, y0, pad + 2 * col_w + gap, y1), col_r, right, prog, hl_side == "right")

    # "vs" в центре
    cv.circle((CW / 2, CY), 46, fill=(*DARK, 255), outline=(*GRAY, 255), w=3)
    cv.text((CW / 2, CY), "vs", (F_XB, 36), (*GRAY, 255))


def _compare_col(cv, box, col, data, prog, hl):
    x0, y0, x1, y1 = box
    a = int(255 * prog)
    # заголовок
    title = data["title"]
    size = 36
    while font(F_XB, size).getlength(title) > (x1 - x0 - 20) and size > 20:
        size -= 2
    cv.rrect((x0, y0, x1, y0 + 80), 20,
             fill=(*mix(DARK, col, 1.0 if hl else 0.35), a),
             outline=(*col, a), w=4 if hl else 2)
    cv.text(((x0 + x1) / 2, y0 + 40), title, (F_XB, size), (*WHITE, a))

    # items
    items = data.get("items") or []
    ih = 90
    y = y0 + 110
    for it in items:
        cv.rrect((x0 + 10, y, x1 - 10, y + ih - 20), 14,
                 fill=(18, 22, 44, a), outline=(*col, int(a * 0.6)), w=2)
        # ужимаем
        size = 28
        while font(F_SB, size).getlength(it) > (x1 - x0 - 40) and size > 16:
            size -= 2
        cv.text(((x0 + x1) / 2, y + (ih - 20) / 2), it, (F_SB, size), (*WHITE, a))
        y += ih


# ===========================================================================
# 6. MLP+ — обновлённый ill_mlp (params: layers, highlight_layer, node_size)
# ===========================================================================
_MLP_W_CACHE = {}

def _mlp_weights(layers):
    key = tuple(layers)
    if key not in _MLP_W_CACHE:
        import random as _r
        rm = _r.Random(3)
        _MLP_W_CACHE[key] = {
            (l, i, j): rm.uniform(0.35, 1)
            for l in range(len(layers) - 1)
            for i in range(layers[l]) for j in range(layers[l + 1])
        }
    return _MLP_W_CACHE[key]


def ill_mlp(cv, t, col, params=None):
    p = params or {}
    layers = list(p.get("layers", [4, 5, 5, 3]))
    hl_layer = p.get("highlight_layer", None)
    node_r = int(p.get("node_size", 22))

    if not (3 <= len(layers) <= 5):
        raise ValueError(f"ill_mlp: layers должно быть 3–5, получено {len(layers)}")
    for i, n in enumerate(layers):
        lo = 1 if i == len(layers) - 1 else 2   # последний слой может быть 1
        if not (lo <= n <= 8):
            raise ValueError(f"ill_mlp: слой {i} должен быть {lo}–8, получено {n}")

    n_layers = len(layers)
    if n_layers == 1:
        LX = [450]
    else:
        LX = [130 + i * (770 - 130) / (n_layers - 1) for i in range(n_layers)]

    max_n = max(layers)
    step_y = min(105, 660 / max_n) if max_n else 105

    MW = _mlp_weights(layers)
    f = (t % 3.0) * 1.4 - 0.4

    pos = [[(LX[l], CY - 20 + (i - (n - 1) / 2) * step_y) for i in range(n)]
           for l, n in enumerate(layers)]

    for l in range(n_layers - 1):
        bl = max(0, 1 - abs(f - (l + 0.5)) * 1.25)
        for i, a in enumerate(pos[l]):
            for j, b in enumerate(pos[l + 1]):
                w = MW[(l, i, j)]
                cv.line(a, b, (*col, min(255, int(34 + 30 * w + 195 * bl * w))),
                        1.6 + 3.2 * bl * w)

    for l in range(n_layers):
        b = max(0, 1 - abs(f - l) * 1.1)
        if hl_layer is not None and l == hl_layer:
            b = max(b, 0.8)
        for (x, y) in pos[l]:
            if b > 0.05:
                glow(cv, (x, y), node_r, col, b)
            cv.circle((x, y), node_r, fill=(*mix(DARK, col, b), 255),
                      outline=(*col, 210), w=3)

    cv.text((LX[0], 660), "вход", (F_SB, 30), (*GRAY, 255))
    if n_layers >= 3:
        cv.text((LX[n_layers // 2], 660), "скрытые слои", (F_SB, 30), (*GRAY, 255))
    cv.text((LX[-1], 660), "выход", (F_SB, 30), (*GRAY, 255))


# ===========================================================================
# 7. RNN+ — обновлённый ill_rnn (params: tokens, direction, memory_steps, highlight_step)
# ===========================================================================
def ill_rnn(cv, t, col, params=None):
    p = params or {}
    tokens = list(p.get("tokens", ["Я", "иду", "в", "кино", "!"]))
    direction = p.get("direction", "forward")
    memory_steps = int(p.get("memory_steps", 0))
    hl_step = p.get("highlight_step", None)

    if not (2 <= len(tokens) <= 6):
        raise ValueError(f"ill_rnn: нужно 2–6 токенов, получено {len(tokens)}")
    if direction not in DIRECTIONS:
        raise ValueError(f"ill_rnn: direction='{direction}' не из {DIRECTIONS}")
    if not (0 <= memory_steps <= 6):
        raise ValueError(f"ill_rnn: memory_steps должно быть 0–6, получено {memory_steps}")

    n = len(tokens)
    xs = [90 + i * (810 - 90) / (n - 1) for i in range(n)]

    step_s = 0.75
    cyc = n * step_s + 1.4
    f = ((t % cyc) / step_s) - 0.3
    cy = CY - 10

    # прямые стрелки между шагами
    for i in range(n - 1):
        x0, x1 = xs[i] + 66, xs[i + 1] - 66
        arrow(cv, (x0, cy), (x1, cy), (*col, 110), 4, 14)
        p1 = (f - (i + 0.55)) / 0.9
        if 0 < p1 < 1:
            cv.circle((x0 + (x1 - x0) * p1, cy), 11, fill=(*col, 255))
    # bidirectional — обратные
    if direction == "bidirectional":
        for i in range(n - 1):
            arrow(cv, (xs[i + 1] - 66, cy - 14), (xs[i] + 66, cy - 14), (*GRAY, 160), 2, 10)

    # память: дуги назад
    for i in range(n):
        for k in range(1, memory_steps + 1):
            j = i - k
            if j < 0:
                break
            # дуга над шагами
            mid_x = (xs[i] + xs[j]) / 2
            arc_h = 30 + 30 * k
            # рисуем параболу из 12 точек
            pts = []
            for s in range(13):
                u = s / 12
                x = xs[j] + (xs[i] - xs[j]) * u
                y = cy - 70 - arc_h * math.sin(math.pi * u)
                pts.append((x, y))
            for s in range(12):
                cv.line(pts[s], pts[s + 1], (*col, 130), 2)
            # стрелка на конце (в сторону i)
            arrow(cv, pts[11], pts[12], (*col, 180), 2, 8)

    # блоки
    for i, x in enumerate(xs):
        act = f - i
        flash = max(0.0, 1 - act * 0.9) if act >= 0 else 0.0
        if hl_step is not None and i == hl_step:
            flash = max(flash, 0.8)
        level = (0.28 + 0.72 * flash) if act >= 0 else (0.4 if hl_step == i else 0.0)
        arrow(cv, (x, cy + 128), (x, cy + 70), (*GRAY, 170), 3, 11)
        cv.text((x, cy + 160), tokens[i], (F_B, 44), (*WHITE, 255))
        arrow(cv, (x, cy - 64), (x, cy - 106), (*col, 120 + int(135 * flash)), 3, 11)
        if flash > 0.05:
            glow(cv, (x, cy - 128), 16, col, flash)
        cv.circle((x, cy - 128), 16, fill=(*mix(DARK, col, flash), 255),
                  outline=(*col, 200), w=3)
        if flash > 0.05:
            glow(cv, (x, cy), 50, col, flash * 0.8)
        cv.rrect((x - 62, cy - 62, x + 62, cy + 62), 28,
                 fill=(*mix(DARK, col, level), 255),
                 outline=(*col, 255 if act >= 0 else 90), w=4)
        cv.text((x, cy), f"h{i + 1}", (F_B, 40),
                (*WHITE, 255) if act >= 0 else (*GRAY, 255))
    cv.text((450, CY + 275), "память о предыдущих шагах", (F_SB, 32), (*col, 255))


# ===========================================================================
# 8. TRF+ — обновлённый ill_trf (params: tokens, mode: graph|heatmap, highlight_token)
# ===========================================================================
_TRF_CACHE = {}

def _trf_precompute(tokens):
    key = tuple(tokens)
    if key in _TRF_CACHE:
        return _TRF_CACHE[key]
    import random as _r
    n = len(tokens)
    rt = _r.Random(11)
    aw = []
    for i in range(n):
        row = [0.0 if i == j else rt.uniform(0.15, 1.0) for j in range(n)]
        m = max(row) or 1.0
        aw.append([v / m for v in row])
    radius = 270 if n >= 4 else 240
    tpos = [(450 + radius * math.cos(math.radians(-90 + 360 * i / n)),
             CY - 15 + (radius * 0.945) * math.sin(math.radians(-90 + 360 * i / n)))
            for i in range(n)]
    _TRF_CACHE[key] = (aw, tpos)
    return aw, tpos


def ill_trf(cv, t, col, params=None):
    p = params or {}
    tokens = list(p.get("tokens", ["Кот", "сел", "на", "мягкий", "диван"]))
    mode = p.get("mode", "graph")
    hl_tok = p.get("highlight_token", None)

    if not (2 <= len(tokens) <= 6):
        raise ValueError(f"ill_trf: нужно 2–6 токенов, получено {len(tokens)}")
    if mode not in TRF_MODES:
        raise ValueError(f"ill_trf: mode='{mode}' не из {TRF_MODES}")

    AW, TPOS = _trf_precompute(tokens)
    n = len(tokens)

    if mode == "heatmap":
        _trf_heatmap(cv, t, col, tokens, AW, hl_tok)
        return

    k = int(t / 1.2) % n
    if hl_tok is not None and 0 <= hl_tok < n:
        k = hl_tok
    blend = smooth(((t % 1.2) / 1.2) / 0.35)

    for i in range(n):
        for j in range(i + 1, n):
            cv.line(TPOS[i], TPOS[j], (*col, 28), 2)
    for j in range(n):
        if j == k:
            continue
        w = AW[k][j] * blend
        cv.line(TPOS[k], TPOS[j], (*col, int(60 + 195 * w)), 3 + 11 * w)

    for i, (x, y) in enumerate(TPOS):
        w = 1.0 if i == k else AW[k][i] * blend
        wd = max(150, font(F_B, 36).getlength(tokens[i]) + 64)
        if w > 0.5:
            cv.rrect((x - wd / 2 - 8, y - 43, x + wd / 2 + 8, y + 43), 30,
                     fill=(*col, int(60 * w)))
        cv.rrect((x - wd / 2, y - 35, x + wd / 2, y + 35), 26,
                 fill=(*mix(DARK, col, 0.9 * w), 255),
                 outline=(*col, 230), w=3)
        cv.text((x, y), tokens[i], (F_B, 36), (*WHITE, 255))
    cv.text((450, CY + 330), "каждое слово смотрит на все остальные",
            (F_SB, 30), (*GRAY, 255))


def _trf_heatmap(cv, t, col, tokens, AW, hl_tok):
    n = len(tokens)
    prog = smooth(t / 0.8)
    # сетка N×N
    cell = min(80, int(500 / n))
    total = cell * n
    x0 = (CW - total) / 2
    y0 = (CH - total) / 2 - 20

    for i in range(n):
        for j in range(n):
            v = AW[i][j] if i != j else 1.0
            alpha = int(40 + 200 * v * prog)
            if hl_tok is not None and i == hl_tok:
                alpha = min(255, alpha + 40)
            fill = (*mix((20, 24, 48), col, v * prog), alpha)
            cv.rrect((x0 + j * cell + 3, y0 + i * cell + 3,
                      x0 + (j + 1) * cell - 3, y0 + (i + 1) * cell - 3),
                     8, fill=fill)
            if i == j:
                cv.rrect((x0 + j * cell + 3, y0 + i * cell + 3,
                          x0 + (j + 1) * cell - 3, y0 + (i + 1) * cell - 3),
                         8, outline=(*WHITE, 180), w=2)

    # подписи по осям
    fs = max(16, min(24, cell - 30))
    for i, tok in enumerate(tokens):
        # ось Y (слева)
        cv.text((x0 - 16, y0 + (i + 0.5) * cell), tok, (F_SB, fs), (*GRAY, 255), anchor="rm")
        # ось X (сверху)
        cv.text((x0 + (i + 0.5) * cell, y0 - 20), tok, (F_SB, fs), (*GRAY, 255), anchor="ms")

    cv.text((CW / 2, y0 + total + 50), "матрица внимания: строка → столбец",
            (F_SB, 26), (*GRAY, 255))

# ===========================================================================
# 9. OUTRO+ — финальная сцена: список типов из текущего ролика
# ===========================================================================
def ill_outro(cv, t, col, params=None):
    """Список сцен 1..N с их title и ill-ключом (вместо SHORT из shorts_creator).
    Берёт сцены из sc.SCENES (уже подменён в video_generator.install_scenes).
    Ожидает, что в SCENES есть хотя бы intro + N основных + outro."""
    scenes = sc.SCENES
    # сколько показывать: все сцены с type_index != null, максимум 6
    items = [s for s in scenes if s.get("type_index") is not None][:6]
    n = len(items)
    if n == 0:
        return

    for i, s in enumerate(items):
        e = ease_out((t - (0.3 + 0.28 * i)) / 0.45)
        if e <= 0:
            continue
        a = int(255 * e)
        c = s.get("color", col)
        # подгоняем высоту строки под количество
        row_h = 100 if n <= 5 else 84
        gap = 32 if n <= 5 else 20
        y0 = 60 + i * (row_h + gap)
        x0 = 90 + (1 - e) * 120
        cv.rrect((x0, y0, x0 + 720, y0 + row_h), 30,
                 fill=(22, 27, 54, a), outline=(*c, a), w=3)
        cv.circle((x0 + 50, y0 + row_h / 2), 30, fill=(*c, a))
        cv.text((x0 + 50, y0 + row_h / 2), str(i + 1), (F_XB, 34), (10, 12, 26, a))
        # заголовок сцены
        # заголовок сцены — фиксированный шрифт, обрезка по ширине
        title = s.get("title", "").capitalize()
        # 720 — ширина плашки, 100 — отступ слева (под номер), 20 — отступ справа        
        max_w = 720 - 100 - 20
        size_t = 44 if n <= 5 else 36
        if font(F_XB, size_t).getlength(title) > max_w:
            while (font(F_XB, size_t).getlength(title + "...") > max_w
                   and len(title) > 4):
                title = title[:-1]
            title = title.rstrip() + "..."
        cv.text((x0 + 100, y0 + row_h / 2), title, (F_XB, size_t),
                (255, 255, 255, a), anchor="lm")
        # # ключ ill справа
        # ill_name = s.get("ill", "").upper()
        # size_i = 28 if n <= 5 else 22
        # cv.text((x0 + 700, y0 + row_h / 2), ill_name, (F_SB, size_i),
        #         (*GRAY, a), anchor="rm")

# ===========================================================================
# Реестр для video_generator.build_registry
# ===========================================================================
ILL_EXTRA = {
    "graph":    ill_graph,
    "flow":     ill_flow,
    "timeline": ill_timeline,
    "tree":     ill_tree,
    "compare":  ill_compare,
    "mlp":      ill_mlp,
    "rnn":      ill_rnn,
    "trf":      ill_trf,
    "outro":    ill_outro,
}

# Алиасы (синонимы для удобства LLM)
ILL_ALIASES = {
    "chart":    "graph",
    "diagram":  "flow",
    "process":  "flow",
    "history":  "timeline",
    "decision": "tree",
    "hierarchy":"tree",
    "vs":       "compare",
    "heatmap":  "trf",
}