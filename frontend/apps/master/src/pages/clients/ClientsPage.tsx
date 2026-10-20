import type { MasterClient } from '@beauty/api';
import {
  Avatar,
  Badge,
  Button,
  ErrorState,
  Skeleton,
  StateView,
  formatSlotShort,
  formatDayShort,
  useOnline,
  visuallyHiddenStyle,
} from '@beauty/ui';
import { useDeferredValue, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { notesText, visitsText } from '../../entities/clients/model';
import { useClients } from '../../entities/clients/queries';
import { useProfile } from '../../entities/schedule/queries';
import { DEFAULT_TZ } from '../../shared/lib/dates';
import { BottomNav } from '../../widgets/bottom-nav/BottomNav';
import styles from './Clients.module.css';

const PAGE = 30;
type Filter = 'all' | 'upcoming';

/** «Клиенты»: вся база мастера — поиск, «с записью впереди», переход в карточку. */
export function ClientsPage() {
  const [params, setParams] = useSearchParams();
  const filter: Filter = params.get('filter') === 'upcoming' ? 'upcoming' : 'all';
  const [query, setQuery] = useState(params.get('q') ?? '');
  const deferred = useDeferredValue(query.trim());
  const [debounced, setDebounced] = useState(deferred);
  const [limit, setLimit] = useState(PAGE);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(deferred), 300);
    return () => clearTimeout(t);
  }, [deferred]);

  const clients = useClients(debounced, filter, limit);
  const tz = useProfile().data?.timezone ?? DEFAULT_TZ;
  const online = useOnline();

  const setFilter = (next: Filter) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        if (next === 'all') n.delete('filter');
        else n.set('filter', next);
        return n;
      },
      { replace: true },
    );

  return (
    <>
      <header className={styles.header}>
        <h1 className={styles.h1}>
          Клиенты
          {clients.data && !debounced && filter === 'all' ? (
            <span className={styles.count}> · {clients.data.total}</span>
          ) : null}
        </h1>
        <label htmlFor="client-search" style={visuallyHiddenStyle}>
          Поиск клиентов
        </label>
        <input
          id="client-search"
          type="search"
          className={styles.search}
          placeholder="Имя или последние цифры телефона"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div role="tablist" aria-label="Фильтр" className={styles.tabs}>
          {(
            [
              ['all', 'Все'],
              ['upcoming', 'С записью'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={filter === id}
              className={styles.tab}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      {clients.isPending ? (
        <ListSkeleton />
      ) : clients.isError ? (
        <div className={styles.empty}>
          <ErrorState offline={!online} onRetry={() => void clients.refetch()} />
        </div>
      ) : clients.data.items.length === 0 ? (
        <div className={styles.empty}>
          <StateView
            icon="users"
            title={
              debounced
                ? 'Никого не нашли'
                : filter === 'upcoming'
                  ? 'Записей впереди нет'
                  : 'Клиентов пока нет'
            }
            text={
              debounced
                ? 'Попробуйте имя или последние цифры телефона.'
                : filter === 'upcoming'
                  ? 'Здесь появятся клиенты с заявкой или записью.'
                  : 'Клиент появится здесь, как только напишет вам в чат.'
            }
          />
        </div>
      ) : (
        <>
          <ul className={styles.list} aria-label="Клиенты" aria-busy={clients.isFetching}>
            {clients.data.items.map((client) => (
              <li key={client.id}>
                <ClientRow client={client} timeZone={tz} />
              </li>
            ))}
          </ul>
          {clients.data.items.length < clients.data.total && (
            <div className={styles.more}>
              <Button
                variant="outline"
                block
                disabled={clients.isFetching}
                onClick={() => setLimit((n) => n + PAGE)}
              >
                Показать ещё
              </Button>
            </div>
          )}
        </>
      )}
      <BottomNav />
    </>
  );
}

function ClientRow({
  client,
  timeZone,
}: {
  readonly client: MasterClient;
  readonly timeZone: string;
}) {
  const visits = client.last_visit_at
    ? `${visitsText(client.visits)}, последний ${formatDayShort(client.last_visit_at, timeZone).split(', ')[1]}`
    : visitsText(client.visits);
  return (
    <Link to={`/clients/${client.id}`} className={styles.item}>
      <Avatar name={client.display_name} size={46} anonymous={!client.named} />
      <div className={styles.body}>
        <span className={styles.name}>{client.display_name}</span>
        <span className={styles.meta}>
          {[client.named ? client.phone_masked : null, visits].filter(Boolean).join(' · ')}
        </span>
        <span className={styles.badges}>
          {client.next_visit_at && (
            <Badge tone="accent">Впереди · {formatSlotShort(client.next_visit_at, timeZone)}</Badge>
          )}
          {client.notes > 0 && <Badge tone="muted">{notesText(client.notes)}</Badge>}
        </span>
      </div>
    </Link>
  );
}

function ListSkeleton() {
  return (
    <ul className={styles.list} aria-busy="true" aria-label="Загрузка клиентов">
      {[0, 1, 2, 3, 4].map((i) => (
        <li key={i} className={styles.item}>
          <Skeleton width={46} height={46} radius="50%" />
          <div className={styles.body}>
            <Skeleton width="45%" height={15} />
            <Skeleton width="70%" height={13} />
          </div>
        </li>
      ))}
    </ul>
  );
}
