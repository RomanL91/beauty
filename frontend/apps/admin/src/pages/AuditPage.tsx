import { Button, ErrorState, Skeleton, useOnline } from '@beauty/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useAdminApi } from '../shared/lib/container';
import { formatDateTime } from '../shared/lib/format';
import { keys } from '../shared/lib/queries';
import ui from '../shared/ui.module.css';

const ACTIONS: Record<string, string> = {
  'master.created': 'Мастер заведён',
  'master.owner_changed': 'Владелец',
  'master.published': 'Публикация',
  'master.unpublished': 'Страница скрыта',
  'agent.enabled': 'Агент включён',
  'agent.disabled': 'Агент выключен',
  'client.blocked': 'Блокировка',
  'client.unblocked': 'Разблокировка',
  'admin.created': 'Новый администратор',
  'admin.updated': 'Администратор',
  'admin.password_changed': 'Смена пароля',
};

/** Журнал действий администраторов. */
export function AuditPage() {
  const api = useAdminApi();
  const online = useOnline();
  const audit = useInfiniteQuery({
    queryKey: keys.audit,
    queryFn: ({ pageParam }) => api.audit(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => (last.has_more ? last.items.at(-1)?.id : undefined),
  });
  const items = audit.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>Журнал</h1>
          <p className={ui.muted}>Кто и что менял в панели — новые сверху.</p>
        </div>
      </header>
      {audit.data ? (
        items.length === 0 ? (
          <div className={ui.tableWrap}>
            <p className={ui.empty}>Пока ничего не меняли.</p>
          </div>
        ) : (
          <>
            <div className={ui.tableWrap}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>Когда</th>
                    <th>Кто</th>
                    <th>Действие</th>
                    <th>Над чем</th>
                    <th>Подробно</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((e) => (
                    <tr key={e.id}>
                      <td>{formatDateTime(e.at)}</td>
                      <td>{e.admin}</td>
                      <td>{ACTIONS[e.action] ?? e.action}</td>
                      <td>{e.target ?? '—'}</td>
                      <td>{e.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {audit.hasNextPage && (
              <Button
                variant="outline"
                disabled={audit.isFetchingNextPage}
                onClick={() => void audit.fetchNextPage()}
              >
                Показать ещё
              </Button>
            )}
          </>
        )
      ) : audit.isError ? (
        <ErrorState offline={!online} onRetry={() => void audit.refetch()} />
      ) : (
        <Skeleton height={240} radius={18} />
      )}
    </div>
  );
}
