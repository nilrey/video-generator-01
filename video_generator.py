#!/usr/bin/env python3
"""Динамический движок роликов. Рендерит по content/scenes.json,
переиспользуя движок shorts_creator.py (иллюстрации, звук, ffmpeg).
Стиль (размеры шрифтов, цвета, громкость, паузы) — из content/presets/*.json.
Дополнительные иллюстрации (graph/flow/timeline/tree/compare и улучшенные
mlp/rnn/trf) подключаются из ills_extra.py."""
import sys, os, subprocess
from datetime import datetime
from pathlib import Path

import shorts_creator as sc
from scenes_loader import load_scenes, load_preset, clone
from ills_extra import ILL_EXTRA, ILL_ALIASES

PROJECT = Path(r"D:\Projects\video-generator-01")
SCENES_JSON = PROJECT / "content" / "scenes.json"
OUT_ROOT    = PROJECT / "output"

# ---------------------------------------------------------------------------
# Реестр ILL по ключу
# ---------------------------------------------------------------------------
_ILL_ORDER = ["intro", "mlp", "cnn", "rnn", "trf", "gen", "outro"]

def build_registry(data):
    assert len(_ILL_ORDER) == len(sc.ILL), "shorts_creator.ILL порядок изменился"
    base = dict(zip(_ILL_ORDER, sc.ILL))

    # переопределяем mlp/rnn/trf/outro на улучшенные версии из ills_extra
    for k in ("mlp", "rnn", "trf", "outro"):
        if k in ILL_EXTRA:
            base[k] = ILL_EXTRA[k]

    # добавляем новые типы (graph/flow/timeline/tree/compare)
    for k, fn in ILL_EXTRA.items():
        base[k] = fn

    def wrap(fn):
        if fn in (sc.ill_intro, sc.ill_gen, sc.ill_outro):
            return lambda cv, t, col, params=None: fn(cv, t, col)
        return lambda cv, t, col, params=None: fn(cv, t, col, params=params)

    reg = {k: wrap(v) for k, v in base.items()}
    reg["transformer"] = reg["trf"]
    reg["generative"]  = reg["gen"]
    # алиасы
    for alias, target in ILL_ALIASES.items():
        if target in reg:
            reg[alias] = reg[target]
    return reg

# ---------------------------------------------------------------------------
# Применение пресета: переопределяем глобалы shorts_creator через setattr.
# Отсутствующие ключи не трогаем (работают дефолты).
# ---------------------------------------------------------------------------
def apply_style(preset):
    if not preset:
        return

    cap = preset.get("caption", {})
    if "highlight_word" in cap:  sc.CAPTION_HIGHLIGHT_WORD = bool(cap["highlight_word"])
    if "font_size"      in cap:  sc.CAPF_SIZE       = int(cap["font_size"])
    if "max_width"      in cap:  sc.CAP_MAXW        = int(cap["max_width"])
    if "base_y"         in cap:  sc.CAP_BASE        = int(cap["base_y"])
    if "line_gap"       in cap:  sc.GAP             = int(cap["line_gap"])
    if "color_text"     in cap:  sc.CAP_COLOR_TEXT  = tuple(cap["color_text"])
    if "color_bg"       in cap:  sc.CAP_COLOR_BG    = tuple(cap["color_bg"])
    if "stroke_width"   in cap:  sc.CAP_STROKE_W    = int(cap["stroke_width"])
    if "stroke_fill"    in cap:  sc.CAP_STROKE_FILL = tuple(cap["stroke_fill"])

    tt = preset.get("title", {})
    if "height"             in tt: sc.TITLE_H          = int(tt["height"])
    if "dot_step"           in tt: sc.TITLE_DOT_STEP   = int(tt["dot_step"])
    if "dot_y"              in tt: sc.TITLE_DOT_Y      = tuple(tt["dot_y"])
    if "counter_y"          in tt: sc.TITLE_COUNTER_Y  = int(tt["counter_y"])
    if "title_y"            in tt: sc.TITLE_TITLE_Y    = int(tt["title_y"])
    if "tag_y"              in tt: sc.TITLE_TAG_Y      = int(tt["tag_y"])
    if "font_size_counter"  in tt: sc.TITLE_FS_COUNTER = int(tt["font_size_counter"])
    if "font_size_title"    in tt: sc.TITLE_FS_TITLE   = int(tt["font_size_title"])
    if "font_size_tag"      in tt: sc.TITLE_FS_TAG     = int(tt["font_size_tag"])
    if "max_title_width"    in tt: sc.TITLE_MAXW       = int(tt["max_title_width"])
    if "color_tag"          in tt: sc.TITLE_COLOR_TAG  = tuple(tt["color_tag"])
    if "color_dot_dim"      in tt: sc.TITLE_DOT_DIM    = tuple(tt["color_dot_dim"])

    il = preset.get("illustration", {})
    if "pos_x" in il or "pos_y" in il:
        x = il.get("pos_x", sc.ILL_POS[0])
        y = il.get("pos_y", sc.ILL_POS[1])
        sc.ILL_POS = (int(x), int(y))
    if "canvas_w"  in il: sc.CW = int(il["canvas_w"])
    if "canvas_h"  in il: sc.CH = int(il["canvas_h"])
    if "canvas_cy" in il: sc.CY = int(il["canvas_cy"])

    au = preset.get("audio", {})
    if "target_lufs" in au: sc.TARGET_LUFS = float(au["target_lufs"])
    if "target_tp"   in au: sc.TARGET_TP   = float(au["target_tp"])
    if "floor_db"    in au: sc.FLOOR_DB    = float(au["floor_db"])
    if "music_gain"  in au: sc.MUSIC_GAIN  = float(au["music_gain"])
    if "voice_dir"   in au: sc.VOICE_DIR   = str(au["voice_dir"])
    if "voice_ext"   in au: sc.VOICE_EXT   = str(au["voice_ext"])

    ti = preset.get("timing", {})
    if "lead_s"      in ti: sc.LEAD        = float(ti["lead_s"])
    if "tail_s"      in ti: sc.TAIL        = float(ti["tail_s"])
    if "speech_rate" in ti: sc.SPEECH_RATE = float(ti["speech_rate"])

    co = preset.get("colors", {})
    if "bg_top"    in co: sc.BG_TOP     = tuple(co["bg_top"])
    if "bg_bot"    in co: sc.BG_BOT     = tuple(co["bg_bot"])
    if "dark"      in co: sc.DARK       = tuple(co["dark"])
    if "gray"      in co: sc.GRAY       = tuple(co["gray"])
    if "decor_dot" in co: sc.DECOR_DOT  = tuple(co["decor_dot"])

