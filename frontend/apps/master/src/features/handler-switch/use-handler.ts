import type { ConversationSummary, Handler } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { inboxKeys } from '../../entities/conversation/queries';
import { useContainer } from '../../shared/lib/container-context';

/** Переключатель «Агент / Я» с оптимистичным обновлением и откатом. */
export function useSetHandler(conversationId: string) {
  const { inbox } = useContainer();
  const queryClient = useQueryClient();
  const toast = useToast();
  const key = inboxKeys.conversation(conversationId);

  return useMutation({
    mutationFn: (handler: Handler) => inbox.setHandler(conversationId, handler),
    onMutate: async (handler) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<ConversationSummary>(key);
      if (previous) queryClient.setQueryData(key, { ...previous, handler });
      return { previous };
    },
    onError: (_error, _handler, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
      toast({ text: 'Не получилось переключить — попробуйте ещё раз' });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: inboxKeys.all }),
  });
}

/** Отметить в кэше, что диалог ведёт мастер (после его ответа). */
export function markHandledByMaster(
  queryClient: ReturnType<typeof useQueryClient>,
  conversationId: string,
): Handler | null {
  const key = inboxKeys.conversation(conversationId);
  const current = queryClient.getQueryData<ConversationSummary>(key);
  if (!current) return null;
  queryClient.setQueryData(key, { ...current, handler: 'master', needs_me: null });
  return current.handler;
}
