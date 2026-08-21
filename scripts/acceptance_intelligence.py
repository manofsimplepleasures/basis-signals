#!/usr/bin/env python3
"""
Acceptance Intelligence parser for Basis Sales Intelligence.

Fetches public Telegram web previews (https://t.me/s/<channel>), normalizes posts
about apartment acceptance / defects, and generates sales cards + weekly digest.

No Telegram account/API token required. It only uses public web preview pages.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

DEFAULT_CHANNELS = [
    "mrnadzor",
    "KIRILLPRIEMKA",
    "tehpriemka",
    "specnovostroy_ch",
    "revizor_priemka",
    "priemka_moscow",
]

CATEGORY_PATTERNS = {
    "окна/стеклопакеты/откосы": r"окн|стеклопакет|профил|створк|подокон|откос|уплотнител|фурнитур|капельник|дренаж",
    "двери/фурнитура": r"двер|ручк|полотн|зам(о|к)|добор|наличник|притвор",
    "отделка стен/потолков": r"обо[ий]|стен|потол|краск|шпакл|штукатур|трещин|отсло|надрыв|морщин|разнотон",
    "полы/ламинат/плитка": r"ламинат|плитк|пол\b|стяжк|плинтус|керамогранит|проседа|инженерн[а-я]+ дос",
    "электрика": r"электр|розет|выключател|автомат|щит|светил|заземлен|узо",
    "вентиляция": r"вентиляц|тяга|вытяж|воздухообмен",
    "сантехника/санузлы": r"сантех|сануз|унитаз|ванн|раковин|смесител|канализац|водоснаб|труб|сифон|гвс|хвс|протеч",
    "геометрия/отклонения": r"отклонен|геометр|уровен|завал|перепад|плоскост|вертикал|горизонтал",
    "смета/объемы/договор/скрытые работы": r"смет|объем|объ[её]м|договор|скрыт|допы|технадзор|подрядчик|ремонт|акт скрытых",
    "гарантия/суды/претензии": r"гаранти|суд|претенз|компенсац|дольщик|иск|взыск|экспертиз|неустойк",
}

STAGE_RULES = [
    ("суд", r"суд|иск|взыск|экспертиз|компенсац|неустойк"),
    ("гарантия", r"гаранти|через 1-2 года|после передачи|повторн[а-я]+ обращ|плесень|влажност"),
    ("выдача ключей", r"выдач[аеи] ключ|стартовал[а]? выдач|началась выдача|передач[аеи] ключ"),
    ("приёмка", r"при[её]мк|принять квартиру|акт при[её]м"),
    ("ремонт", r"ремонт|подрядчик|смет|договор|допы"),
    ("технадзор", r"технадзор|строительн[а-я]+ контроль|скрыт[а-я]+ работ|объем|объ[её]м"),
]

MODULE_BY_CATEGORY = {
    "гарантия/суды/претензии": "Гарантия",
    "смета/объемы/договор/скрытые работы": "Стройконтроль",
}

@dataclass
class RawPost:
    channel: str
    post_id: str
    date: str
    views: str
    link: str
    text: str

@dataclass
class NormalizedPost:
    source_channel: str
    post_id: str
    date: str
    views: str
    link: str
    residential_complexes: list[str]
    developers: list[str]
    stage: str
    categories: list[str]
    defect_counts: list[int]
    basis_modules: list[str]
    safety_note: str
    distinctive_details: list[str]
    story_hook: str
    summary: str
    operator_pain: str
    basis_connection: str
    safe_call_phrase: str
    client_question: str
    raw_text: str

class TGParser(HTMLParser):
    def __init__(self, channel: str):
        super().__init__()
        self.channel = channel
        self.posts: list[RawPost] = []
        self.cur: dict | None = None
        self.in_text = False
        self.text_parts: list[str] = []
        self.in_views = False
        self.views_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = str(attrs.get("class", ""))
        # A real post container has class token `tgme_widget_message` and a
        # `data-post` id. Child nodes such as `tgme_widget_message_text` should
        # not start a new post.
        if tag == "div" and "tgme_widget_message" in cls.split() and attrs.get("data-post"):
            self._finish_post()
            self.cur = {"post_id": attrs.get("data-post", ""), "date": "", "views": "", "link": "", "text": ""}
        if self.cur is None:
            return
        if tag == "div" and "tgme_widget_message_text" in cls:
            self.in_text = True
            self.text_parts = []
        elif tag == "br" and self.in_text:
            self.text_parts.append("\n")
        elif tag == "time":
            self.cur["date"] = attrs.get("datetime", "")
        elif tag == "a" and "tgme_widget_message_date" in cls:
            self.cur["link"] = attrs.get("href", "")
        elif tag == "span" and "tgme_widget_message_views" in cls:
            self.in_views = True
            self.views_parts = []

    def handle_endtag(self, tag):
        if tag == "div" and self.in_text:
            self.in_text = False
            self.cur["text"] = html.unescape("".join(self.text_parts)).strip()
        elif tag == "span" and self.in_views:
            self.in_views = False
            self.cur["views"] = "".join(self.views_parts).strip()

    def handle_data(self, data):
        if self.in_text:
            self.text_parts.append(data)
        if self.in_views:
            self.views_parts.append(data)

    def _finish_post(self):
        if not self.cur:
            return
        if self.in_text:
            self.cur["text"] = html.unescape("".join(self.text_parts)).strip()
            self.in_text = False
        if self.cur.get("post_id") and self.cur.get("text"):
            self.posts.append(RawPost(channel=self.channel, **self.cur))
        self.cur = None

    def close(self):
        super().close()
        self._finish_post()


def fetch_html(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BasisAcceptanceIntelligence/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def fetch_channel(channel: str, pages: int, pause: float) -> list[RawPost]:
    posts: list[RawPost] = []
    seen = set()
    url = f"https://t.me/s/{channel}"
    for _ in range(pages):
        try:
            data = fetch_html(url)
        except Exception as exc:
            print(f"WARN: failed to fetch {url}: {exc}", file=sys.stderr)
            break
        parser = TGParser(channel)
        parser.feed(data)
        parser.close()
        page_posts = parser.posts
        for post in page_posts:
            key = (post.channel, post.post_id)
            if key not in seen:
                seen.add(key)
                posts.append(post)
        ids = []
        for post in page_posts:
            m = re.search(r"/(\d+)$", post.link or post.post_id)
            if m:
                ids.append(int(m.group(1)))
        if not ids:
            break
        url = f"https://t.me/s/{channel}?before={min(ids)}"
        if pause:
            time.sleep(pause)
    return posts


def unique_matches(pattern: str, text: str, flags=re.I) -> list[str]:
    values = []
    for m in re.finditer(pattern, text, flags):
        value = re.sub(r"\s+", " ", m.group(1).strip(" .,:;—-\n\t"))
        if value and value not in values:
            values.append(value)
    return values


def extract_developers(text: str) -> list[str]:
    """Extract developer names conservatively.

    Telegram prose often contains phrases like "застройщик исправляет дефекты".
    False-positive developers are worse than omissions for lead routing, so this
    function prefers known developer tokens and short title-like names after the
    word "застройщик".
    """
    values: list[str] = []
    known_pattern = (
        r"\b(ПИК|ЛСР|ФСК|Sminex|Самол(?:е|ё)т|Абсолют|А101|а101|MR Group|Level Group|"
        r"Эталон|Донстрой|Брусника|Hauswerk|ИКАР|PROGRESS|ГК\s+[А-ЯЁA-Z][А-ЯЁа-яA-Z0-9\-]{2,20})\b"
    )
    for value in unique_matches(known_pattern, text):
        value = value.strip(" .,:;—-")
        if value.lower() == "а101":
            value = "А101"
        if value not in values:
            values.append(value)
    return values


def classify_stage(text: str) -> str:
    low = text.lower()
    for stage, pattern in STAGE_RULES:
        if re.search(pattern, low):
            return stage
    return "не классифицировано"


def classify_categories(text: str) -> list[str]:
    low = text.lower()
    return [name for name, pattern in CATEGORY_PATTERNS.items() if re.search(pattern, low)]


def module_recommendations(stage: str, categories: list[str]) -> list[str]:
    modules = []
    if stage in {"выдача ключей", "приёмка"}:
        modules.append("Ключи")
    if stage in {"технадзор", "ремонт"}:
        modules.append("Стройконтроль")
    if stage in {"гарантия", "суд"}:
        modules.append("Гарантия")
    for cat in categories:
        mod = MODULE_BY_CATEGORY.get(cat)
        if mod and mod not in modules:
            modules.append(mod)
    if "Ключи" in modules and "Гарантия" not in modules and any(c in categories for c in ["гарантия/суды/претензии", "сантехника/санузлы"]):
        modules.append("Гарантия")
    return modules or ["Ключи", "Стройконтроль", "Гарантия"]


def split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.replace("•", ". ").replace("*", ". ")).strip()
    parts = re.split(r"(?<=[.!?])\s+|\n+|(?<=:)\s+[-–—]", cleaned)
    return [p.strip(" -–—•	") for p in parts if len(p.strip()) >= 35]


def extract_distinctive_details(text: str, limit: int = 5) -> list[str]:
    """Pull vivid, concrete defect details instead of generic category labels."""
    vivid = [
        r"окалин", r"трещин", r"протеч", r"плесен", r"влажност", r"пустот", r"очень слабая тяга",
        r"отсутств", r"не проклеен", r"некачествен", r"деформ", r"люфт", r"цепляет", r"заедан",
        r"проседа", r"зазор", r"скол", r"брак", r"царап", r"перепад", r"отклонение.*\d+\s*мм",
        r"\d+\s*мм", r"\d+\s*(?:замечан|дефект)", r"через\s+1-2\s+года", r"суд", r"экспертиз",
        r"коллектор", r"МОП", r"стяжк", r"ГВС", r"сифон", r"герметизац", r"дренаж",
    ]
    scored: list[tuple[int, int, str]] = []
    for idx, sent in enumerate(split_sentences(text)):
        low = sent.lower()
        score = sum(2 for pat in vivid if re.search(pat, low))
        score += min(len(re.findall(r"\d+", sent)), 3)
        promo_markers = [
            "основные", "полезные материалы", "для записи", "whatsapp", "писать сюда",
            "сохраните этот пост", "профессиональную проверку", "профессиональную приемку", "профессиональную приёмку",
            "неважно, сколько стоит", "приемка.москва", "https://", "+7", "миллионов рублей", "сотни тысяч рублей",
        ]
        if any(word in low for word in promo_markers):
            continue
        # Keep mostly defect/exploitation/legal specifics, not promotional advice.
        if not any(re.search(pat, low) for pat in vivid):
            score -= 4
        if score > 0:
            sent = re.sub(r"\s+", " ", sent).strip()
            if len(sent) > 230:
                sent = sent[:227].rstrip() + "…"
            scored.append((score, -idx, sent))
    scored.sort(reverse=True)
    details: list[str] = []
    for _, _, sent in scored:
        if sent not in details:
            details.append(sent)
        if len(details) >= limit:
            break
    return details


def make_story_hook(details: list[str], counts: list[int], complexes: list[str]) -> str:
    if details:
        lead = details[0]
        obj = f"в ЖК «{complexes[0]}»" if complexes else "в публичном кейсе"
        return f"{obj}: {lead[0].lower() + lead[1:] if lead else lead}"
    if counts:
        return f"масштабом: в одной квартире указано {max(counts)} замечаний — это хороший мост к разговору о массовой выдаче и повторных осмотрах."
    return "тем, что за красивой выдачей ключей часто стоит длинный хвост фиксации, устранения и повторных проверок."


def compact_summary(text: str, complexes: list[str], counts: list[int], categories: list[str], details: list[str]) -> str:
    object_part = f"В ЖК «{', '.join(complexes[:2])}»" if complexes else "В публичном разборе приёмки"
    count_part = f"зафиксировано {max(counts)} замечаний" if counts else "описан набор строительных замечаний"
    if details:
        return f"{object_part} {count_part}. Самое яркое: {details[0]}"
    cats = ", ".join(categories[:4]) if categories else "качество, сроки и ответственность"
    return f"{object_part} {count_part}; ключевые зоны: {cats}."


def make_sales_fields(stage: str, categories: list[str], modules: list[str], summary: str, details: list[str], story_hook: str) -> tuple[str, str, str, str]:
    concrete = "; ".join(details[:3]) if details else summary
    pain = (
        f"Операционная боль не абстрактная: {concrete}. "
        "Для COO это означает поток задач между клиентским сервисом, стройкой, подрядчиками и гарантией: нужно не просто записать дефект, а довести его до ответственного, срока, повторной проверки и закрывающего акта."
    )
    basis = f"Связка с Basis: {' + '.join(modules)}. Такие конкретные замечания должны становиться не текстом в чате, а управляемой записью: чек-лист, фото, ответственный, срок, статус, повторная приёмка/предписание и аналитика по объекту/подрядчику."
    phrase = (
        f"Из открытых разборов приёмок запомнился такой сюжет: {story_hook}. "
        "Не как обвинение к рынку, а как пример, почему важно видеть путь каждого замечания от осмотра до устранения и гарантии."
    )
    question = "Если у вас на выдаче появляется такая нестандартная связка замечаний, кто видит её целиком: клиентский сервис, стройка, подрядчик и гарантия — или каждый ведёт свой кусок?"
    if stage == "суд":
        question = "По таким спорным замечаниям какая доказательная база остаётся в системе: фото, даты, ответственные, повторные осмотры, экспертиза и история коммуникации?"
    elif stage == "технадзор":
        question = "Если замечание связано со скрытыми работами, объёмами или подрядчиком, как вы сейчас связываете фотофиксацию, предписание, срок устранения и влияние на КС/оплату?"
    return pain, basis, phrase, question


def normalize(post: RawPost) -> NormalizedPost:
    text = post.text
    complexes = unique_matches(r"ЖК\s+[«\"]([^»\"]+)[»\"]", text)
    developers = extract_developers(text)
    counts = [int(x) for x in re.findall(r"(\d{1,3})\s+(?:замечан|дефект)", text, flags=re.I)]
    categories = classify_categories(text)
    stage = classify_stage(text)
    modules = module_recommendations(stage, categories)
    details = extract_distinctive_details(text)
    story_hook = make_story_hook(details, counts, complexes)
    summary = compact_summary(text, complexes, counts, categories, details)
    pain, basis, phrase, question = make_sales_fields(stage, categories, modules, summary, details, story_hook)
    return NormalizedPost(
        source_channel=post.channel,
        post_id=post.post_id,
        date=post.date,
        views=post.views,
        link=post.link,
        residential_complexes=complexes,
        developers=developers,
        stage=stage,
        categories=categories,
        defect_counts=counts,
        basis_modules=modules,
        safety_note="Использовать как публичный рыночный сигнал/пример, не как утверждение о клиенте Basis и не как компромат.",
        distinctive_details=details,
        story_hook=story_hook,
        summary=summary,
        operator_pain=pain,
        basis_connection=basis,
        safe_call_phrase=phrase,
        client_question=question,
        raw_text=text,
    )


def write_outputs(items: list[NormalizedPost], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_date = datetime.now(timezone.utc).date().isoformat()
    jsonl_path = output_dir / "acceptance-posts.jsonl"
    csv_path = output_dir / "acceptance-posts.csv"
    cards_path = output_dir / "sales-cards.md"
    digest_path = output_dir / f"weekly-digest-{run_date}.md"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    fieldnames = [
        "source_channel", "post_id", "date", "views", "link", "residential_complexes", "developers",
        "stage", "categories", "defect_counts", "basis_modules", "distinctive_details", "story_hook", "summary", "safe_call_phrase", "client_question",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = asdict(item)
            for key in ["residential_complexes", "developers", "categories", "defect_counts", "basis_modules", "distinctive_details"]:
                row[key] = "; ".join(map(str, row[key]))
            writer.writerow({k: row[k] for k in fieldnames})

    # Sales cards should prioritize memorable, concrete cases. Keep the CSV as
    # the broader attributed database, but cards/digest use cases with vivid
    # extracted details first.
    card_candidates = [item for item in items if item.distinctive_details] or items
    selected = sorted(card_candidates, key=lambda x: (x.date or "", x.post_id), reverse=True)[:30]
    with cards_path.open("w", encoding="utf-8") as f:
        f.write("# Acceptance Intelligence — sales-карточки\n\n")
        f.write("> Публичные сигналы из каналов приемщиков. Использовать как полевые примеры и вопросы для диагностики, не как компромат.\n\n")
        for item in selected:
            f.write(f"## {item.residential_complexes[0] if item.residential_complexes else item.post_id}\n\n")
            f.write(f"- **Источник:** [{item.source_channel}]({item.link}) · {item.date} · {item.views}\n")
            f.write(f"- **ЖК:** {', '.join(item.residential_complexes) or 'не указан'}\n")
            f.write(f"- **Застройщик:** {', '.join(item.developers) or 'не указан'}\n")
            f.write(f"- **Стадия:** {item.stage}\n")
            f.write(f"- **Категории:** {', '.join(item.categories) or 'не классифицировано'}\n")
            f.write(f"- **Число замечаний:** {', '.join(map(str, item.defect_counts)) or 'не указано'}\n\n")
            f.write("**Конкретика:**\n")
            details = item.distinctive_details[:5] or [item.summary]
            for detail in details:
                f.write(f"- {detail}\n")
            f.write("\n")

    # Digest
    by_category: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    for item in items:
        by_stage[item.stage] = by_stage.get(item.stage, 0) + 1
        for cat in item.categories:
            by_category[cat] = by_category.get(cat, 0) + 1
    fresh = sorted(card_candidates, key=lambda x: (x.date or "", x.post_id), reverse=True)[:5]
    odd = [i for i in card_candidates if any(c in i.categories for c in ["вентиляция", "сантехника/санузлы", "геометрия/отклонения"])]
    with digest_path.open("w", encoding="utf-8") as f:
        f.write(f"# Acceptance Intelligence — еженедельный дайджест {run_date}\n\n")
        f.write(f"Собрано нормализованных постов: **{len(items)}**. Каналы: {', '.join(sorted(set(i.source_channel for i in items)))}.\n\n")
        f.write("## 5 свежих кейсов по приёмке\n")
        for item in fresh:
            f.write(f"- [{item.residential_complexes[0] if item.residential_complexes else item.post_id}]({item.link}) — {item.story_hook} Модули: {' + '.join(item.basis_modules)}.\n")
        f.write("\n## 3 неочевидных дефекта недели\n")
        for item in odd[:3]:
            detail = item.distinctive_details[0] if item.distinctive_details else item.summary
            f.write(f"- [{item.residential_complexes[0] if item.residential_complexes else item.post_id}]({item.link}) — {', '.join(item.categories[:3])}: {detail}\n")
        f.write("\n## 3 фразы для storytelling\n")
        f.write("- «Когда на одной квартире десятки замечаний, на масштабе корпуса это уже не вопрос листочка приёмки, а вопрос управляемого цифрового контура».\n")
        f.write("- «Дефект — это не только фото. Это ответственный, срок, повторная проверка, акт, подрядчик и будущая гарантийная история».\n")
        f.write("- «Публичные разборы приёмок показывают, что часть проблем проявляется не в день выдачи, а через месяцы — значит, передача и гарантия должны быть связаны».\n")
        f.write("\n## 3 вопроса для COO / директора по строительству / клиентского сервиса\n")
        f.write("- Как вы видите единый статус по замечаниям: квартира → этаж → корпус → подрядчик → срок устранения?\n")
        f.write("- Что происходит с замечанием после первичной приёмки: кто назначает ответственного, как контролируется повторный осмотр и акт?\n")
        f.write("- Какие дефекты чаще всего переходят из приёмки в гарантию, и есть ли у вас сквозная история по ним?\n")
        f.write("\n## Кого проверить как потенциальные лиды\n")
        seen = []
        for item in items:
            for dev in item.developers:
                if dev not in seen:
                    seen.append(dev)
        if seen:
            for dev in seen[:10]:
                f.write(f"- {dev}: проверить текущие выдачи ключей, гарантийный фон, публичные объекты и релевантность Ключи + Гарантия + Стройконтроль.\n")
        else:
            f.write("- В текущем прогоне застройщики распознаны слабо: проверить вручную ЖК из sales-cards.md.\n")
        f.write("\n## Распределение по стадиям\n")
        for stage, count in sorted(by_stage.items(), key=lambda x: x[1], reverse=True):
            f.write(f"- {stage}: {count}\n")
        f.write("\n## Частые категории дефектов\n")
        for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            f.write(f"- {cat}: {count}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", nargs="*", default=DEFAULT_CHANNELS)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--pause", type=float, default=0.2)
    parser.add_argument("--output-dir", default="knowledge/market/acceptance-intelligence/data")
    parser.add_argument(
        "--include-unattributed",
        action="store_true",
        help="Keep posts where neither residential complex nor developer was extracted. Default: drop them from outputs.",
    )
    args = parser.parse_args(argv)

    raw_posts: list[RawPost] = []
    for channel in args.channels:
        raw_posts.extend(fetch_channel(channel, args.pages, args.pause))
    all_normalized = [normalize(post) for post in raw_posts]
    if args.include_unattributed:
        normalized = all_normalized
    else:
        normalized = [item for item in all_normalized if item.residential_complexes or item.developers]
    normalized.sort(key=lambda item: (item.date or "", item.source_channel, item.post_id), reverse=True)
    write_outputs(normalized, Path(args.output_dir))
    dropped = len(all_normalized) - len(normalized)
    print(f"Fetched {len(raw_posts)} posts from {len(args.channels)} channels; normalized {len(normalized)} posts; dropped_unattributed {dropped}")
    print(f"Output: {Path(args.output_dir).resolve()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
