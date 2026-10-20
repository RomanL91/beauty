import type { Appointment, FeedItem, MasterPage } from '@beauty/api';
import {
  Announcement,
  Bubble,
  BubbleMeta,
  FailedBadge,
  MessageRow,
  SlotButtons,
  Sources,
  SystemPill,
  VoicePlayer,
  formatTime,
} from '@beauty/ui';
import { BookingCard } from '../appointment/BookingCard';

/** Действия, доступные из ленты клиента. */
export interface ClientMessageActions {
  readonly onPickSlot: (offerId: string, start: string) => void;
  readonly onRetry: (clientId: string) => void;
  readonly onReschedule: (appointment: Appointment) => void;
  readonly onCancel: (appointment: Appointment) => void;
}

/**
 * Сообщение в чате клиента по виду (`kind`). Заметки агента клиенту не
 * показываются никогда, даже если сервер ошибочно их прислал.
 */
export function ClientMessageView({
  item,
  master,
  picked,
  actions,
}: {
  readonly item: FeedItem;
  readonly master: MasterPage;
  readonly picked: ReadonlyMap<string, string>;
  readonly actions: ClientMessageActions;
}) {
  const { message, delivery } = item;
  const tz = master.timezone;
  const time = formatTime(message.created_at, tz);
  const mine = message.author === 'client';
  const pending = delivery === 'pending';
  const meta = mine ? (
    delivery === 'failed' ? (
      <FailedBadge onRetry={() => actions.onRetry(message.client_id ?? '')} />
    ) : pending ? (
      <BubbleMeta>Отправляется…</BubbleMeta>
    ) : null
  ) : message.ai_generated ? (
    <BubbleMeta ai>Ответ ИИ · {time}</BubbleMeta>
  ) : (
    <BubbleMeta>
      {message.author === 'master' ? master.name_forms.nominative : 'Администратор'} · {time}
    </BubbleMeta>
  );

  switch (message.kind) {
    case 'agent_note':
    case 'choice':
    case 'task_progress':
    case 'broadcast':
      return null;
    case 'announcement':
      return (
        <MessageRow side="in" wide>
          <Bubble tone="surface" layout="flush">
            <Announcement
              label={`Объявление от ${master.name_forms.genitive}`}
              text={message.text}
              photoUrl={message.photo_url}
            />
          </Bubble>
          <BubbleMeta>{time}</BubbleMeta>
        </MessageRow>
      );
    case 'system':
      return (
        <SystemPill tone={message.tone}>
          {message.text} · {time}
        </SystemPill>
      );
    case 'text':
      return (
        <MessageRow side={mine ? 'out' : 'in'}>
          <Bubble
            tone={mine ? 'accent' : 'surface'}
            layout={message.sources.length ? 'stack' : 'text'}
            pending={pending}
          >
            {message.sources.length ? <span>{message.text}</span> : message.text}
            <Sources items={message.sources} />
          </Bubble>
          {meta}
        </MessageRow>
      );
    case 'voice':
      return (
        <MessageRow side={mine ? 'out' : 'in'} wide>
          <Bubble tone={mine ? 'accent' : 'surface'} pending={pending}>
            <VoicePlayer
              src={message.audio_url}
              duration={message.duration}
              transcript={message.transcript}
              tone={mine ? 'accent' : 'surface'}
            />
          </Bubble>
          {meta}
        </MessageRow>
      );
    case 'slot_offer': {
      const selected = message.selected_start ?? picked.get(message.id) ?? null;
      return (
        <MessageRow side="in">
          <Bubble tone="surface" layout="stack">
            <span>{message.text}</span>
            <SlotButtons
              slots={message.slots}
              selected={selected}
              disabled={false}
              label={(start) => formatTime(start, tz)}
              onPick={(start) => actions.onPickSlot(message.id, start)}
            />
          </Bubble>
          {meta}
        </MessageRow>
      );
    }
    case 'booking_card':
      return (
        <MessageRow side="in" wide>
          <Bubble tone="surface" layout="flush">
            <BookingCard
              appointment={message.appointment}
              timeZone={tz}
              names={master.name_forms}
              onReschedule={() => actions.onReschedule(message.appointment)}
              onCancel={() => actions.onCancel(message.appointment)}
            />
          </Bubble>
          {meta}
        </MessageRow>
      );
  }
}
