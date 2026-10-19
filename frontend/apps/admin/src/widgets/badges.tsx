import type { AgentState, MasterStatus } from '@beauty/api';
import { Badge } from '@beauty/ui';

/** Статус страницы. */
export function StatusBadge({ status }: { readonly status: MasterStatus }) {
  return status === 'published' ? (
    <Badge tone="ok">Опубликована</Badge>
  ) : (
    <Badge tone="warn">Черновик</Badge>
  );
}

/** ИИ-администратор мастера. */
export function AgentBadge({ state }: { readonly state: AgentState }) {
  if (state === 'enabled') return <Badge tone="accent">Включён</Badge>;
  if (state === 'disabled') return <Badge tone="muted">Выключен</Badge>;
  return <Badge tone="muted">Не подключён</Badge>;
}
