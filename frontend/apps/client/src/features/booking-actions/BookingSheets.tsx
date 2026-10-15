import { ApiError, type Appointment, type MasterPage } from '@beauty/api';
import {
  Button,
  Sheet,
  Skeleton,
  formatDayShort,
  formatSlotShort,
  formatTime,
  useToast,
} from '@beauty/ui';
import { useMutation } from '@tanstack/react-query';
import { PushPrompt } from '@beauty/pwa/PushPrompt';
import type { usePushSubscription } from '@beauty/pwa/push';
import { useState } from 'react';
import { useSlots } from '../../entities/master/queries';
import { useContainer } from '../../shared/lib/container-context';
import styles from './BookingSheets.module.css';

function errorText(error: unknown): string {
  if (error instanceof ApiError && error.isNetwork) return 'Нет соединения — попробуйте ещё раз';
  if (error instanceof ApiError && error.status === 409)
    return 'Запись уже изменилась — обновили карточку';
  return 'Не получилось — попробуйте ещё раз';
}

/** Подтверждение отмены записи. */
export function CancelSheet({
  appointment,
  master,
  onClose,
  onDone,
}: {
  readonly appointment: Appointment | null;
  readonly master: MasterPage;
  readonly onClose: () => void;
  readonly onDone: (appointment: Appointment) => void;
}) {
  const { conversations } = useContainer();
  const toast = useToast();
  const cancel = useMutation({
    mutationFn: (id: string) => conversations.cancelAppointment(id),
    onSuccess: (updated) => {
      onDone(updated);
      onClose();
    },
    onError: (error) => toast({ text: errorText(error) }),
  });
  const tz = master.timezone;
  return (
    <Sheet open={appointment !== null} title="Отменить запись?" onClose={onClose}>
      {appointment && (
        <>
          <p className={styles.text}>
            {appointment.service.title}, {formatDayShort(appointment.start, tz)} в{' '}
            {formatTime(appointment.start, tz)}. Окно освободится для других клиентов.
          </p>
          <div className={styles.row}>
            <Button variant="outline" size="lg" onClick={onClose}>
              Не отменять
            </Button>
            <Button
              size="lg"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(appointment.id)}
            >
              {cancel.isPending ? 'Отменяем…' : 'Отменить'}
            </Button>
          </div>
        </>
      )}
    </Sheet>
  );
}

/** Перенос: выбрать новое окно для той же услуги. */
export function RescheduleSheet({
  appointment,
  master,
  onClose,
  onDone,
}: {
  readonly appointment: Appointment | null;
  readonly master: MasterPage;
  readonly onClose: () => void;
  readonly onDone: (appointment: Appointment) => void;
}) {
  const { conversations } = useContainer();
  const toast = useToast();
  const [start, setStart] = useState<string | null>(null);
  const slots = useSlots(appointment?.service.id, 12, appointment !== null);
  const reschedule = useMutation({
    mutationFn: (args: { id: string; start: string }) =>
      conversations.rescheduleAppointment(args.id, args.start),
    onSuccess: (updated) => {
      toast({ text: `Запросили перенос — ${master.name_forms.nominative} подтвердит` });
      onDone(updated);
      setStart(null);
      onClose();
    },
    onError: (error) => toast({ text: errorText(error) }),
  });
  return (
    <Sheet open={appointment !== null} title="Перенести запись" onClose={onClose}>
      {appointment && (
        <>
          <p className={styles.text}>
            Сейчас: {formatDayShort(appointment.start, master.timezone)},{' '}
            {formatTime(appointment.start, master.timezone)}. Выберите новое время:
          </p>
          {slots.isPending ? (
            <div className={styles.slots}>
              {[90, 90, 90, 90].map((w, i) => (
                <Skeleton key={i} width={w} height={44} radius={12} />
              ))}
            </div>
          ) : slots.isError || slots.data.length === 0 ? (
            <p className={styles.text}>
              Свободных окон не нашли — напишите в чат, подберём вместе.
            </p>
          ) : (
            <div className={styles.slots} role="group" aria-label="Новое время">
              {slots.data
                .filter((s) => s.start !== appointment.start)
                .map((s) => (
                  <button
                    key={s.start}
                    type="button"
                    className={styles.slot}
                    aria-pressed={start === s.start}
                    onClick={() => setStart(s.start)}
                  >
                    {formatSlotShort(s.start, master.timezone)}
                  </button>
                ))}
            </div>
          )}
          <Button
            size="lg"
            block
            disabled={!start || reschedule.isPending}
            onClick={() => start && reschedule.mutate({ id: appointment.id, start })}
          >
            {reschedule.isPending ? 'Отправляем…' : 'Перенести'}
          </Button>
        </>
      )}
    </Sheet>
  );
}

/** «Мои записи»: активные записи из переписки. */
export function MyBookingsSheet({
  open,
  appointments,
  master,
  onClose,
  onShow,
  onLogout,
  push,
}: {
  readonly open: boolean;
  readonly appointments: readonly Appointment[];
  readonly master: MasterPage;
  readonly onClose: () => void;
  readonly onShow: (appointment: Appointment) => void;
  readonly onLogout: () => void;
  readonly push: ReturnType<typeof usePushSubscription>;
}) {
  const tz = master.timezone;
  return (
    <Sheet open={open} title="Мои записи" onClose={onClose}>
      {appointments.length === 0 ? (
        <p className={styles.text}>
          Активных записей нет. Напишите в чат — администратор подберёт время.
        </p>
      ) : (
        <ul className={styles.list}>
          {appointments.map((a) => (
            <li key={a.id}>
              <button type="button" className={styles.item} onClick={() => onShow(a)}>
                <span className={styles.itemTitle}>
                  {formatDayShort(a.start, tz)} · {formatTime(a.start, tz)}
                </span>
                <span className={styles.itemMeta}>
                  {a.service.title} ·{' '}
                  {a.status === 'confirmed' ? 'подтверждена' : 'ждёт подтверждения'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <PushPrompt
        push={push}
        variant="settings"
        reason="Напоминания о визитах и ответы мастера — уведомлением."
      />
      <Button variant="ghost" onClick={onLogout}>
        Выйти из аккаунта
      </Button>
    </Sheet>
  );
}
