/**
 * @beauty/api — типы контракта, HTTP-ядро, порты и адаптеры.
 *
 * Компоненты приложений зависят только от портов (`ports/*`); конкретные
 * адаптеры собирает `AppContainer` каждого приложения.
 */
export * from './types';
export { ApiError } from './http/api-error';
export {
  HttpCore,
  API_BASE_PATH,
  call,
  unwrap,
  type BeautyClient,
  type HttpCoreOptions,
} from './http/client';
export { createAuthorizedFetch, globalFetch, type RequestFetch } from './http/authorized-fetch';
export {
  SessionStore,
  type SessionRefresher,
  type SessionState,
  type SignOutReason,
} from './http/session-store';
export { SseParser, type SseFrame } from './sse/sse-parser';
export { SseConnection, type SseConnectionState, type SseOptions } from './sse/sse-connection';
export type * from './ports';
export { HttpAuthGateway } from './adapters/http-auth-gateway';
export { StubMasterAuthGateway, STUB_MASTER_ACCOUNT_ID } from './adapters/stub-master-auth-gateway';
export { HttpMasterGateway } from './adapters/http-master-gateway';
export { HttpConversationGateway } from './adapters/http-conversation-gateway';
export { HttpScheduleGateway } from './adapters/http-schedule-gateway';
export { HttpInboxGateway } from './adapters/http-inbox-gateway';
export { HttpAssistantGateway } from './adapters/http-assistant-gateway';
export { HttpMasterEventsGateway } from './adapters/http-master-events-gateway';
export { HttpPushGateway } from './adapters/http-push-gateway';
export { HttpMasterSettingsGateway } from './adapters/http-master-settings-gateway';
export { HttpAdminGateway } from './adapters/http-admin-gateway';
export { HttpClientsGateway } from './adapters/http-clients-gateway';
export { HttpBroadcastsGateway } from './adapters/http-broadcasts-gateway';
export {
  EMPTY_FEED,
  feedReducer,
  oldestMessageId,
  type Delivery,
  type FeedAction,
  type FeedItem,
  type FeedState,
  type OutgoingDraft,
} from './model/message-feed';
export {
  formatRemainingClock,
  formatRemainingLong,
  remaining,
  type Remaining,
} from './model/countdown';