# ---------------------------------------------------------------------------
# Подмена SCENES / SPEECH_RATE
# ---------------------------------------------------------------------------
def install_scenes(scenes):
    sc.SCENES = scenes
    return scenes

def build_timeline_scoped(scenes, speech_rate=1.0):
    data = clone({"scenes": scenes})
    saved_scenes = sc.SCENES
    saved_rate   = sc.SPEECH_RATE
    try:
        sc.SCENES = data["scenes"]
        sc.SPEECH_RATE = float(speech_rate)
        total = sc.build_timeline()
        return total, data["scenes"]
    finally:
        sc.SCENES = saved_scenes
        sc.SPEECH_RATE = saved_rate

# ---------------------------------------------------------------------------
# build_title_dyn
# ---------------------------------------------------------------------------
def build_title_dyn(scene, idx, total):
    W = sc.W
    col = scene["color"]
    L = sc.Image.new("RGBA", (W, sc.TITLE_H), (0, 0, 0, 0))
    d = sc.ImageDraw.Draw(L)

    if total > 0:
        x0 = W / 2 - (total - 1) * sc.TITLE_DOT_STEP / 2
        for i in range(total):
            x = x0 + i * sc.TITLE_DOT_STEP
            if i == idx:
                d.ellipse([x - 15, sc.TITLE_DOT_Y[0], x + 15, sc.TITLE_DOT_Y[1]], fill=col)
            elif i < idx:
                d.ellipse([x - 10, sc.TITLE_DOT_Y[0] + 5, x + 10, sc.TITLE_DOT_Y[1] - 5],
                          fill=(*col, 130))
            else:
                d.ellipse([x - 10, sc.TITLE_DOT_Y[0] + 5, x + 10, sc.TITLE_DOT_Y[1] - 5],
                          fill=(*sc.TITLE_DOT_DIM, 255))

    size = sc.TITLE_FS_TITLE
    while sc.font(sc.F_XB, size).getlength(scene["title"]) > sc.TITLE_MAXW:
        size -= 4
    d.text((W / 2, sc.TITLE_TITLE_Y), scene["title"],
           font=sc.font(sc.F_XB, size), fill=(255, 255, 255), anchor="ms")
    d.text((W / 2, sc.TITLE_TAG_Y), scene["tag"],
           font=sc.font(sc.F_SB, sc.TITLE_FS_TAG), fill=sc.TITLE_COLOR_TAG, anchor="ms")
    return L


