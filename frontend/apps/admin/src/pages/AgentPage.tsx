import { Badge, ErrorState, Skeleton, useOnline } from '@beauty/ui';
import { formatDateTime, formatDay, formatNumber, formatSeconds } from '../shared/lib/format';
import { useAgentReport } from '../shared/lib/queries';
import ui from '../shared/ui.module.css';
import { BarChart } from '../widgets/BarChart';
import { StatTile } from '../widgets/StatTile';

const FACE = { front_desk: 'клиенту', back_office: 'мастеру' } as const;

/** ИИ-администратор: настройки, ходы по дням, время ответа, сбои, голосовые. */
export function AgentPage() {
  const report = useAgentReport();
  const online = useOnline();
  const data = report.data;
  if (!data) {
    return (
      <div className={ui.page}>
        <h1 className={ui.h1}>ИИ-администратор</h1>
        {report.isError ? (
          <ErrorState offline={!online} onRetry={() => void report.refetch()} />
        ) : (
          <Skeleton height={320} radius={18} />
        )}
      </div>
    );
  }
  const turns = data.days.reduce((s, d) => s + d.front_desk + d.office, 0);
  const failures = data.days.reduce((s, d) => s + d.failures, 0);
  const handoffs = data.days.reduce((s, d) => s + d.handoffs, 0);
  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>ИИ-администратор</h1>
          <p className={ui.muted}>За последние 14 дней.</p>
        </div>
        <div className={ui.row}>
          <Badge tone={data.runtime === 'off' ? 'warn' : 'ok'}>
            {data.runtime === 'off' ? 'Агент выключен' : `Модель ${data.model}`}
          </Badge>
          <Badge tone={data.speech.provider === 'off' ? 'warn' : 'ok'}>
            {data.speech.provider === 'off'
              ? 'Расшифровка выключена'
              : `Расшифровка ${data.speech.model}`}
          </Badge>
        </div>
      </header>
      <section className={ui.grid} aria-label="Итоги">
        <StatTile label="Ходы" value={turns} hint="ответы клиентам и поручения" />
        <StatTile
          label="Сбои"
          value={failures}
          hint={turns ? `${Math.round((failures / turns) * 100)}% ходов` : undefined}
        />
        <StatTile label="Передано мастеру" value={handoffs} />
        <StatTile
          label="Голосовые"
          value={data.voice.total}
          hint={`расшифровано ${formatNumber(data.voice.transcribed)}`}
        />
      </section>
      <div className={ui.twoCols}>
        <div className={ui.card}>
          <BarChart
            title="Ходы по дням"
            unit={['ход', 'хода', 'ходов']}
            points={data.days.map((d) => ({ date: d.date, value: d.front_desk + d.office }))}
          />
        </div>
        <section className={ui.card} aria-labelledby="latency">
          <h2 id="latency" className={ui.h2}>
            Время ответа
          </h2>
          <div className={ui.tableWrap} style={{ border: 0 }}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>День</th>
                  <th className={ui.num}>Клиентам</th>
                  <th className={ui.num}>Мастеру</th>
                  <th className={ui.num}>Среднее</th>
                  <th className={ui.num}>p95</th>
                </tr>
              </thead>
              <tbody>
                {[...data.days]
                  .reverse()
                  .slice(0, 7)
                  .map((d) => (
                    <tr key={d.date}>
                      <td>{formatDay(d.date)}</td>
                      <td className={ui.num}>{formatNumber(d.front_desk)}</td>
                      <td className={ui.num}>{formatNumber(d.office)}</td>
                      <td className={ui.num}>{formatSeconds(d.avg_seconds)}</td>
                      <td className={ui.num}>{formatSeconds(d.p95_seconds)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <section className={ui.card} aria-labelledby="failures">
        <h2 id="failures" className={ui.h2}>
          Последние сбои
        </h2>
        {data.failures.length === 0 ? (
          <p className={ui.muted}>Сбоев не было.</p>
        ) : (
          <table className={ui.table}>
            <thead>
              <tr>
                <th>Когда</th>
                <th>Мастер</th>
                <th>Кому отвечал</th>
                <th>Итог</th>
                <th className={ui.num}>Длительность</th>
              </tr>
            </thead>
            <tbody>
              {data.failures.map((f) => (
                <tr key={`${f.at}-${f.master}`}>
                  <td>{formatDateTime(f.at)}</td>
                  <td>{f.master}</td>
                  <td>{FACE[f.face]}</td>
                  <td>
                    <Badge tone="warn">{f.status}</Badge>
                  </td>
                  <td className={ui.num}>{formatSeconds(f.seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className={ui.muted}>
          timeout — модель не ответила вовремя, no_reply — ответила служебной заметкой, empty —
          пустым ответом. Клиенту в этих случаях отвечает мастер.
        </p>
      </section>
    </div>
  );
}
