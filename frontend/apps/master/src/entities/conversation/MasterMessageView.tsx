import type { Appointment, FeedItem } from '@beauty/api';
import {
  Announcement,
  Bubble,
  BubbleLabel,
  BubbleMeta,
  Button,
  FailedBadge,
  Icon,
  MessageRow,
  SystemPill,
  VoicePlayer,
  cx,
  formatDayShort,
  formatDuration,
  formatTime,
  useNow,
} from '@beauty/ui';
import styles from './MasterMessage.module.css';

const TRANSCRIPT_WAIT_MS = 2 * 60_000;

/** Действия из ленты диалога. */
export interface DialogActions {
  readonly onRetry: (clientId: string) => void;
  readonly onConfirm: (appointment: Appointment) => void;
  readonly onOfferOther: (appointment: Appointment) => void;
  readonly busyAppointmentId: string | null;
}

/**
 * Сообщение диалога глазами мастера: клиент слева, агент и мастер справа;
 * заметки агента — отдельной карточкой «видите только вы».
 */
export function MasterMessageView({
  item,
  timeZone,
  actions,
}: {
  readonly item: FeedItem;
  readonly timeZone: string;
  readonly actions: DialogActions;
}) {
  const { message, delivery } = item;
  const time = formatTime(message.created_at, timeZone);
  const fromClient = message.author === 'client';
  const label =
    message.author === 'agent' ? (
      <BubbleLabel>
        Агент · {time}
        {message.sources.length > 0 &&
          ` · по ${message.sources.map((s) => `памятке «${s.title}»`).join(', ')}`}
      </BubbleLabel>
    ) : message.author === 'master' ? (
      <BubbleLabel>Вы · {delivery === 'pending' ? 'отправляется…' : time}</BubbleLabel>
    ) : null;
  const failed =
    delivery === 'failed' ? (
      <FailedBadge onRetry={() => actions.onRetry(message.client_id ?? '')} />
    ) : null;
  const tone = message.author === 'master' ? 'accent' : 'soft';

  switch (message.kind) {
    case 'agent_note':
      return (
        <div className={styles.note}>
          <Icon name="eye" size={18} strokeWidth={1.8} />
          <div className={styles.noteBody}>
            <span className={styles.noteTitle}>Заметка агента · видите только вы</span>
            <span className={styles.noteText}>{message.text}</span>
          </div>
        </div>
      );
    case 'system':
      return (
        <SystemPill tone={message.tone}>
          {message.text} · {time}
        </SystemPill>
      );
    case 'booking_card':
      return (
        <DialogBookingCard
          appointment={message.appointment}
          timeZone={timeZone}
          actions={actions}
        />
      );
    case 'text':
      return fromClient ? (
        <MessageRow side="in">
          <Bubble tone="surface">{message.text}</Bubble>
          <BubbleMeta>{time}</BubbleMeta>
        </MessageRow>
      ) : (
        <MessageRow side="out">
          {label}
          <Bubble tone={tone} pending={delivery === 'pending'}>
            {message.text}
          </Bubble>
          {failed}
        </MessageRow>
      );
    case 'voice':
      return (
        <MessageRow side={fromClient ? 'in' : 'out'}>
          {label}
          <Bubble tone={fromClient ? 'surface' : tone} layout="stack">
            <div className={styles.voiceCol}>
              <span className={styles.voiceLabel}>
                Голосовое {formatDuration(message.duration)}
                {message.transcript ? (
                  ' · расшифровка'
                ) : (
                  <TranscriptPending createdAt={message.created_at} />
                )}
              </span>
              {message.transcript && <span>«{message.transcript}»</span>}
            </div>
            <VoicePlayer src={message.audio_url} duration={message.duration} tone="surface" />
          </Bubble>
          {fromClient && <BubbleMeta>{time}</BubbleMeta>}
        </MessageRow>
      );
    case 'slot_offer':
      return (
        <MessageRow side="out">
          {label}
          <Bubble tone="soft" layout="stack">
            <span>{message.text}</span>
            <div className={styles.times}>
              {message.slots.map((s) => (
                <span
                  key={s.start}
                  className={cx(
                    styles.timeChip,
                    message.selected_start === s.start && styles.timeChipOn,
                  )}
                >
                  {formatTime(s.start, timeZone)}
                </span>
              ))}
            </div>
          </Bubble>
        </MessageRow>
      );
    case 'announcement':
      return (
        <MessageRow side="out" wide>
          <Bubble tone="surface" layout="flush">
            <Announcement
              label="Объявление · рассылка"
              text={message.text}
              photoUrl={message.photo_url}
            />
          </Bubble>
          <BubbleMeta>{formatTime(message.created_at, timeZone)}</BubbleMeta>
        </MessageRow>
      );
    case 'choice':
    case 'task_progress':
    case 'broadcast':
      return null;
  }
}

function DialogBookingCard({
  appointment,
  timeZone,
  actions,
}: {
  readonly appointment: Appointment;
  readonly timeZone: string;
  readonly actions: DialogActions;
}) {
  const busy = actions.busyAppointmentId === appointment.id;
  const what = `${formatDayShort(appointment.start, timeZone)} · ${formatTime(appointment.start, timeZone)}–${formatTime(appointment.end, timeZone)} · ${appointment.service.title}`;
  return (
    <div
      className={cx(
        styles.request,
        appointment.status === 'confirmed' && styles.confirmed,
        (appointment.status === 'cancelled' || appointment.status === 'completed') &&
          styles.cancelled,
      )}
    >
      <span className={styles.tag}>
        {appointment.status === 'requested' && 'Заявка · держим слот'}
        {appointment.status === 'confirmed' && 'Запись подтверждена'}
        {appointment.status === 'cancelled' && 'Заявка отклонена'}
        {appointment.status === 'completed' && 'Визит состоялся'}
      </span>
      <span className={styles.what}>{what}</span>
      {appointment.status === 'requested' && (
        <div className={styles.buttons}>
          <Button disabled={busy} onClick={() => actions.onConfirm(appointment)}>
            Подтвердить
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => actions.onOfferOther(appointment)}
          >
            Предложить другое
          </Button>
        </div>
      )}
    </div>
  );
}

/** Расшифровка ещё идёт — первые минуты после отправки (дальше её уже не будет). */
function TranscriptPending({ createdAt }: { readonly createdAt: string }) {
  const now = useNow(15_000);
  return now - Date.parse(createdAt) < TRANSCRIPT_WAIT_MS ? ' · расшифровываем…' : null;
}
