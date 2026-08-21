# Storage policy

## Что хранится на сервере

```text
/opt/basis_signal/
  index.html
  raw/acceptance-posts.jsonl
  data/latest.json
  data/latest.min.json
  data/signals.min.jsonl
  data/archive/YYYY-MM-DD.json.gz
  data/snapshots/YYYY-MM-DD.min.json.gz
  logs/update.log
```

## Почему так

Сайту нужен последний рабочий набор данных и накопительная публичная база, чтобы через несколько месяцев было видно, что проект не разовый HTML-снимок, а ежедневный мониторинг.

`signals.min.jsonl` - главный публичный датасет. Он дедуплицируется по источнику, id поста и ссылке. В нем остаются только нормализованные поля: дата, канал, ссылка, ЖК, застройщик, стадия, категории, числа замечаний и короткие детали. Сырые HTML-страницы Telegram и медиа не хранятся, потому что они быстро раздувают диск и не нужны для публичной витрины.

`snapshots/YYYY-MM-DD.min.json.gz` - сжатая дневная копия витрины. Она нужна, чтобы в GitHub было видно историю ежедневных обновлений.

## Ограничение размера

- дневные snapshot сохраняются в gzip;
- серверный runtime-архив `data/archive` хранится 60 дней;
- публичные `data/snapshots/*.min.json.gz` можно хранить месяцы в GitHub, потому что они маленькие;
- лог обрезается, если становится больше 5 MB;
- в GitHub уходит код, сайт, `latest.min.json`, `signals.min.jsonl` и сжатые публичные snapshot;
- в GitHub не уходят `raw/`, `logs/`, `latest.json` и серверный runtime-архив.
