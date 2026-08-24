#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CHANNELS = [
    "mrnadzor",
    "KIRILLPRIEMKA",
    "tehpriemka",
    "specnovostroy_ch",
    "revizor_priemka",
    "priemka_moscow",
    "pro_smarent",
    "iliilitop",
    "cityprofmsk",
    "nikita_ooobrik",
    "expert_novostroy",
    "moydom_estate",
    "sudex",
    "priemka_komandask",
    "priemka_krd",
]

INSPECTION_CHANNELS = {"mrnadzor", "KIRILLPRIEMKA", "tehpriemka", "specnovostroy_ch", "revizor_priemka", "priemka_moscow", "cityprofmsk", "nikita_ooobrik", "expert_novostroy", "sudex", "priemka_komandask", "priemka_krd"}
ENRICHMENT_CHANNELS = {"pro_smarent", "iliilitop", "moydom_estate"}
MOSCOW = ZoneInfo("Europe/Moscow")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def clean_text(value: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .")
    value = re.sub(r"[☎📞].*", "", value).strip()
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def source_type(channel: str) -> str:
    if channel in ENRICHMENT_CHANNELS:
        return "обогащение / рынок"
    return "приёмка / технадзор"


def concrete_label(score: int) -> str:
    if score >= 6:
        return "МНОГО КОНКРЕТИКИ"
    if score >= 3:
        return "ЕСТЬ КОНКРЕТИКА"
    return "МАЛО КОНКРЕТИКИ"


def score_item(item: dict) -> int:
    score = 0
    if item.get("residential_complexes"):
        score += 2
    if item.get("developers"):
        score += 2
    if item.get("defect_counts"):
        score += 2
    details = item.get("distinctive_details") or []
    score += min(len(details), 4)
    cats = item.get("categories") or []
    score += min(len(cats), 3)
    if item.get("stage") in {"суд", "гарантия", "выдача ключей"}:
        score += 1
    if item.get("source_channel") in ENRICHMENT_CHANNELS:
        score -= 2
    return max(score, 0)


def item_title(item: dict) -> str:
    rc = item.get("residential_complexes") or []
    dev = item.get("developers") or []
    if rc:
        return "ЖК «" + ", ".join(rc[:2]) + "»"
    if dev:
        return ", ".join(dev[:3])
    return item.get("post_id") or "сигнал"


def first_detail(item: dict) -> str:
    details = [clean_text(x, 160) for x in (item.get("distinctive_details") or []) if clean_text(x)]
    if details:
        return details[0]
    summary = clean_text(item.get("summary") or item.get("raw_text") or "", 160)
    return summary or "деталь в первоисточнике"


def process_insight(item: dict, idx: int) -> tuple[list[str], str]:
    stage = item.get("stage") or ""
    cats = set(item.get("categories") or [])
    counts = item.get("defect_counts") or []
    details = item.get("distinctive_details") or []
    channel = item.get("source_channel") or ""
    date = parse_dt(item.get("date"))
    date_hint = date.astimezone(MOSCOW).strftime("%d.%m.%Y") if date else "без даты"
    source_hint = f"@{channel}" if channel else "первоисточник"
    source_hint = f"{source_hint} от {date_hint}"
    title = item_title(item)
    dev = ", ".join(item.get("developers") or [])
    subject = title if title != "сигнал" else (dev or "этот сигнал")
    detail = first_detail(item)
    detail_sentence = f"Фрагмент из карточки: {detail}."

    if counts and max(counts) >= 60:
        return ["#много_замечаний", "#ручная_координация"], f"{max(counts)} пунктов — это уже не один акт, а мини-проект по закрытию замечаний. Сначала группировка по зонам и исполнителям, потом повторная проверка. {detail_sentence}"
    if counts and max(counts) >= 20:
        return ["#очередь_дефектов", "#повторная_приёмка"], f"{max(counts)} дефектов превращают приемку в очередь работ. Хороший след здесь — не общий статус «исправим», а список: что закрыто сразу, что ушло подрядчику и что осталось после второго осмотра."
    if stage == "суд":
        variants = [
            (["#судебный_след", "#доказательства"], f"Судебная стадия — это проверка архива по замечанию. Нужны даты, акт, фото, экспертиза или переписка; без них спор быстро превращается в пересказ событий. {detail_sentence}"),
            (["#спор_после_приёмки", "#след_документов"], f"Для {subject} важен путь до претензии: когда дефект заметили, что обещали исправить, где появился отказ или расхождение. Проверять нужно не общий ярлык «суд», а цепочку документов и осмотров."),
            (["#юридический_хвост", "#история_замечания"], f"Пост {source_hint} лучше читать как историю одного замечания после приемки. Что было в акте, что исправляли, что не приняли повторно — именно эти точки потом становятся доказательной базой."),
            (["#суд", "#ручная_проверка"], f"Юридический маркер в карточке сильный, но его нужно разбирать руками: предмет претензии, документы и результат спора. Без этих атомов лучше не усиливать вывод по {subject}."),
            (["#претензия", "#архив_приёмки"], f"Здесь полезен не пересказ конфликта, а архив приемки: исходное замечание, повторный осмотр, ответ застройщика и итог. {detail_sentence}"),
        ]
        return variants[idx % len(variants)]
    if stage == "гарантия":
        variants = [
            (["#гарантийный_хвост", "#повтор_дефекта"], f"Гарантийная карточка должна отвечать на простой вопрос: это новый дефект или старый пункт, который вернулся? Без истории закрытия команда спорит не о ремонте, а о памяти процесса."),
            (["#после_ключей", "#контроль_возврата"], f"После выдачи ключей ценность дает не красивый акт, а способность поднять старое замечание: кто принял, что обещали, когда проверяли и почему тема снова открылась."),
        ]
        return variants[idx % len(variants)]
    if stage == "выдача ключей":
        return ["#выдача_ключей", "#поток_замечаний"], f"На выдаче опасен не один дефект, а параллельный поток квартир, актов и обещаний. Если статусы разъезжаются по чатам, повторный визит начинается с вопроса «а что мы уже закрыли?»"
    if "вентиляция" in cats or "сантехника/санузлы" in cats:
        variants = [
            (["#инженерный_узел", "#проверка_результата"], f"Инженерные замечания нельзя закрывать только фотографией «после». Нужна проверка функции: течет или нет, тянет или нет, держит ли узел после исправления. {detail_sentence}"),
            (["#сантехника", "#замер_после_исправления"], f"Если в карточке сантехника или вентиляция, слабое место — подтверждение результата. Важно не кто написал «готово», а кто проверил узел и чем это зафиксировано."),
            (["#инженерка", "#не_косметика"], f"Такой дефект не закрывается визуальным осмотром. Для инженерки нужен контрольный признак: замер, повторный запуск, отсутствие течи/запаха/обратной тяги, подпись ответственного."),
        ]
        return variants[idx % len(variants)]
    if "геометрия/отклонения" in cats:
        return ["#замеры_и_нормы", "#геометрия"], f"По {subject} важны не общие слова про качество, а измеримая часть сигнала. Когда есть отклонения, спор должен опираться на место, норму, замер и повторную фиксацию после исправления. Без этого цифры быстро превращаются в переписку."
    if "окна/стеклопакеты/откосы" in cats:
        variants = [
            (["#оконный_узел", "#монтаж"], f"Окна редко живут одним пунктом: рядом идут профиль, откос, фурнитура, герметизация. Если такие замечания повторяются, это уже вопрос к монтажному узлу, а не к одной квартире."),
            (["#окна", "#серия_замечаний"], f"Для оконного сюжета важна повторяемость. Одна створка — частный дефект; одинаковые замечания по откосам или фурнитуре — повод смотреть серию по корпусу и подрядчику."),
        ]
        return variants[idx % len(variants)]
    if "смета/объемы/договор/скрытые работы" in cats:
        variants = [
            (["#скрытые_работы", "#контроль_слоя"], f"Скрытые работы требуют фиксации до того, как слой закрыли. Иначе через неделю остается только спор: было сделано или нет. В карточке важны фото до/после, ответственный и основание для приемки результата."),
            (["#подрядчик", "#объём_работ"], f"В {subject} тема объемов или подрядчика упирается в подтверждение выполненной работы. Кто принял объем, на каком основании и что считается закрытием пункта."),
            (["#ремонтный_контур", "#предписание"], f"Здесь полезно отделить приемочный дефект от ремонтной задачи. Для ремонта нужен не общий комментарий, а предписание: что переделать, кто делает, до какого срока и как принимают результат."),
            (["#скрытый_слой", "#фотофиксация"], f"Если работа закрывается слоем отделки, спор потом почти невозможно разобрать без фотофиксации. Для {subject} главный вопрос — что сохранилось до закрытия слоя и кто принял результат."),
            (["#граница_ремонта", "#ответственный"], f"Сюжет по {subject} похож на границу между приемкой и ремонтом: дефект нашли, но дальше нужна задача для исполнителя. Важны срок, ответственный и критерий, по которому пункт считается закрытым."),
        ]
        return variants[idx % len(variants)]
    if channel in ENRICHMENT_CHANNELS:
        return ["#рыночный_фон", "#слабее_как_доказательство"], f"Этот сигнал по {subject} полезен как фон, но слабее как доказательство дефектов. Его стоит держать отдельно от прямой приемки: он помогает видеть контекст вокруг объекта или девелопера, но не должен превращаться в обвинительную карточку."
    if details:
        return ["#проверяемая_конкретика", "#журнал_замечаний"], f"В {subject} ценен сам предмет сигнала: {detail}. Это уже можно положить в журнал не как эмоцию, а как проверяемую запись: где найдено, к какой категории относится и появлялось ли похожее рядом по объекту."
    variants = [
        (["#слабый_сигнал", "#наблюдать"], f"По {subject} пока мало фактуры для сильного вывода. Но запись из {source_hint} полезно оставить: если рядом появятся новые посты по тому же объекту, слабая карточка станет частью общей картины."),
        (["#первичный_след", "#нужна_проверка"], f"Сигнал по {subject} пока больше похож на точку для наблюдения. Здесь рано делать выводы, зато у {source_hint} есть дата и ссылка, к которым можно вернуться при повторе сюжета."),
        (["#фон_объекта", "#без_обобщений"], f"У {subject} недостаточно деталей, чтобы говорить о процессе уверенно. Лучше оставить пост из {source_hint} как аккуратный фон объекта, без обобщений и без попытки достроить недостающие факты."),
    ]
    return variants[idx % len(variants)]


def select_items(items: list[dict], start: datetime, end: datetime, limit: int) -> list[dict]:
    fresh = []
    for item in items:
        d = parse_dt(item.get("date"))
        if d and start <= d <= end:
            item = dict(item)
            item["_score"] = score_item(item)
            fresh.append(item)
    fresh.sort(key=lambda x: (x["_score"], x.get("date") or "", x.get("post_id") or ""), reverse=True)
    # public page should not be dominated by weak enrichment-only rows
    selected = [x for x in fresh if x["_score"] >= 3][:limit]
    if len(selected) < min(limit, len(fresh)):
        selected += [x for x in fresh if x not in selected][: limit - len(selected)]
    selected.sort(key=lambda x: (x.get("date") or "", x.get("post_id") or ""), reverse=True)
    return selected


def channel_links(channels: list[str]) -> str:
    parts = []
    for ch in sorted(channels, key=str.lower):
        parts.append(f'<a href="https://t.me/s/{html.escape(ch)}" target="_blank" rel="noreferrer">@{html.escape(ch)}</a>')
    return ", ".join(parts)


def build_html(items: list[dict], all_items: list[dict], all_window: list[dict], start: datetime, end: datetime, generated_at: datetime, last_signal: datetime | None, fetched_total: int | None) -> str:
    channels = CHANNELS
    by_stage = Counter(i.get("stage") or "не классифицировано" for i in items)
    by_cat = Counter(c for i in items for c in (i.get("categories") or []))
    rc_count = sum(1 for i in all_window if i.get("residential_complexes"))
    dev_count = sum(1 for i in all_window if i.get("developers"))
    high_count = sum(1 for i in items if score_item(i) >= 6)
    period = f"{start.astimezone(MOSCOW).strftime('%d.%m.%Y')} — {end.astimezone(MOSCOW).strftime('%d.%m.%Y')}"
    last_signal_text = last_signal.astimezone(MOSCOW).strftime('%d.%m.%Y') if last_signal else "не найден"
    update_text = generated_at.astimezone(MOSCOW).strftime("ОТКРЫТЫЕ ИСТОЧНИКИ · ОБНОВЛЕНО %d.%m.%Y В 05:00 МСК")
    viewed_total = fetched_total or len(all_items)

    cards = []
    rows = []
    for n, item in enumerate(items, 1):
        score = score_item(item)
        label = concrete_label(score)
        title = item_title(item)
        ch = item.get("source_channel") or ""
        date = parse_dt(item.get("date"))
        date_s = date.astimezone(MOSCOW).strftime('%d.%m.%Y') if date else "без даты"
        details = [clean_text(x, 260) for x in (item.get("distinctive_details") or []) if clean_text(x)]
        if not details:
            details = [clean_text(item.get("summary") or item.get("raw_text") or "См. первоисточник.", 260)]
        detail_html = "".join(f"<li>{html.escape(d)}</li>" for d in details[:4])
        cats = item.get("categories") or []
        cat_html = "".join(f"<span>{html.escape(c)}</span>" for c in cats[:5])
        counts = item.get("defect_counts") or []
        stage = item.get("stage") or "не классифицировано"
        pattern_tags, note = process_insight(item, n)
        pattern_html = "".join(f"<span>{html.escape(tag)}</span>" for tag in pattern_tags)
        link = item.get("link") or f"https://t.me/s/{ch}"
        rc = ", ".join(item.get("residential_complexes") or []) or "не указан"
        dev = ", ".join(item.get("developers") or []) or "не указан"
        cards.append(f"""
<article class="signal" data-high="{'1' if score >= 6 else '0'}" data-rc="{'1' if item.get('residential_complexes') else '0'}" data-dev="{'1' if item.get('developers') else '0'}" data-legal="{'1' if stage in {'суд','гарантия'} else '0'}">
  <div class="cardtop"><b>СИГНАЛ #{n:03d}</b><span>{label}</span></div>
  <h3>{html.escape(title)}</h3>
  <p class="source"><a href="{html.escape(link)}" target="_blank" rel="noreferrer">@{html.escape(ch)}</a> · {date_s} · {source_type(ch)}</p>
  <div class="meta"><span>{html.escape(stage.upper())}</span><span>ЖК: {html.escape(rc)}</span><span>Застройщик: {html.escape(dev)}</span><span>Замечаний: {html.escape(', '.join(map(str, counts)) or 'не указано')}</span></div>
  <ul class="details">{detail_html}</ul>
  <div class="tags">{cat_html}</div>
  <details><summary>Что видно за дефектом</summary><div class="pattern-tags">{pattern_html}</div><p>{html.escape(note)}</p></details>
</article>
""")
        rows.append(f"<tr><td>#{n:03d}</td><td>{date_s}</td><td>{html.escape(title)}</td><td>{html.escape(dev)}</td><td>{html.escape(stage)}</td><td>{html.escape(label)}</td><td><a href=\"{html.escape(link)}\" target=\"_blank\" rel=\"noreferrer\">источник</a></td></tr>")

    stage_rows = ''.join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in by_stage.most_common())
    cat_rows = ''.join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in by_cat.most_common(12))
    catalog_rows = ''.join(rows)
    cards_html = ''.join(cards)

    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Базис - Сигналы</title><meta property="og:title" content="Базис - Сигналы"><meta name="twitter:title" content="Базис - Сигналы"><style>
