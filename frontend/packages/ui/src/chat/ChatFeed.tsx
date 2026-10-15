import { Fragment, useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import styles from './ChatFeed.module.css';
import { DaySeparator } from './Chat';
import { Skeleton } from '../components/Skeleton';
import { dateKey, formatDayLong } from '../format';

/** Минимум, который ленте нужно знать об элементе. */
export interface FeedEntry {
  readonly key: string;
  readonly message: { readonly created_at: string; readonly author: string };
}

/**
 * Прокручиваемая лента: разделители дней, подгрузка истории вверх (кнопка +
 * автоматически при прокрутке к началу) с сохранением позиции, прилипание к
 * низу для новых сообщений.
 */
export function ChatFeed({
  feed,
  timeZone,
  older,
  onLoadOlder,
  renderItem,
  empty,
  label,
}: {
  readonly feed: { readonly items: readonly FeedEntry[]; readonly hasMore: boolean };
  readonly timeZone: string;
  readonly older: 'idle' | 'loading' | 'error';
  readonly onLoadOlder: () => void;
  readonly renderItem: (index: number) => ReactNode;
  readonly empty?: ReactNode;
  readonly label: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const firstKey = useRef<string | null>(null);
  const lastKey = useRef<string | null>(null);
  const heightBefore = useRef(0);
  const nearBottom = useRef(true);

  const items = feed.items;
  const head = items[0]?.key ?? null;
  const tail = items.at(-1);

  // Позиция прокрутки: история сверху — сохранить, новое снизу — прилипнуть.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const prependedOlder =
      firstKey.current !== null && head !== firstKey.current && lastKey.current === tail?.key;
    if (prependedOlder) {
      el.scrollTop += el.scrollHeight - heightBefore.current;
    } else if (tail && tail.key !== lastKey.current) {
      const mine = tail.message.author === 'client' || tail.message.author === 'master';
      if (nearBottom.current || mine || lastKey.current === null) el.scrollTop = el.scrollHeight;
    }
    firstKey.current = head;
    lastKey.current = tail?.key ?? null;
    heightBefore.current = el.scrollHeight;
  });

  // Карточка могла вырасти (обновление статуса) — держим низ, если были внизу.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && nearBottom.current) el.scrollTop = el.scrollHeight;
  }, [feed]);

  useEffect(() => {
    const target = sentinel.current;
    const root = scroller.current;
    if (!target || !root || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting) && feed.hasMore && older === 'idle')
          onLoadOlder();
      },
      { root, rootMargin: '200px 0px 0px 0px' },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [feed.hasMore, older, onLoadOlder]);

  const separators: Array<string | null> = [];
  for (let i = 0; i < items.length; i += 1) {
    const created = items[i]!.message.created_at;
    const previous = items[i - 1]?.message.created_at;
    separators.push(
      previous === undefined || dateKey(previous, timeZone) !== dateKey(created, timeZone)
        ? formatDayLong(created, timeZone)
        : null,
    );
  }
  return (
    <div
      ref={scroller}
      className={styles.scroller}
      onScroll={(e) => {
        const el = e.currentTarget;
        nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        heightBefore.current = el.scrollHeight;
      }}
    >
      <div
        className={styles.list}
        role="log"
        aria-label={label}
        aria-live="polite"
        aria-relevant="additions"
      >
        <div ref={sentinel} />
        {feed.hasMore && (
          <div className={styles.older}>
            {older === 'loading' ? (
              <Skeleton width={160} height={20} />
            ) : (
              <button type="button" className={styles.olderButton} onClick={onLoadOlder}>
                {older === 'error' ? 'Не загрузилось — повторить' : 'Показать раньше'}
              </button>
            )}
          </div>
        )}
        {items.length === 0 && empty}
        {items.map((item, index) => (
          <Fragment key={item.key}>
            {separators[index] && <DaySeparator>{separators[index]}</DaySeparator>}
            {renderItem(index)}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

/** Скелетон ленты. */
export function FeedSkeleton() {
  return (
    <div className={styles.list} aria-busy="true" aria-label="Загрузка переписки">
      <Skeleton width={130} height={12} style={{ alignSelf: 'center' }} />
      <Skeleton width="70%" height={42} radius={18} style={{ alignSelf: 'flex-end' }} />
      <Skeleton width="80%" height={96} radius={18} />
      <Skeleton width="30%" height={42} radius={18} style={{ alignSelf: 'flex-end' }} />
      <Skeleton width="86%" height={150} radius={18} />
    </div>
  );
}
