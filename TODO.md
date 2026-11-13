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

Что нужно сделать (вариант 1 — расширение схемы):

    PROMPT.md — добавить опциональные поля в ill_params:

        mlp: pulse_layers: [int] — порядок подсветки слоёв.

        flow: pulse_steps: [int] — порядок подсветки шагов.

        graph: pulse_bars: [int] — порядок подсветки столбцов (индексы в values).

        compare: pulse_sides: ["left"|"right"] — порядок переключения сторон.

        Зафиксировать правило: если задан pulse_*, он переопределяет соответствующий одиночный highlight_*; если нет — поведение прежнее (обратная совместимость).

        Описать дефолтную длительность подшага (например, сцена делится на len(pulse_*) равных интервалов).

    Валидатор схемы — добавить новые поля в допустимые, иначе JSON будет отклонён до рендера.

    Код рендерера — для каждой затронутой иллюстрации:

        прочитать pulse_* с дефолтом (старые JSON без поля не должны падать);

        реализовать внутренний таймлайн кадров сцены: разбить длительность сцены на N подшагов, на каждом подсвечивать соответствующий элемент;

        проверить, что механика подкадров есть (если каждая сцена — один статичный кадр, потребуется добавить механизм подкадров — это основная трудоёмкость);

        убедиться, что анимация не конфликтует с озвучкой (подшаги укладываются в длительность text).

    Тест — прогнать ролик shorts_mlp.mp4 (сцена structure — mlp с pulse_layers, forward — flow с pulse_steps, apply — graph с pulse_bars, limits — compare с pulse_sides) и убедиться, что подсветка идёт последовательно и старые ролики рендерятся без изменений.

Явно вне скоупа: структура meta / style / scenes не меняется; pulse_* кладётся внутрь ill_params. Вариант «зашить динамику в рендерер без изменения JSON» и вариант «дублировать сцены» — отклонены.


Задача 2: автоматизировать TTS.
1. tts_generate.py: читает content/scenes.json, для каждой сцены берёт text,
   генерирует mp3 в assets/voice/<output_name>_<key>.mp3.
2. Пользователь выбирает провайдера (edge-tts бесплатный / ElevenLabs / OpenAI TTS).
3. trim_voice.py -> video_generator.py без изменений.
4. В будущем: mp3 хранить в output/<timestamp>/voices/, чтобы папка рендера
   была самодостаточной. Пока — assets/voice/, как сейчас.

Жду первого сообщения: обсудим провайдера и напишем tts_generate.py.