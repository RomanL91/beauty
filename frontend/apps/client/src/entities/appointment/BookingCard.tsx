import { formatRemainingLong, remaining, type Appointment, type NameForms } from '@beauty/api';
import { Icon, cx, formatDayShort, formatMoney, formatTime, useNow } from '@beauty/ui';
import styles from './BookingCard.module.css';

/**
 * Карточка заявки/записи в чате клиента. Статус — текущий (карточка
 * обновляется событием `message.updated`); таймер удержания тикает локально
 * от `hold_until`.
 */
export function BookingCard({
  appointment,
  timeZone,
  names,
  onReschedule,
  onCancel,
}: {
  readonly appointment: Appointment;
  readonly timeZone: string;
  readonly names: NameForms;
  readonly onReschedule: () => void;
  readonly onCancel: () => void;
}) {
  const requested = appointment.status === 'requested';
  const now = useNow(30_000, requested);
  const left = requested ? remaining(appointment.hold_until, now) : null;
  const when = `${formatDayShort(appointment.start, timeZone)} · ${formatTime(appointment.start, timeZone)}–${formatTime(appointment.end, timeZone)}`;
  const active = appointment.status === 'requested' || appointment.status === 'confirmed';

  return (
    <div className={styles.card} id={`appointment-${appointment.id}`}>
      <div className={cx(styles.head, styles[appointment.status])}>
        <Icon
          name={appointment.status === 'confirmed' ? 'check' : 'clock'}
          size={16}
          strokeWidth={2}
        />
        {appointment.status === 'requested' && `Ждёт подтверждения ${names.genitive}`}
        {appointment.status === 'confirmed' && 'Запись подтверждена'}
        {appointment.status === 'cancelled' && 'Запись отменена'}
        {appointment.status === 'completed' && 'Визит состоялся'}
        {left && !left.expired && (
          <span className={styles.left} aria-label={`Держим ещё ${formatRemainingLong(left)}`}>
            {formatRemainingLong(left)}
          </span>
        )}
      </div>
      <div className={styles.body}>
        <span className={cx(styles.when, appointment.status === 'cancelled' && styles.struck)}>
          {when}
        </span>
        <span className={styles.what}>
          {appointment.service.title} · {formatMoney(appointment.service.price)}
        </span>
        {appointment.status === 'requested' && (
          <span className={styles.note}>
            Время держим за вами. {names.nominative} ответит до{' '}
            {formatTime(appointment.auto_decline_at, timeZone)}, иначе пришлём новые варианты.
          </span>
        )}
        {appointment.status === 'confirmed' && (
          <span className={styles.note}>
            Напомним накануне. Перенести или отменить можно здесь.
          </span>
        )}
      </div>
      {active && (
        <div className={styles.actions}>
          <button type="button" className={styles.action} onClick={onReschedule}>
            Перенести
          </button>
          <button type="button" className={styles.action} onClick={onCancel}>
            Отменить
          </button>
        </div>
      )}
    </div>
  );
}
