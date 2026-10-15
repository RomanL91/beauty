"""Beauty — персональный ИИ-администратор для мастеров-одиночек.

Сервис ведёт переписку с клиентами, запись и график мастера так, как это делал бы
администратор салона. Проект построен как модульный монолит:

* ``beauty.shared`` — shared kernel: базовые строительные блоки домена, CQRS,
  Unit of Work, outbox/inbox, RabbitMQ, отложенные задачи;
* ``beauty.contexts`` — ограниченные контексты (identity, tenancy, scheduling, …);
* ``beauty.bootstrap`` — корень композиции (сборка зависимостей);
* ``beauty.entrypoints`` — процессы: API, Telegram-бот, outbox relay, планировщик.
"""
