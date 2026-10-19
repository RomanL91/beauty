import type { AdminMasterDetail, ClientQuery, MasterStatus } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAdminApi } from './container';
import { errorText } from './session';

export const keys = {
  dashboard: ['admin', 'dashboard'] as const,
  masters: (q: string, status: MasterStatus | null) => ['admin', 'masters', q, status] as const,
  master: (id: string) => ['admin', 'master', id] as const,
  clients: (query: ClientQuery) => ['admin', 'clients', query] as const,
  agent: ['admin', 'agent'] as const,
  system: ['admin', 'system'] as const,
  admins: ['admin', 'admins'] as const,
  audit: ['admin', 'audit'] as const,
};

export function useDashboard() {
  const api = useAdminApi();
  return useQuery({ queryKey: keys.dashboard, queryFn: () => api.dashboard(), staleTime: 60_000 });
}

export function useMasters(q: string, status: MasterStatus | null) {
  const api = useAdminApi();
  return useQuery({
    queryKey: keys.masters(q, status),
    queryFn: () => api.masters({ q, ...(status ? { status } : {}) }),
    placeholderData: (previous) => previous,
  });
}

export function useMaster(id: string) {
  const api = useAdminApi();
  return useQuery({ queryKey: keys.master(id), queryFn: () => api.master(id) });
}

/**
 * Действие над мастером: ответ — карточка целиком; списки и журнал перечитываются.
 * Ошибка — тостом (и в `error` мутации для формы).
 */
export function useMasterAction<A>(
  action: (api: ReturnType<typeof useAdminApi>, input: A) => Promise<AdminMasterDetail>,
  success?: string,
) {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (input: A) => action(api, input),
    onSuccess: (master) => {
      queryClient.setQueryData(keys.master(master.id), master);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'masters'] });
      void queryClient.invalidateQueries({ queryKey: keys.audit });
      void queryClient.invalidateQueries({ queryKey: keys.dashboard });
      if (success) toast({ text: success });
    },
    onError: (error) => toast({ text: errorText(error) }),
  });
}

export function useClients(query: ClientQuery) {
  const api = useAdminApi();
  return useQuery({
    queryKey: keys.clients(query),
    queryFn: () => api.clients(query),
    placeholderData: (previous) => previous,
  });
}

export function useAgentReport() {
  const api = useAdminApi();
  return useQuery({ queryKey: keys.agent, queryFn: () => api.agent(), staleTime: 60_000 });
}

export function useSystem() {
  const api = useAdminApi();
  return useQuery({ queryKey: keys.system, queryFn: () => api.system(), refetchInterval: 30_000 });
}

export function useAdmins() {
  const api = useAdminApi();
  return useQuery({ queryKey: keys.admins, queryFn: () => api.admins() });
}
