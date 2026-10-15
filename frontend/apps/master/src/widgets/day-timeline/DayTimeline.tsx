import {
  formatRemainingLong,
  remaining,
  type Appointment,
  type DaySchedule,
  type ScheduleItem,
} from '@beauty/api';
import { Button, cx, formatMinutes, formatTime, useNow } from '@beauty/ui';
import { useEffect } from 'react';
import { Link } from 'react-router';
import styles from './DayTimeline.module.css';

/** Обработчики решений по заявке. */
export interface DecisionHandlers {
  readonly onConfirm: (appointment: Appointment) => void;
  readonly onDecline: (appointment: Appointment) => void;
  /** Срок автоотклонения прошёл — сверить с сервером. */
  readonly onExpired: () => void;
  readonly busyId: string | null;
}

/** Лента дня: записи, заявки, окна и перерывы. */
export function DayTimeline({
  day,
  timeZone,
  handlers,
}: {
  readonly day: DaySchedule;
  readonly timeZone: string;
  readonly handlers: DecisionHandlers;
}) {
  return (
    <ol
      className={styles.list}
      aria-label="Расписание дня"
      style={{ margin: 0, padding: 0, listStyle: 'none' }}
    >
      {day.items.map((item, index) => (
        <li key={keyOf(item)} className={styles.row}>
          <TimelineItem
            item={item}
            timeZone={timeZone}
            isLastFree={index === day.items.length - 1}
            handlers={handlers}
          />
        </li>
      ))}
    </ol>
  );
}

function keyOf(item: ScheduleItem): string {
  return item.kind === 'appointment' ? item.appointment.id : `${item.kind}-${item.start}`;
}

function TimelineItem({
  item,
  timeZone,
  isLastFree,
  handlers,
}: {
  readonly item: ScheduleItem;
  readonly timeZone: string;
  readonly isLastFree: boolean;
  readonly handlers: DecisionHandlers;
}) {
  if (item.kind === 'free' || item.kind === 'break') {
    const minutes = Math.round((Date.parse(item.end) - Date.parse(item.start)) / 60_000);
    return (
      <>
        <span className={cx(styles.time, styles.timeShort)}>
          {formatTime(item.start, timeZone)}
        </span>
        {item.kind === 'free' ? (
          <div className={styles.free}>
            {isLastFree
              ? `Окно до ${formatTime(item.end, timeZone)} · ${formatMinutes(minutes)}`
              : `Окно ${formatMinutes(minutes)}`}
          </div>
        ) : (
          <div className={styles.break}>{item.title}</div>
        )}
      </>
    );
  }
  const { appointment, conversation_id: conversationId } = item;
  if (appointment.status === 'requested') {
    return (
      <>
        <span className={cx(styles.time, styles.timeWarn)}>
          {formatTime(appointment.start, timeZone)}
        </span>
        <RequestCard
          appointment={appointment}
          timeZone={timeZone}
          conversationId={conversationId}
          handlers={handlers}
        />
      </>
    );
  }
  const reminder =
    appointment.status === 'confirmed' && appointment.reminder === 'read'
      ? 'Напоминание отправлено · прочитано'
      : appointment.status === 'confirmed' && appointment.reminder === 'sent'
        ? 'Напоминание отправлено'
        : null;
  return (
    <>
      <span className={styles.time}>{formatTime(appointment.start, timeZone)}</span>
      <div className={styles.card}>
        <div className={styles.top}>
          <span className={styles.dot} aria-hidden="true" />
          <span className={styles.who}>{appointment.client.display_name}</span>
          <span className={styles.until}>до {formatTime(appointment.end, timeZone)}</span>
        </div>
        <span className={styles.service}>
          {appointment.service.title}
          {appointment.note ? ` · ${appointment.note}` : ''}
        </span>
        {reminder && <span className={styles.meta}>{reminder}</span>}
      </div>
    </>
  );
}

function RequestCard({
  appointment,
  timeZone,
  conversationId,
  handlers,
}: {
  readonly appointment: Extract<Appointment, { status: 'requested' }>;
  readonly timeZone: string;
  readonly conversationId: string | null;
  readonly handlers: DecisionHandlers;
}) {
  const now = useNow(15_000);
  const left = remaining(appointment.auto_decline_at, now);
  const { onExpired } = handlers;
  useEffect(() => {
    if (left.expired) onExpired();
  }, [left.expired, onExpired]);
  const busy = handlers.busyId === appointment.id;
  const visit = appointment.client.visit_number;
  return (
    <div className={styles.request}>
      <div className={styles.requestHead}>
        <span className={styles.tag}>Заявка</span>
        <span className={styles.countdown} role="timer">
          {left.expired ? 'отклоняется…' : `автоотклонение через ${formatRemainingLong(left)}`}
        </span>
      </div>
      <div className={styles.requestWho}>
        <span className={styles.who}>
          {appointment.client.display_name} · до {formatTime(appointment.end, timeZone)}
        </span>
        <span className={styles.service}>
          {appointment.service.title} · {visit === 1 ? 'первый визит' : `${visit}-й визит`}
        </span>
      </div>
      <div className={styles.buttons}>
        <Button disabled={busy || left.expired} onClick={() => handlers.onConfirm(appointment)}>
          Подтвердить
        </Button>
        <Button
          variant="outline"
          disabled={busy || left.expired}
          onClick={() => handlers.onDecline(appointment)}
        >
          Отклонить
        </Button>
      </div>
      {conversationId && (
        <Link to={`/chats/${conversationId}`} className={styles.link}>
          Открыть переписку
        </Link>
      )}
    </div>
  );
}
