import type { ConversationFilter, ConversationSummary } from '@beauty/api';
import {
  Avatar,
  Badge,
  ErrorState,
  Skeleton,
  StateView,
  cx,
  formatListTime,
  useOnline,
  visuallyHiddenStyle,
} from '@beauty/ui';
import { useDeferredValue, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useInbox } from '../../entities/conversation/queries';
import { useProfile } from '../../entities/schedule/queries';
import { DEFAULT_TZ } from '../../shared/lib/dates';
import { BottomNav } from '../../widgets/bottom-nav/BottomNav';
import styles from './ChatsPage.module.css';

const TABS: Array<{ id: ConversationFilter; label: string }> = [
  { id: 'all', label: 'Все' },
  { id: 'needs_me', label: 'Нужны вы' },
  { id: 'agent', label: 'Ведёт агент' },
  { id: 'me', label: 'Веду я' },
];

const isFilter = (v: string | null): v is ConversationFilter => TABS.some((t) => t.id === v);

/** Экран «Все чаты» (макет MasterChats). */
export function ChatsPage() {
  const [params, setParams] = useSearchParams();
  const filter: ConversationFilter = isFilter(params.get('filter'))
    ? (params.get('filter') as ConversationFilter)
    : 'all';
  const [query, setQuery] = useState(params.get('q') ?? '');
  const deferred = useDeferredValue(query.trim());
  const [debounced, setDebounced] = useState(deferred);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(deferred), 300);
    return () => clearTimeout(t);
  }, [deferred]);

  const inbox = useInbox(filter, debounced);
  const tz = useProfile().data?.timezone ?? DEFAULT_TZ;
  const online = useOnline();
  const counts = inbox.data?.counts;

  const setFilter = (next: ConversationFilter) =>
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
        <h1 className={styles.h1}>Чаты</h1>
        <label htmlFor="search" style={visuallyHiddenStyle}>
          Поиск по клиентам
        </label>
        <input
          id="search"
          type="search"
          className={styles.search}
          placeholder="Имя, телефон или текст"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div role="tablist" aria-label="Фильтр" className={styles.tabs}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={filter === tab.id}
              className={styles.tab}
              onClick={() => setFilter(tab.id)}
            >
              {tab.label}
              {tab.id === 'needs_me' && counts && counts.needs_me > 0
                ? ` · ${counts.needs_me}`
                : ''}
            </button>
          ))}
        </div>
      </header>

      {inbox.isPending ? (
        <ListSkeleton />
      ) : inbox.isError ? (
        <div className={styles.empty}>
          <ErrorState offline={!online} onRetry={() => void inbox.refetch()} />
        </div>
      ) : inbox.data.items.length === 0 ? (
        <div className={styles.empty}>
          <StateView
            icon="chat"
            title={
              debounced
                ? 'Ничего не нашли'
                : filter === 'needs_me'
                  ? 'Всё под контролем'
                  : 'Чатов нет'
            }
            text={
              debounced
                ? 'Попробуйте имя, последние цифры телефона или слово из переписки.'
                : filter === 'needs_me'
                  ? 'Агент справляется сам — позовёт, если понадобитесь.'
                  : undefined
            }
          />
        </div>
      ) : (
        <ul className={styles.list} aria-busy={inbox.isFetching}>
          {inbox.data.items.map((c) => (
            <li key={c.id}>
              <ConversationRow conversation={c} timeZone={tz} />
            </li>
          ))}
        </ul>
      )}
      <BottomNav />
    </>
  );
}

function ConversationRow({
  conversation: c,
  timeZone,
}: {
  readonly conversation: ConversationSummary;
  readonly timeZone: string;
}) {
  const last = c.last_message;
  const needsMe = c.needs_me !== null;
  const prefix =
    needsMe || !last
      ? ''
      : last.author === 'agent'
        ? 'Агент: '
        : last.author === 'master'
          ? 'Вы: '
          : '';
  return (
    <Link to={`/chats/${c.id}`} className={cx(styles.item, needsMe && styles.needsMe)}>
      <Avatar name={c.client.display_name} size={46} anonymous={c.client.visit_number === 1} />
      <div className={styles.body}>
        <div className={styles.top}>
          <span className={styles.name}>{c.client.display_name}</span>
          {last && <span className={styles.time}>{formatListTime(last.created_at, timeZone)}</span>}
        </div>
        {last && (
          <span className={cx(styles.preview, needsMe && styles.previewStrong)}>
            {prefix}
            {last.preview}
          </span>
        )}
        {c.needs_me === 'request' && <Badge tone="warn">Нужны вы · заявка</Badge>}
        {c.needs_me === 'question' && <Badge tone="warn">Нужны вы · вопрос</Badge>}
        {!needsMe && c.handler === 'agent' && <Badge tone="accent">Ведёт агент</Badge>}
        {!needsMe && c.handler === 'master' && <Badge tone="muted">Веду я · агент на паузе</Badge>}
      </div>
    </Link>
  );
}

function ListSkeleton() {
  return (
    <ul className={styles.list} aria-busy="true" aria-label="Загрузка чатов">
      {[0, 1, 2, 3, 4].map((i) => (
        <li key={i} className={styles.item}>
          <Skeleton width={46} height={46} radius="50%" />
          <div className={styles.body}>
            <Skeleton width="45%" height={15} />
            <Skeleton width="85%" height={13} />
            <Skeleton width={90} height={18} radius={8} />
          </div>
        </li>
      ))}
    </ul>
  );
}
