# Базис - Сигналы

Публичный радар сигналов по приемке квартир из открытых источников.

Live:

- http://basis-signals.31.59.44.174.nip.io/
- http://31.59.44.174/

## Что показывает сайт

Сайт собирает публичные посты из Telegram web previews, вытаскивает из них ЖК, застройщика, стадию, категории дефектов и конкретные детали. Главная страница показывает последние 14 дней и отбирает карточки, где больше всего проверяемой конкретики.

Это не рейтинг застройщиков и не утверждение о системных проблемах. Каждая карточка ведет к первоисточнику.

## Зачем проект

Это pet-project про продуктовое мышление на стыке PropTech, клиентского сервиса и данных:

- поиск полевых сигналов в открытых источниках;
- нормализация разрозненных постов;
- безопасная публичная формулировка;
- простой UX для просмотра и фильтрации;
- ежедневное обновление на сервере;
- легкое хранение данных без сырого медиа и HTML-дампов.

## Обновление

На сервере сайт обновляется каждый день в 05:00 МСК.

Пайплайн:

```text
public Telegram previews
→ parser
→ latest.json / latest.min.json
→ archive/YYYY-MM-DD.json.gz
→ index.html
```

Архив хранится сжато и ограниченно по времени. В GitHub попадает код, README и пример облегченных данных, а не полный сырой архив.

## Источники

Каналы приемки и технадзора:

- @mrnadzor
- @KIRILLPRIEMKA
- @tehpriemka
- @specnovostroy_ch
- @revizor_priemka
- @priemka_moscow

Каналы рыночного обогащения:

- @pro_smarent
- @iliilitop

## Локальный запуск

```bash
python3 scripts/acceptance_intelligence.py \
  --pages 4 \
  --channels mrnadzor KIRILLPRIEMKA tehpriemka specnovostroy_ch revizor_priemka priemka_moscow pro_smarent iliilitop \
  --output-dir raw

python3 scripts/generate_site.py \
  --input raw/acceptance-posts.jsonl \
  --outdir . \
  --days 14 \
  --limit 24

python3 -m http.server 8080
```
