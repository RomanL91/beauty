/** Отписка от потока событий. */
export type Unsubscribe = () => void;

/** Состояние потока событий — для индикатора «нет связи». */
export type StreamState = 'connecting' | 'open' | 'reconnecting' | 'closed';

/** Курсор подгрузки истории вверх. */
export interface HistoryCursor {
  /** `id` самого старого загруженного сообщения. */
  readonly before?: string;
  readonly limit?: number;
}

/** Записанное голосовое, готовое к отправке. */
export interface VoiceDraft {
  readonly clientId: string;
  readonly audio: Blob;
  /** Длительность, секунды. */
  readonly duration: number;
}
