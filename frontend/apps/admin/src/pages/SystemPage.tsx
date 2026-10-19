import { Badge, ErrorState, Icon, Skeleton, useOnline } from '@beauty/ui';
import type { ReactNode } from 'react';
import { formatNumber } from '../shared/lib/format';
import { useSystem } from '../shared/lib/queries';
import ui from '../shared/ui.module.css';

function Status({ ok, children }: { readonly ok: boolean; readonly children: ReactNode }) {
  return (
    <span className={ui.row} style={{ gap: 6 }}>
      <Icon name={ok ? 'check' : 'pending'} size={18} strokeWidth={2} aria-hidden="true" />
      <Badge tone={ok ? 'ok' : 'warn'}>{children}</Badge>
    </span>
  );
}

/** Состояние системы: база, очередь событий, отложенные задачи, что включено. */
export function SystemPage() {
  const system = useSystem();
  const online = useOnline();
  const data = system.data;
  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>Система</h1>
          <p className={ui.muted}>Обновляется каждые 30 секунд.</p>
        </div>
        {data && <Badge tone="muted">Окружение: {data.environment}</Badge>}
      </header>
      {data ? (
        <div className={ui.twoCols}>
          <section className={ui.card} aria-labelledby="infra">
            <h2 id="infra" className={ui.h2}>
              Работа сервиса
            </h2>
            <dl className={ui.kv}>
              <dt>База данных</dt>
              <dd>
                <Status ok={data.database}>{data.database ? 'Доступна' : 'Недоступна'}</Status>
              </dd>
              <dt>Очередь событий</dt>
              <dd>
                <Status ok={data.outbox.pending < 100 && (data.outbox.oldest_seconds ?? 0) < 60}>
                  {data.outbox.pending === 0
                    ? 'Пусто — всё отправлено'
                    : `Ждут отправки: ${formatNumber(data.outbox.pending)}`}
                </Status>
              </dd>
              {data.outbox.oldest_seconds !== null && (
                <>
                  <dt>Старейшее событие</dt>
                  <dd>{Math.round(data.outbox.oldest_seconds)} с назад</dd>
                </>
              )}
              <dt>Отложенные задачи</dt>
              <dd>
                <Status ok={data.jobs.overdue === 0}>
                  {data.jobs.overdue === 0
                    ? `В расписании: ${formatNumber(data.jobs.scheduled)}`
                    : `Просрочено: ${formatNumber(data.jobs.overdue)}`}
                </Status>
              </dd>
            </dl>
            <p className={ui.muted}>
              Растущая очередь событий или просроченные задачи — признак, что не работает relay,
              worker или scheduler.
            </p>
          </section>
          <section className={ui.card} aria-labelledby="features">
            <h2 id="features" className={ui.h2}>
              Возможности
            </h2>
            <dl className={ui.kv}>
              <dt>ИИ-администратор</dt>
              <dd>
                <Status ok={data.features.agent}>
                  {data.features.agent ? 'Включён' : 'Выключен'}
                </Status>
              </dd>
              <dt>Расшифровка голосовых</dt>
              <dd>
                <Status ok={data.features.speech}>
                  {data.features.speech ? 'Включена' : 'Выключена'}
                </Status>
              </dd>
              <dt>Push-уведомления</dt>
              <dd>
                <Status ok={data.features.push}>
                  {data.features.push ? 'Настроены' : 'Нет ключей VAPID'}
                </Status>
              </dd>
            </dl>
          </section>
        </div>
      ) : system.isError ? (
        <ErrorState offline={!online} onRetry={() => void system.refetch()} />
      ) : (
        <Skeleton height={200} radius={18} />
      )}
    </div>
  );
}
