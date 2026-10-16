import { ApiError, type Appointment, type DaySchedule } from '@beauty/api';
import { useToast } from '@beauty/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContainer } from '../../shared/lib/container-context';
import { patchAppointment, scheduleKeys } from './model';

/** День графика. */
export function useDay(date: string) {
  const { schedule } = useContainer();
  return useQuery({
    queryKey: scheduleKeys.day(date),
    queryFn: () => schedule.getDay(date),
    staleTime: 30_000,
  });
}

/** Свой профиль мастера (403 `not_a_master` — вход не владельцем страницы). */
export function useProfile(enabled = true) {
  const { schedule } = useContainer();
  return useQuery({
    queryKey: ['profile'],
    queryFn: () => schedule.getProfile(),
    staleTime: 10 * 60_000,
    enabled,
    retry: (count, error) => !(error instanceof ApiError && error.status === 403) && count < 2,
  });
}

type Decision = { kind: 'confirm' } | { kind: 'decline'; offerAlternatives: boolean };

/**
 * Решение по заявке с оптимистичным обновлением: карточка меняется сразу,
 * при ошибке — откат и уведомление; после ответа — сверка с сервером.
 */
export function useAppointmentDecision(date: string | null) {
  const { schedule } = useContainer();
  const queryClient = useQueryClient();
  const toast = useToast();

  return useMutation({
    mutationFn: ({ appointment, decision }: { appointment: Appointment; decision: Decision }) =>
      decision.kind === 'confirm'
        ? schedule.confirm(appointment.id)
        : schedule.decline(appointment.id, { offerAlternatives: decision.offerAlternatives }),
    onMutate: async ({ appointment, decision }) => {
      if (!date) return { previous: undefined };
      const key = scheduleKeys.day(date);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<DaySchedule>(key);
      const optimistic: Appointment =
        decision.kind === 'confirm'
          ? {
              ...base(appointment),
              status: 'confirmed',
              confirmed_at: new Date().toISOString(),
              reminder: 'none',
            }
          : { ...base(appointment), status: 'cancelled', cancelled_by: 'master' };
      if (previous) queryClient.setQueryData(key, patchAppointment(previous, optimistic));
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (date && context?.previous)
        queryClient.setQueryData(scheduleKeys.day(date), context.previous);
      toast({
        text:
          error instanceof ApiError && error.status === 409
            ? 'Заявка уже обработана — обновили график'
            : error instanceof ApiError && error.isNetwork
              ? 'Нет соединения — решение не сохранено'
              : 'Не получилось — попробуйте ещё раз',
      });
    },
    onSuccess: (appointment, { decision }) => {
      toast({
        text:
          decision.kind === 'confirm'
            ? 'Запись подтверждена — клиент получит уведомление'
            : 'Заявка отклонена',
      });
      queryClient.setQueriesData<DaySchedule>({ queryKey: scheduleKeys.all }, (day) =>
        day ? patchAppointment(day, appointment) : day,
      );
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: scheduleKeys.all }),
  });
}

function base(a: Appointment) {
  return {
    id: a.id,
    service: a.service,
    start: a.start,
    end: a.end,
    client: a.client,
    ...(a.note !== undefined && { note: a.note }),
  };
}
