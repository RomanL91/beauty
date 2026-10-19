import type { AdminMasterDetail } from '@beauty/api';
import {
  Button,
  ErrorState,
  Icon,
  Notice,
  Skeleton,
  TextField,
  iconButtonClass,
  useOnline,
} from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router';
import { formatDateTime, formatNumber, formatPhone } from '../shared/lib/format';
import { useMaster, useMasterAction } from '../shared/lib/queries';
import { pageUrl } from '../shared/lib/links';
import { parsePhone } from '../shared/lib/slug';
import ui from '../shared/ui.module.css';
import { AgentBadge, StatusBadge } from '../widgets/badges';
import { StatTile } from '../widgets/StatTile';

/** Карточка мастера: страница, публикация, агент, владелец, статистика, ближайшие записи. */
export function MasterPage() {
  const { id = '' } = useParams();
  const master = useMaster(id);
  const online = useOnline();
  return (
    <div className={ui.page}>
      <Link to="/masters" className={iconButtonClass()} aria-label="К мастерам">
        <Icon name="back" strokeWidth={2} />
      </Link>
      {master.data ? (
        <MasterCard master={master.data} />
      ) : master.isError ? (
        <ErrorState offline={!online} onRetry={() => void master.refetch()} />
      ) : (
        <Skeleton height={320} radius={18} />
      )}
    </div>
  );
}

function MasterCard({ master }: { readonly master: AdminMasterDetail }) {
  const online = useOnline();
  const publication = useMasterAction((api, published: boolean) =>
    api.setPublication(master.id, published),
  );
  const agent = useMasterAction((api, enabled: boolean) => api.setAgent(master.id, enabled));
  const published = master.status === 'published';
  const { stats, page } = master;

  return (
    <>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>{master.display_name}</h1>
          <p className={ui.muted}>
            <a href={pageUrl(master.slug, window.location)} target="_blank" rel="noreferrer">
              {master.slug}
            </a>
            {master.specialty ? ` · ${master.specialty}` : ''} · заведён{' '}
            {formatDateTime(master.created_at)}
          </p>
        </div>
        <div className={ui.row}>
          <StatusBadge status={master.status} />
          <AgentBadge state={master.agent} />
        </div>
      </header>

      <section className={ui.grid} aria-label="За 30 дней">
        <StatTile label="Заявки" value={stats.requested} hint="за 30 дней" />
        <StatTile label="Подтверждено" value={stats.confirmed} hint="за 30 дней" />
        <StatTile label="Отменено" value={stats.cancelled} hint="за 30 дней" />
        <StatTile label="Клиенты" value={stats.clients} hint={`переписок ${stats.conversations}`} />
        <StatTile
          label="Ходы агента"
          value={stats.agent_turns}
          hint={`сбоев ${stats.agent_failures} · мастеру ${stats.handoffs}`}
        />
      </section>

      <div className={ui.twoCols}>
        <section className={ui.card} aria-labelledby="publication">
          <h2 id="publication" className={ui.h2}>
            Страница
          </h2>
          <dl className={ui.kv}>
            <dt>Статус</dt>
            <dd>
              {published ? `Опубликована ${formatDateTime(master.published_at)}` : 'Черновик'}
            </dd>
            <dt>Услуги</dt>
            <dd>{formatNumber(page.services.length)}</dd>
            <dt>Фото работ</dt>
            <dd>{formatNumber(page.photos.length)}</dd>
            <dt>Адрес</dt>
            <dd>{page.address || '—'}</dd>
            <dt>Пояс</dt>
            <dd>{page.timezone}</dd>
          </dl>
          {!published && master.publish_blockers.length > 0 && (
            <Notice tone="warn" role="status">
              Опубликовать пока нельзя: {master.publish_blockers.join('; ').toLowerCase()}. Это
              заполняет мастер в кабинете.
            </Notice>
          )}
          <div className={ui.row}>
            {published ? (
              <Button
                variant="outline"
                disabled={publication.isPending || !online}
                onClick={() => publication.mutate(false)}
              >
                Скрыть страницу
              </Button>
            ) : (
              <Button
                disabled={publication.isPending || !online || master.publish_blockers.length > 0}
                onClick={() => publication.mutate(true)}
              >
                Опубликовать
              </Button>
            )}
          </div>
        </section>

        <section className={ui.card} aria-labelledby="agent">
          <h2 id="agent" className={ui.h2}>
            ИИ-администратор
          </h2>
          {master.agent === 'not_connected' ? (
            <>
              <p className={ui.muted}>
                Не подключён. Подключение создаёт профиль Hermes — это команда на сервере:
              </p>
              <code className={ui.code}>{master.agent_command}</code>
            </>
          ) : (
            <>
              <p className={ui.muted}>
                {master.agent === 'enabled'
                  ? 'Отвечает клиентам и выполняет поручения мастера.'
                  : 'Выключен: свободные вопросы клиентов ждут мастера.'}
              </p>
              <div className={ui.row}>
                <Button
                  variant={master.agent === 'enabled' ? 'outline' : 'primary'}
                  disabled={agent.isPending || !online}
                  onClick={() => agent.mutate(master.agent !== 'enabled')}
                >
                  {master.agent === 'enabled' ? 'Выключить' : 'Включить'}
                </Button>
              </div>
            </>
          )}
        </section>

        <OwnerCard master={master} />

        <section className={ui.card} aria-labelledby="upcoming">
          <h2 id="upcoming" className={ui.h2}>
            Ближайшие записи
          </h2>
          {master.upcoming.length === 0 ? (
            <p className={ui.muted}>Записей впереди нет.</p>
          ) : (
            <table className={ui.table}>
              <tbody>
                {master.upcoming.map((a) => (
                  <tr key={a.id}>
                    <td>{formatDateTime(a.start)}</td>
                    <td>
                      {a.service}
                      <div className={ui.muted}>
                        {formatPhone(a.client)} ·{' '}
                        {a.status === 'requested' ? 'заявка' : 'подтверждена'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}

function OwnerCard({ master }: { readonly master: AdminMasterDetail }) {
  const online = useOnline();
  const [phone, setPhone] = useState('');
  const [touched, setTouched] = useState(false);
  const save = useMasterAction(
    (api, value: string) => api.setOwner(master.id, value),
    'Владелец сохранён — кабинет откроется этому номеру',
  );
  const parsed = parsePhone(phone);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (parsed) save.mutate(parsed, { onSuccess: () => setPhone('') });
  };
  return (
    <section className={ui.card} aria-labelledby="owner">
      <h2 id="owner" className={ui.h2}>
        Владелец
      </h2>
      <p className={ui.muted}>
        {master.owner_phone
          ? `Кабинет открыт номеру ${formatPhone(master.owner_phone)} (вход через Telegram).`
          : 'Владелец не задан — кабинет мастера пока никому не открыт.'}
      </p>
      <form className={ui.toolbar} onSubmit={submit} noValidate aria-label="Сменить владельца">
        <div style={{ flex: '1 1 220px' }}>
          <TextField
            label={master.owner_phone ? 'Новый телефон' : 'Телефон владельца'}
            type="tel"
            inputMode="tel"
            value={phone}
            placeholder="+7 701 123 45 67"
            error={touched && !parsed ? 'Телефон в формате +7 701 123 45 67' : null}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
        <Button type="submit" variant="outline" disabled={save.isPending || !online || !phone}>
          Сохранить
        </Button>
      </form>
    </section>
  );
}
