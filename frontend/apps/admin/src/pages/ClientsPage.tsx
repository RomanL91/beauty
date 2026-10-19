import type { AdminClientRow } from '@beauty/api';
import {
  Badge,
  Button,
  ErrorState,
  Sheet,
  Skeleton,
  TextArea,
  useOnline,
  useToast,
} from '@beauty/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useDeferredValue, useState } from 'react';
import { useAdminApi } from '../shared/lib/container';
import { formatDateTime, formatNumber, formatPhone } from '../shared/lib/format';
import { keys, useClients } from '../shared/lib/queries';
import { errorText } from '../shared/lib/session';
import ui from '../shared/ui.module.css';

const PAGE = 50;

/** Клиенты платформы: поиск по телефону, блокировка. */
export function ClientsPage() {
  const [q, setQ] = useState('');
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [target, setTarget] = useState<AdminClientRow | null>(null);
  const query = useDeferredValue(q.replace(/\D/g, ''));
  const clients = useClients({ q: query, blocked: blockedOnly ? true : undefined, limit });
  const online = useOnline();
  const block = useBlock(() => setTarget(null));

  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>Клиенты</h1>
          <p className={ui.muted}>
            Все учётные записи платформы
            {clients.data ? ` — ${formatNumber(clients.data.total)}` : ''}.
          </p>
        </div>
      </header>
      <div className={ui.toolbar}>
        <input
          type="search"
          inputMode="tel"
          className={ui.search}
          placeholder="Цифры телефона"
          aria-label="Поиск по телефону"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className={ui.chips} role="group" aria-label="Фильтр">
          <button
            type="button"
            className={ui.chip}
            aria-pressed={!blockedOnly}
            onClick={() => setBlockedOnly(false)}
          >
            Все
          </button>
          <button
            type="button"
            className={ui.chip}
            aria-pressed={blockedOnly}
            onClick={() => setBlockedOnly(true)}
          >
            Заблокированные
          </button>
        </div>
      </div>
      {clients.data ? (
        clients.data.items.length === 0 ? (
          <div className={ui.tableWrap}>
            <p className={ui.empty}>Никого не нашли.</p>
          </div>
        ) : (
          <>
            <div className={ui.tableWrap}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>Телефон</th>
                    <th>Мастера</th>
                    <th className={ui.num}>Записи</th>
                    <th>С нами с</th>
                    <th>Последний вход</th>
                    <th>Статус</th>
                    <th aria-label="Действия" />
                  </tr>
                </thead>
                <tbody>
                  {clients.data.items.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <strong>{formatPhone(c.phone)}</strong>
                      </td>
                      <td>{c.masters.join(', ') || '—'}</td>
                      <td className={ui.num}>{formatNumber(c.appointments)}</td>
                      <td>{formatDateTime(c.created_at)}</td>
                      <td>{formatDateTime(c.last_login_at)}</td>
                      <td>
                        {c.blocked ? (
                          <span title={c.blocked_reason ?? undefined}>
                            <Badge tone="warn">Заблокирован</Badge>
                          </span>
                        ) : (
                          <Badge tone="ok">Активен</Badge>
                        )}
                      </td>
                      <td>
                        {c.blocked ? (
                          <Button
                            variant="ghost"
                            disabled={block.isPending || !online}
                            onClick={() => block.mutate({ client: c, blocked: false })}
                          >
                            Разблокировать
                          </Button>
                        ) : (
                          <Button variant="ghost" disabled={!online} onClick={() => setTarget(c)}>
                            Заблокировать
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {clients.data.total > clients.data.items.length && (
              <Button variant="outline" onClick={() => setLimit((l) => l + PAGE)}>
                Показать ещё
              </Button>
            )}
          </>
        )
      ) : clients.isError ? (
        <ErrorState offline={!online} onRetry={() => void clients.refetch()} />
      ) : (
        <Skeleton height={240} radius={18} />
      )}
      <Sheet open={target !== null} title="Заблокировать клиента" onClose={() => setTarget(null)}>
        {target && (
          <BlockForm
            client={target}
            pending={block.isPending}
            onBlock={(reason) => block.mutate({ client: target, blocked: true, reason })}
          />
        )}
      </Sheet>
    </div>
  );
}

function useBlock(onDone: () => void) {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({
      client,
      blocked,
      reason,
    }: {
      client: AdminClientRow;
      blocked: boolean;
      reason?: string;
    }) => api.setClientBlock(client.id, blocked, reason),
    onSuccess: (client) => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'clients'] });
      void queryClient.invalidateQueries({ queryKey: keys.audit });
      void queryClient.invalidateQueries({ queryKey: keys.dashboard });
      toast({
        text: client.blocked ? 'Клиент заблокирован — его сессии закрыты' : 'Клиент разблокирован',
      });
      onDone();
    },
    onError: (error) => toast({ text: errorText(error) }),
  });
}

function BlockForm({
  client,
  pending,
  onBlock,
}: {
  readonly client: AdminClientRow;
  readonly pending: boolean;
  readonly onBlock: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  return (
    <div className={ui.form}>
      <p className={ui.muted}>
        {formatPhone(client.phone)} не сможет войти, его сессии закроются сразу. Записи и переписка
        сохранятся; разблокировать можно здесь же.
      </p>
      <TextArea
        label="Причина (видна только в панели)"
        value={reason}
        maxLength={300}
        rows={3}
        onChange={(e) => setReason(e.target.value)}
      />
      <Button size="lg" block disabled={pending} onClick={() => onBlock(reason.trim())}>
        Заблокировать
      </Button>
    </div>
  );
}
