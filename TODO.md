Контекст: проект D:\Projects\video-generator-01 — генератор вертикальных
YouTube Shorts (1080x1920, 30 fps). Пайплайн: LLM по промпту выдаёт
content/scenes.json, video_generator.py рендерит mp4 в output/<timestamp>/.

Ключевые файлы:
- video_generator.py — оркестратор (load scenes -> apply_style -> render -> ffmpeg -> метрики)
- shorts_creator.py — движок (иллюстрации, аудио-микс, ffmpeg)
- ills_extra.py — 8 доп. иллюстраций (graph/flow/timeline/tree/compare + улучшения mlp/rnn/trf/outro)
- scenes_loader.py — загрузчик/валидатор scenes.json и presets
- content/scenes.json — текущий ролик
- content/presets/default_style.json — стиль (font_size=68, colors, audio, timing)
- content/PROMPT.md — промпт для LLM
- trim_voice.py — сканирует assets/voice/*.mp3, режет тишину в assets/voice_trimmed/*.wav

Озвучка сейчас:
- mp3 генерируются вручную в сервисе, называются <output_name>_<key>.mp3,
- кладутся в assets/voice/,
- trim_voice.py -> assets/voice_trimmed/,
- video_generator.py читает с префиксом VIDEO_ID = output_name без .mp4,
- валидатор падает до рендера, если mp3 нет.

Задача 1: добавить динамику (анимацию подсветки) в иллюстрации рендерера Shorts

Контекст. Генератор сцен выдаёт scenes.json по схеме из PROMPT.md. Иллюстрации (mlp, flow, graph, compare и др.) сейчас рисуют статичный кадр с одним highlight_* (один слой / один шаг / один столбец / одна сторона). Нужна последовательная подсветка нескольких элементов внутри одной сцены (например, слои MLP мигают по очереди, шаги flow подсвечиваются по порядку, столбцы графика — по очереди, стороны compare переключаются).

Ограничение схемы. В текущем PROMPT.md полей для этого нет. Одиночные highlight_layer / highlight_step / highlight.index / highlight_side статичны и не выражают последовательность.


Задача 2: автоматизировать TTS.
1. tts_generate.py: читает content/scenes.json, для каждой сцены берёт text,
   генерирует mp3 в assets/voice/<output_name>_<key>.mp3.
2. Пользователь выбирает провайдера (edge-tts бесплатный / ElevenLabs / OpenAI TTS).
3. trim_voice.py -> video_generator.py без изменений.
4. В будущем: mp3 хранить в output/<timestamp>/voices/, чтобы папка рендера
   была самодостаточной. Пока — assets/voice/, как сейчас.

Задача 3: Рефакторинг highlight_* -> pulse_*

Правило: при наличии pulse_* соответствующий highlight_* игнорируется.

Места в content/scenes.json (текущий shorts_mlp):
- scene "forward" (ill=flow): highlight_step: 1 — не используется (есть pulse_steps)
- scene "apply"   (ill=graph): highlight.index/label — не используется (есть pulse_bars)
- scene "limits"  (ill=compare): highlight_side: "right" — не используется (есть pulse_sides)

Задача: после стабилизации pulse_* удалить мертвые highlight_* из этих сцен.