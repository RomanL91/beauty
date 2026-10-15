import type { Appointment, Message, MessageOf, Service, Slot, Source } from '@beauty/api';
import { uuidv7 } from '../ids';
import { plusMinutes } from '../clock';

type Base = Pick<Message, 'id' | 'author' | 'ai_generated' | 'sources' | 'created_at'> & {
  client_id?: string | null;
};

/** Общие поля сообщения. */
export function base(
  author: Message['author'],
  createdAt: string,
  extra: { ai?: boolean; sources?: Source[]; clientId?: string | null; id?: string } = {},
): Base {
  return {
    id: extra.id ?? uuidv7(Date.parse(createdAt)),
    client_id: extra.clientId ?? null,
    author,
    ai_generated: extra.ai ?? author === 'agent',
    sources: extra.sources ?? [],
    created_at: createdAt,
  };
}

export const text = (b: Base, body: string): MessageOf<'text'> => ({
  ...b,
  kind: 'text',
  text: body,
});

export const voice = (
  b: Base,
  duration: number,
  transcript: string | null,
  audioUrl: string,
): MessageOf<'voice'> => ({ ...b, kind: 'voice', duration, transcript, audio_url: audioUrl });

export const slotOffer = (
  b: Base,
  body: string,
  slots: Slot[],
  selected: string | null = null,
): MessageOf<'slot_offer'> => ({
  ...b,
  kind: 'slot_offer',
  text: body,
  slots,
  selected_start: selected,
});

export const bookingCard = (b: Base, appointment: Appointment): MessageOf<'booking_card'> => ({
  ...b,
  kind: 'booking_card',
  appointment,
});

export const system = (
  b: Base,
  body: string,
  tone: MessageOf<'system'>['tone'] = 'info',
): MessageOf<'system'> => ({ ...b, kind: 'system', text: body, tone });

export const agentNote = (b: Base, body: string): MessageOf<'agent_note'> => ({
  ...b,
  kind: 'agent_note',
  text: body,
});

/** Окно для услуги, начинающееся в `start`. */
export function slotFor(service: Service, start: string): Slot {
  return { start, end: plusMinutes(start, service.duration_min), service_id: service.id };
}
