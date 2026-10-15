import type { ConversationFilter } from '@beauty/api';
import { useQuery } from '@tanstack/react-query';
import { useContainer } from '../../shared/lib/container-context';

/** Ключи кэша чатов. */
export const inboxKeys = {
  all: ['inbox'] as const,
  list: (filter: ConversationFilter, q: string) => ['inbox', filter, q] as const,
  conversation: (id: string) => ['conversation', id] as const,
};

/** Список чатов. */
export function useInbox(filter: ConversationFilter, q: string) {
  const { inbox } = useContainer();
  return useQuery({
    queryKey: inboxKeys.list(filter, q),
    queryFn: () => inbox.list(filter, q || undefined),
    staleTime: 15_000,
    placeholderData: (previous) => previous,
  });
}

/** Шапка диалога. */
export function useConversation(id: string) {
  const { inbox } = useContainer();
  return useQuery({ queryKey: inboxKeys.conversation(id), queryFn: () => inbox.get(id) });
}