# ---------------------------------------------------------------------------
# Рендер кадров
# ---------------------------------------------------------------------------
def render(scenes, registry):
    BG, TITLE = [], []
    for i, scene in enumerate(scenes):
        sc.layout_caption(scene)
        BG.append(sc.make_bg(scene["color"]))
        TITLE.append(build_title_dyn(scene, i, len(scenes)))

    def scene_at(t):
        for i, s in enumerate(scenes):
            if t < s["end"]:
                return i
        return len(scenes) - 1

    def make_frame(t):
        si = scene_at(t)
        scene = scenes[si]
        lt = t - scene["start"]
        fr = BG[si].copy()

        e = sc.ease_out(lt / 0.45)
        L = TITLE[si]
        if e < 1:
            L = L.copy()
            L.putalpha(L.getchannel("A").point(lambda v, e=e: int(v * e)))
        fr.paste(L, (0, 130 + int((1 - e) * 45)), L)

        cv = sc.Cv()
        fn = registry[scene["ill"]]
        fn(cv, lt, scene["color"], scene.get("ill_params", {}))
        im = cv.out()
        e2 = sc.ease_out((lt - 0.1) / 0.5)
        if e2 < 1:
            im.putalpha(im.getchannel("A").point(lambda v, e2=e2: int(v * e2)))
        fr.paste(im, sc.ILL_POS, im)

        sc.draw_caption(fr, scene, t)
        return fr

    return make_frame


# ---------------------------------------------------------------------------
# Аудио и ffmpeg
# ---------------------------------------------------------------------------
def render_audio(scenes, total, out_dir):
    music = sc.make_music(total)
    mix   = sc.mix_voice_and_music(total, music)
    raw   = os.path.join(out_dir, "audio_raw.wav")
    final = os.path.join(out_dir, "audio_final.wav")
    sc.write_wav(raw, mix)
    sc.normalize_lufs(raw, final)
    return final

def encode_video(make_frame, audio_path, total, out_path):
    W, H, FPS = sc.W, sc.H, sc.FPS
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-t", f"{total:.3f}", "-movflags", "+faststart", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nframes = int(total * FPS)
    for i in range(nframes):
        p.stdin.write(make_frame(i / FPS).tobytes())
        if i % 150 == 0:
            print(f"кадр {i}/{nframes}", flush=True)
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg вернул код {p.returncode}")

# ---------------------------------------------------------------------------
def main():
    import time
    t_start = time.time()
    stills = "--stills" in sys.argv

    data   = load_scenes(SCENES_JSON)
    meta   = data["meta"]
    scenes = data["scenes"]
    out_name = meta["output_name"]
    video_id = os.path.splitext(out_name)[0]

    preset = load_preset(data["style_path"])
    apply_style(preset)

    sr = preset.get("timing", {}).get("speech_rate", meta["speech_rate"])

    registry = build_registry(data)
    for s in scenes:
        if s["ill"] not in registry:
            raise KeyError(f"scene '{s['key']}': ill='{s['ill']}' не найден. "
                           f"Доступно: {sorted(set(registry))}")

    # префикс озвучки = output_name без расширения
    sc.VIDEO_ID = video_id

    # валидация: все mp3 для сцен существуют (кроме --stills)
    if not stills:
        missing = []
        for s in scenes:
            vp = sc.voice_path(s["key"])
            if not os.path.exists(vp):
                missing.append(f"{s['key']} -> {vp}")
        if missing:
            print("ОШИБКА: не найдены файлы озвучки для сцен:")
            for m in missing:
                print("  " + m)
            print(f"Сгенерируй mp3 с префиксом '{video_id}_' в {sc.VOICE_DIR}")
            sys.exit(1)

    total, scenes = build_timeline_scoped(scenes, sr)
    print(f"Длительность: {total:.1f} сек, слов: {sum(len(s['words']) for s in scenes)}")
    print(f"Пресет: {data['style_path']} ({'загружен' if preset else 'не найден, дефолты'})")
    print(f"Типов ill в реестре: {len(registry)}")
    print(f"VIDEO_ID: {video_id}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_stills" if stills else ""
    out_dir = OUT_ROOT / (ts + suffix)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Папка вывода: {out_dir}")

    sc.OUT_DIR = str(out_dir)
    install_scenes(scenes)

    make_frame = render(scenes, registry)

    if stills:
        STILLS = out_dir / "stills"
        STILLS.mkdir(exist_ok=True)
        thumbs = []
        for si, s in enumerate(scenes):
            frac = 0.7
            fr = make_frame(s["start"] + (s["end"] - s["start"]) * frac)
            fr.save(STILLS / f"{si}_{s['key']}.png")
            thumbs.append(fr.resize((405, 720)))
        rows = (len(thumbs) + 3) // 4
        sheet = sc.Image.new("RGB", (405 * 4, 720 * rows), (0, 0, 0))
        for i, th in enumerate(thumbs):
            sheet.paste(th, ((i % 4) * 405, (i // 4) * 720))
        sheet.save(STILLS / "sheet.png")
        print("Кадры сохранены в:", STILLS)
        return

    audio = render_audio(scenes, total, out_dir)
    out_path = os.path.join(out_dir, out_name)
    encode_video(make_frame, audio, total, out_path)

    sc.write_texts(total)
    print("Готово:", out_path)

    # метрики
    elapsed = time.time() - t_start
    print(f"Время ролика:    {total:5.1f} сек")
    print(f"Время сборки:    {elapsed:5.1f} сек")

if __name__ == "__main__":
    main()