:root{{--bg:#f6eedc;--panel:#fff8e8;--ink:#1b1712;--muted:#6f6658;--line:#16120e;--gold:#d7a83f;--honey:#f1c75b;--mint:#9adbcb;--red:#d75a3a;--gray:#d8cdb9;--shadow:rgba(27,23,18,.12);--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:radial-gradient(circle at 20% 0,rgba(241,199,91,.28),transparent 26rem),var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;padding:28px 18px 80px}}.wrap{{max-width:1180px;margin:auto}}.shell,.panel,.signal{{border:1.5px solid var(--line);background:var(--panel);box-shadow:8px 8px 0 var(--shadow)}}.titlebar{{height:34px;border-bottom:1.5px solid var(--line);background:linear-gradient(90deg,var(--honey),#ffe9a3);display:flex;align-items:center;justify-content:space-between;padding:0 12px;font-family:var(--mono);font-size:12px}}.hero{{padding:30px}}h1{{font-size:clamp(42px,8vw,86px);letter-spacing:-.06em;line-height:.9;margin:8px 0 16px}}h2{{font-family:var(--mono);font-size:18px;text-transform:uppercase;margin:0 0 12px;display:flex;justify-content:space-between;gap:10px}}h2 a,.top-float{{font-size:12px;color:var(--ink)}}.top-float{{position:fixed;right:18px;bottom:18px;background:var(--honey);border:1.5px solid var(--line);padding:8px 10px;z-index:10;box-shadow:4px 4px 0 var(--shadow);text-decoration:none}}.lead{{max-width:760px;font-size:18px}}.note{{border:1px dashed var(--line);background:#fff3cb;padding:10px 12px;max-width:820px}}.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:24px}}.stat{{border:1.5px solid var(--line);padding:12px;background:#fffef7}}.stat b{{font-size:30px}}.stat span{{display:block;font-family:var(--mono);font-size:11px;text-transform:uppercase}}.funnel{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px;max-width:900px}}.step{{border:1px dashed var(--line);background:#fff3cb;padding:8px 10px;font-family:var(--mono);font-size:11px}}.step b{{display:block;font-family:var(--sans);font-size:22px;line-height:1;color:var(--ink)}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}}nav a,.btn{{border:1.5px solid var(--line);background:var(--mint);padding:8px 10px;color:var(--ink);text-decoration:none;font-family:var(--mono);font-size:12px}}.layout{{display:grid;grid-template-columns:250px 1fr;gap:18px;align-items:start}}aside{{position:sticky;top:14px}}.panel{{padding:14px;margin-bottom:18px}}.panel p{{margin:8px 0;color:var(--muted)}}label{{display:block;margin:8px 0;font-family:var(--mono);font-size:12px}}button{{font:inherit;cursor:pointer}}.status{{font-family:var(--mono);font-size:11px;background:#fff;border:1px solid var(--line);padding:7px;margin-top:8px}}section{{margin-bottom:22px;scroll-margin-top:16px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.signal{{padding:14px;overflow:hidden}}.cardtop{{display:flex;justify-content:space-between;gap:8px;align-items:center;font-family:var(--mono);font-size:11px}}.cardtop span,.meta span,.tags span{{border:1px solid var(--line);background:var(--honey);padding:3px 6px}}.signal h3{{font-size:24px;line-height:1.05;margin:12px 0 8px}}.source{{font-family:var(--mono);font-size:12px;color:var(--muted)}}a{{color:#4d2d00;text-underline-offset:3px}}.meta,.tags,.pattern-tags{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0;font-size:12px}}.tags span{{background:#fff}}.pattern-tags span{{border:1px solid var(--line);background:var(--mint);padding:3px 6px;font-family:var(--mono);font-size:11px}}.details{{padding-left:20px}}details{{border-top:1px dashed var(--line);margin-top:10px;padding-top:10px}}summary{{cursor:pointer;font-family:var(--mono);background:#fff4c7;border:1px solid var(--line);padding:7px;width:max-content;max-width:100%}}details p{{background:#fff;border:1px solid var(--line);padding:10px;margin:10px 0 0}}table{{border-collapse:collapse;width:100%;background:#fff}}td,th{{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}th{{background:var(--honey);font-family:var(--mono);font-size:12px}}.small{{font-size:13px;color:var(--muted)}}@media(max-width:860px){{body{{padding:12px 10px 70px}}.layout{{grid-template-columns:1fr}}aside{{position:static}}.grid,.stats,.funnel{{grid-template-columns:1fr}}h1{{font-size:52px}}table{{font-size:12px}}}}
</style></head><body id="top"><a href="#top" class="top-float" aria-label="Вернуться наверх">↑ наверх</a><div class="wrap"><header class="shell"><div class="titlebar"><strong>basis_signal.exe</strong><span>public · open sources</span></div><div class="hero"><p class="small">{update_text}</p><h1>Базис - Сигналы</h1><p class="lead">Публичные наблюдения из открытых источников: ЖК, застройщики, конкретные замечания, стадии и процессный смысл за дефектом.</p><p class="note">Не рейтинг застройщиков и не утверждение о системных проблемах. Каждая карточка ведёт к первоисточнику.</p><div class="stats"><div class="stat"><b>{len(all_window)}</b><span>сигналов за 14 дней</span></div><div class="stat"><b>{len(channels)}</b><span>источников</span></div><div class="stat"><b>{rc_count}</b><span>с ЖК</span></div><div class="stat"><b>{high_count}</b><span>много конкретики</span></div></div><div class="funnel" aria-label="Воронка отбора"><div class="step"><b>{viewed_total}</b>публикаций просмотрено</div><div class="step"><b>{len(all_items)}</b>распознано</div><div class="step"><b>{len(all_window)}</b>сигналов за 14 дней</div><div class="step"><b>{len(items)}</b>на витрине</div></div></div></header><nav><a href="#radar">Радар сегодня</a><a href="#week">Сюжеты недели</a><a href="#catalog">Картотека ЖК</a><a href="#painmap">Карта болей</a><a href="#journal">Журнал сигналов</a><a href="#sources">Источники</a></nav><div class="layout"><aside><div class="panel"><p><b>ФИЛЬТР</b></p><label><input type="checkbox" id="fHigh"> больше всего конкретики</label><label><input type="checkbox" id="fRc"> есть ЖК</label><label><input type="checkbox" id="fDev"> есть застройщик</label><label><input type="checkbox" id="fLegal"> гарантия / суд</label><button class="btn" id="reset">сбросить</button><div id="filterStatus" class="status">Фильтр применяется сразу · показано {len(items)} из {len(items)}</div></div><div class="panel"><p><b>ПЕРИОД ДАННЫХ</b></p><p>{period}</p><p class="small">Последний найденный сигнал: {last_signal_text}</p></div><div class="panel"><p><b>КАНАЛЫ</b></p><p>{channel_links(channels)}</p></div></aside><main><section id="radar" class="panel"><h2>Радар сегодня <a href="#top">↑ наверх</a></h2><p>Последние отобранные сигналы за 14 дней. На главной не все найденные посты, а карточки, где есть больше всего конкретики.</p><div class="grid">{cards_html}</div></section><section id="week" class="panel"><h2>Сюжеты недели <a href="#top">↑ наверх</a></h2><table><tr><th>Стадия</th><th>Карточек</th></tr>{stage_rows}</table></section><section id="catalog" class="panel"><h2>Картотека ЖК <a href="#top">↑ наверх</a></h2><table><tr><th>#</th><th>Дата</th><th>Объект</th><th>Застройщик</th><th>Стадия</th><th>Конкретика</th><th>Ссылка</th></tr>{catalog_rows}</table></section><section id="painmap" class="panel"><h2>Карта болей <a href="#top">↑ наверх</a></h2><table><tr><th>Категория</th><th>Сигналов</th></tr>{cat_rows}</table></section><section id="journal" class="panel"><h2>Журнал сигналов <a href="#top">↑ наверх</a></h2><p>Каждый ежедневный прогон сохраняет лёгкий снимок данных: последний JSON для сайта и сжатый архив по дням. Сырые HTML-страницы и медиа не хранятся.</p></section><section id="sources" class="panel"><h2>Источники <a href="#top">↑ наверх</a></h2><p>Используются публичные Telegram web previews. Каналы приёмки и технадзора отделяются от рыночного обогащения.</p><p>{channel_links(channels)}</p></section></main></div></div><script>
const boxes=[fHigh,fRc,fDev,fLegal]; const cards=[...document.querySelectorAll('.signal')];
function applyFilters(){{let shown=0; const active=[]; cards.forEach(card=>{{let ok=true; if(fHigh.checked){{ok=ok&&card.dataset.high==='1';}} if(fRc.checked){{ok=ok&&card.dataset.rc==='1';}} if(fDev.checked){{ok=ok&&card.dataset.dev==='1';}} if(fLegal.checked){{ok=ok&&card.dataset.legal==='1';}} card.style.display=ok?'block':'none'; if(ok) shown++;}}); if(fHigh.checked) active.push('больше всего конкретики'); if(fRc.checked) active.push('есть ЖК'); if(fDev.checked) active.push('есть застройщик'); if(fLegal.checked) active.push('гарантия / суд'); filterStatus.textContent=(active.length?'Активно: '+active.join(' · '):'Фильтр применяется сразу')+' · показано '+shown+' из '+cards.length;}}
boxes.forEach(b=>b.addEventListener('change',applyFilters)); reset.addEventListener('click',()=>{{boxes.forEach(b=>b.checked=false); applyFilters();}});
</script></body></html>"""


def write_data_files(items: list[dict], all_items: list[dict], all_window: list[dict], outdir: Path, generated_at: datetime, keep_days: int, fetched_total: int | None) -> None:
    data = outdir / "data"
    archive = data / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": generated_at.isoformat(),
        "timezone": "Europe/Moscow",
        "window_days": 14,
        "fetched_total": fetched_total,
        "normalized_total": len(all_items),
        "items_on_page": items,
        "all_window_items": all_window,
    }
    (data / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    min_items = []
    for item in items:
        min_items.append({k: item.get(k) for k in ["source_channel", "post_id", "date", "link", "residential_complexes", "developers", "stage", "categories", "defect_counts", "distinctive_details"]})
    (data / "latest.min.json").write_text(json.dumps({"generated_at": generated_at.isoformat(), "fetched_total": fetched_total, "normalized_total": len(all_items), "window_total": len(all_window), "displayed_total": len(items), "items": min_items}, ensure_ascii=False, indent=2), encoding="utf-8")
    day = generated_at.astimezone(MOSCOW).strftime("%Y-%m-%d")
    with gzip.open(archive / f"{day}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    cutoff = generated_at.astimezone(MOSCOW).date() - timedelta(days=keep_days)
    for path in archive.glob("*.json.gz"):
        try:
            d = datetime.strptime(path.stem.replace('.json',''), "%Y-%m-%d").date()
        except Exception:
            continue
        if d < cutoff:
            path.unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--keep-days", type=int, default=60)
    ap.add_argument("--now")
    ap.add_argument("--fetched-total", type=int)
    args = ap.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    end = generated_at
    start = end - timedelta(days=args.days)
    raw = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    all_window = []
    last_signal = None
    for item in raw:
        d = parse_dt(item.get("date"))
        if d and start <= d <= end:
            all_window.append(item)
            if last_signal is None or d > last_signal:
                last_signal = d
    selected = select_items(raw, start, end, args.limit)
    html_text = build_html(selected, raw, all_window, start, end, generated_at, last_signal, args.fetched_total)
    (outdir / "index.html").write_text(html_text, encoding="utf-8")
    write_data_files(selected, raw, all_window, outdir, generated_at, args.keep_days, args.fetched_total)
    print(f"generated index.html; window_items={len(all_window)} selected={len(selected)} period={start.date()}..{end.date()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
