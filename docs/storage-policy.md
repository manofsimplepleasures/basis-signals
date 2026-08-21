# Storage policy

## Что хранится на сервере

```text
/opt/basis_signal/
  index.html
  raw/acceptance-posts.jsonl
  data/latest.json
  data/latest.min.json
  data/archive/YYYY-MM-DD.json.gz
  logs/update.log
```

## Почему так

Сайту нужен последний рабочий набор данных и небольшой архив, чтобы видеть историю обновлений. Сырые HTML-страницы Telegram и медиа не хранятся, потому что они быстро раздувают диск и не нужны для публичной витрины.

## Ограничение размера

- дневные snapshot сохраняются в gzip;
- архив хранится 60 дней;
- лог обрезается, если становится больше 5 MB;
- в GitHub уходит только код и пример `latest.min.json`.
