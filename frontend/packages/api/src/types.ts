/**
 * Доменные типы API — короткие имена для схем из сгенерированного `schema.d.ts`.
 *
 * Все типы выводятся из контракта `contracts/openapi/beauty.yaml`; руками здесь
 * описываются только производные (сужения объединений).
 */
import type { components, paths } from './schema';

type Schemas = components['schemas'];

export type { components, paths };

export type Problem = Schemas['Problem'];

export type ChallengeStatus = Schemas['ChallengeStatus'];
export type StartChallengeResponse = Schemas['StartChallengeResponse'];
export type ChallengeStatusResponse = Schemas['ChallengeStatusResponse'];
export type SessionResponse = Schemas['SessionResponse'];

export type Money = Schemas['Money'];
export type Service = Schemas['Service'];
export type BookingRules = Schemas['BookingRules'];
export type MasterPage = Schemas['MasterPage'];
export type NameForms = Schemas['NameForms'];
export type Photo = Schemas['Photo'];
export type MasterSettings = Schemas['MasterSettings'];
export type WorkingDay = Schemas['WorkingDay'];
export type TimeInterval = Schemas['TimeInterval'];
export type BookingRulesSettings = Schemas['BookingRulesSettings'];
export type ProfileInput = Schemas['ProfileInput'];
export type ServiceInput = Schemas['ServiceInput'];
export type Slot = Schemas['Slot'];

export type ClientRef = Schemas['ClientRef'];
export type Appointment = Schemas['Appointment'];
export type AppointmentStatus = Appointment['status'];
export type AppointmentRequested = Schemas['AppointmentRequested'];

export type Author = Schemas['Author'];
export type Source = Schemas['Source'];
export type Message = Schemas['Message'];
export type MessageKind = Message['kind'];
/** Сообщение конкретного вида: `MessageOf<'voice'>`. */
export type MessageOf<K extends MessageKind> = Extract<Message, { kind: K }>;
export type MessagePage = Schemas['MessagePage'];
export type ChoiceOption = Schemas['ChoiceOption'];
export type TaskStep = Schemas['TaskStep'];

export type TextInput = Schemas['TextInput'];
export type SlotPickInput = Schemas['SlotPickInput'];
export type BookSlotInput = Schemas['BookSlotInput'];
export type ClientMessageInput = Schemas['ClientMessageInput'];

export type Handler = Schemas['Handler'];
export type ClientConversation = Schemas['ClientConversation'];
export type ConversationFilter = Schemas['ConversationFilter'];
export type ConversationSummary = Schemas['ConversationSummary'];
export type ConversationList = Schemas['ConversationList'];
export type MasterSendResult = Schemas['MasterSendResult'];

export type ScheduleItem = Schemas['ScheduleItem'];
export type DaySchedule = Schemas['DaySchedule'];
export type WeekDay = Schemas['WeekDay'];

export type ChallengeStatusEvent = Schemas['ChallengeStatusEvent'];
export type ConversationEvent = Schemas['ConversationEvent'];
export type MasterEvent = Schemas['MasterEvent'];

export type PushSubscriptionInput = Schemas['PushSubscriptionInput'];
export type PushPayload = Schemas['PushPayload'];

/** Финальные статусы входа: дальше поток статусов не меняется. */
export const FINAL_CHALLENGE_STATUSES: ReadonlySet<ChallengeStatus> = new Set([
  'completed',
  'consumed',
  'rejected',
  'expired',
]);
