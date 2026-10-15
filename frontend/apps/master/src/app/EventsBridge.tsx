import type { DaySchedule } from '@beauty/api';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { inboxKeys } from '../entities/conversation/queries';
import { hasAppointment, patchAppointment, scheduleKeys } from '../entities/schedule/model';
import { useContainer } from '../shared/lib/container-context';
import { useEventHub } from '../shared/lib/events';

/**
 * Одна SSE-подписка на `/me/events`: записи и чаты патчатся прямо в кэше
 * запросов (обратный отсчёт заявок сверяется с сервером), сообщения уходят
 * в ленты через хаб.
 */
export function EventsBridge() {
  const { events } = useContainer();
  const hub = useEventHub();
  const queryClient = useQueryClient();

  useEffect(
    () =>
      events.subscribe({
        onStateChange: (state) => hub.setState(state),
        onEvent: (event) => {
          switch (event.type) {
            case 'appointment.updated': {
              const { appointment } = event;
              let known = false;
              for (const [, day] of queryClient.getQueriesData<DaySchedule>({
                queryKey: scheduleKeys.all,
              })) {
                if (hasAppointment(day, appointment.id)) known = true;
              }
              if (known) {
                queryClient.setQueriesData<DaySchedule>({ queryKey: scheduleKeys.all }, (day) =>
                  day ? patchAppointment(day, appointment) : day,
                );
              }
              void queryClient.invalidateQueries({ queryKey: scheduleKeys.all });
              break;
            }
            case 'conversation.updated':
              queryClient.setQueryData(
                inboxKeys.conversation(event.conversation.id),
                event.conversation,
              );
              void queryClient.invalidateQueries({ queryKey: inboxKeys.all });
              break;
            default:
              hub.dispatch(event);
          }
        },
      }),
    [events, hub, queryClient],
  );
  return null;
}
