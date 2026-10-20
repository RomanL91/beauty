import type { AssistantGateway, Playbook } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContainer } from '../../shared/lib/container-context';
import { playbookErrorText, playbookKeys } from './model';

/** Опыт мастера — что знает ассистент. */
export function usePlaybook() {
  const { assistant } = useContainer();
  return useQuery({ queryKey: playbookKeys.all, queryFn: () => assistant.playbook() });
}

/** Изменение опыта: ответ — опыт целиком. */
export function usePlaybookChange<A>(
  change: (gateway: AssistantGateway, input: A) => Promise<Playbook>,
  success?: string,
) {
  const { assistant } = useContainer();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (input: A) => change(assistant, input),
    onSuccess: (next) => {
      queryClient.setQueryData(playbookKeys.all, next);
      if (success) toast({ text: success });
    },
    onError: (error) => toast({ text: playbookErrorText(error) }),
  });
}
