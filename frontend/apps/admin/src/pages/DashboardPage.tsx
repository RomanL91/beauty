import { ErrorState, Skeleton, useOnline } from '@beauty/ui';
import { useDashboard } from '../shared/lib/queries';
import ui from '../shared/ui.module.css';
import { BarChart } from '../widgets/BarChart';
import { StatTile } from '../widgets/StatTile';

/** Сводка: итоги и 30 дней по дням. */
export function DashboardPage() {
  const dashboard = useDashboard();
  const online = useOnline();
  const data = dashboard.data;
  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>Сводка</h1>
          <p className={ui.muted}>Сервис целиком; графики — за последние 30 дней (UTC).</p>
        </div>
      </header>
      {data ? (
        <>
          <section className={ui.grid} aria-label="Итоги">
            <StatTile
              label="Мастера"
              value={data.totals.masters}
              hint={`опубликовано ${data.totals.published} · с агентом ${data.totals.agents_enabled}`}
            />
            <StatTile
              label="Клиенты"
              value={data.totals.clients}
              hint={
                data.totals.blocked_clients
                  ? `заблокировано ${data.totals.blocked_clients}`
                  : undefined
              }
            />
            <StatTile
              label="Записи впереди"
              value={data.totals.upcoming_appointments}
              hint="подтверждённые"
            />
            <StatTile
              label="Ждут мастера"
              value={data.totals.pending_requests}
              hint="заявки без ответа"
            />
            <StatTile label="Переписки" value={data.totals.conversations} />
          </section>
          <section className={ui.twoCols} aria-label="По дням">
            <div className={ui.card}>
              <BarChart
                title="Заявки на запись"
                unit={['заявка', 'заявки', 'заявок']}
                points={data.days.map((d) => ({ date: d.date, value: d.requested }))}
              />
            </div>
            <div className={ui.card}>
              <BarChart
                title="Новые клиенты"
                unit={['клиент', 'клиента', 'клиентов']}
                points={data.days.map((d) => ({ date: d.date, value: d.new_clients }))}
              />
            </div>
            <div className={ui.card}>
              <BarChart
                title="Сообщения клиентов"
                unit={['сообщение', 'сообщения', 'сообщений']}
                points={data.days.map((d) => ({ date: d.date, value: d.messages }))}
              />
            </div>
            <div className={ui.card}>
              <BarChart
                title="Ходы ИИ-администратора"
                unit={['ход', 'хода', 'ходов']}
                points={data.days.map((d) => ({ date: d.date, value: d.agent_turns }))}
              />
            </div>
          </section>
        </>
      ) : dashboard.isError ? (
        <ErrorState offline={!online} onRetry={() => void dashboard.refetch()} />
      ) : (
        <div className={ui.grid} aria-busy="true">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} height={96} radius={18} />
          ))}
        </div>
      )}
    </div>
  );
}
