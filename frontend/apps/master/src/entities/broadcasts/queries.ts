import type { Broadcast, BroadcastsGateway } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContainer } from '../../shared/lib/container-context';
import { inboxKeys } from '../conversation/queries';
import { broadcastErrorText, broadcastKeys } from './model';

/** Пока рассылка доставляется — перечитываем раз в 2 с. */
const whileSending = (broadcast: Broadcast | undefined) =>
  broadcast?.status === 'sending' ? 2000 : false;

/** Рассылки мастера. */
export function useBroadcasts() {
  const { broadcasts } = useContainer();
  return useQuery({
    queryKey: broadcastKeys.list,
    queryFn: () => broadcasts.list(),
    refetchInterval: (query) =>
      query.state.data?.items.some((b) => b.status === 'sending') ? 2000 : false,
  });
}

/** Одна рассылка (карточка черновика в ленте поручений). */
export function useBroadcast(id: string) {
  const { broadcasts } = useContainer();
  return useQuery({
    queryKey: broadcastKeys.one(id),
    queryFn: () => broadcasts.get(id),
    refetchInterval: (query) => whileSending(query.state.data),
    retry: false,
  });
}

/** Изменение рассылки: ответ — рассылка целиком; список и чаты перечитываются. */
export function useBroadcastChange<A>(
  change: (gateway: BroadcastsGateway, input: A) => Promise<Broadcast | void>,
  success?: string,
) {
  const { broadcasts } = useContainer();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (input: A) => change(broadcasts, input),
    onSuccess: (next) => {
      if (next) queryClient.setQueryData(broadcastKeys.one(next.id), next);
      void queryClient.invalidateQueries({ queryKey: broadcastKeys.all });
      if (next?.status !== 'draft') void queryClient.invalidateQueries({ queryKey: inboxKeys.all });
      if (success) toast({ text: success });
    },
    onError: (error) => toast({ text: broadcastErrorText(error) }),
  });
}
