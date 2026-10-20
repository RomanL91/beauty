import type { ClientsGateway, MasterClientCard } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContainer } from '../../shared/lib/container-context';
import { inboxKeys } from '../conversation/queries';
import { scheduleKeys } from '../schedule/model';
import { saveErrorText } from '../settings/model';
import { clientKeys } from './model';

/** Клиенты мастера: поиск, фильтр, первые `limit`. */
export function useClients(q: string, filter: 'all' | 'upcoming', limit: number) {
  const { clients } = useContainer();
  return useQuery({
    queryKey: clientKeys.list(q, filter, limit),
    queryFn: () => clients.list({ q: q || undefined, filter, limit }),
    staleTime: 15_000,
    placeholderData: (previous) => previous,
  });
}

/** Карточка клиента. */
export function useClientCard(id: string) {
  const { clients } = useContainer();
  return useQuery({ queryKey: clientKeys.card(id), queryFn: () => clients.card(id) });
}

/**
 * Изменение карточки: ответ — карточка целиком; список клиентов перечитывается, а имя
 * ещё и в чатах и графике (сервер обновит их следом — перечитываем с небольшой задержкой).
 */
export function useClientChange<A>(
  id: string,
  change: (gateway: ClientsGateway, input: A) => Promise<MasterClientCard>,
  success?: string,
  { renames = false }: { renames?: boolean } = {},
) {
  const { clients } = useContainer();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (input: A) => change(clients, input),
    onSuccess: (card) => {
      queryClient.setQueryData(clientKeys.card(id), card);
      void queryClient.invalidateQueries({ queryKey: [...clientKeys.all, 'list'] });
      if (renames)
        setTimeout(() => {
          void queryClient.invalidateQueries({ queryKey: inboxKeys.all });
          void queryClient.invalidateQueries({ queryKey: ['conversation'] });
          void queryClient.invalidateQueries({ queryKey: scheduleKeys.all });
        }, 800);
      if (success) toast({ text: success });
    },
    onError: (error) => toast({ text: saveErrorText(error) }),
  });
}
