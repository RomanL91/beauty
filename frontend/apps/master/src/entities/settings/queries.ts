import type { MasterSettings } from '@beauty/api';
import type { MasterSettingsGateway } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContainer } from '../../shared/lib/container-context';
import { scheduleKeys } from '../schedule/model';
import { saveErrorText, settingsKey } from './model';

/** Настройки страницы мастера. */
export function useSettings() {
  const { settings } = useContainer();
  return useQuery({ queryKey: settingsKey, queryFn: () => settings.get(), staleTime: 60_000 });
}

/**
 * Изменение настроек: ответ сервера — настройки целиком, они сразу становятся данными
 * экрана и профиля; график перечитывается (часы и выходные меняют дни). Ошибка — тост
 * и `error` у мутации (форма показывает её у полей).
 */
export function useSettingsChange<A>(
  change: (gateway: MasterSettingsGateway, input: A) => Promise<MasterSettings>,
  success?: string,
) {
  const { settings } = useContainer();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (input: A) => change(settings, input),
    onSuccess: (next) => {
      queryClient.setQueryData(settingsKey, next);
      queryClient.setQueryData(['profile'], next.page);
      void queryClient.invalidateQueries({ queryKey: scheduleKeys.all });
      if (success) toast({ text: success });
    },
    onError: (error) => toast({ text: saveErrorText(error) }),
  });
}
