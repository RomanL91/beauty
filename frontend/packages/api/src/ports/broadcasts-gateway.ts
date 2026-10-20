import type { Broadcast, BroadcastList } from '../types';

/** Порт рассылок мастера: черновик, фото, отправка всем клиентам. */
export interface BroadcastsGateway {
  list(): Promise<BroadcastList>;
  get(broadcastId: string): Promise<Broadcast>;
  draft(text: string): Promise<Broadcast>;
  edit(broadcastId: string, text: string): Promise<Broadcast>;
  /** Только черновик. */
  discard(broadcastId: string): Promise<void>;
  setPhoto(broadcastId: string, file: Blob): Promise<Broadcast>;
  removePhoto(broadcastId: string): Promise<Broadcast>;
  /** Доставка — в фоне: статус `sending`, затем `sent`. */
  send(broadcastId: string): Promise<Broadcast>;
}
