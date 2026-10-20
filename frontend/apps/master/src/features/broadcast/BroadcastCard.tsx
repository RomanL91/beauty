import { ApiError, type Broadcast, type MessageOf } from '@beauty/api';
import { Announcement, Bubble, Button, MessageRow, useOnline } from '@beauty/ui';
import { useState } from 'react';
import { broadcastStatusText, recipientsText } from '../../entities/broadcasts/model';
import { useBroadcast, useBroadcastChange } from '../../entities/broadcasts/queries';
import { PhotoPicker } from './PhotoPicker';
import styles from './Broadcast.module.css';

/**
 * Черновик рассылки от агента в ленте поручений: текст и фото, «Отправить» — только здесь,
 * мастером. Состояние берётся с сервера (после отправки — «Отправляется N из M»).
 */
export function BroadcastCard({ message }: { readonly message: MessageOf<'broadcast'> }) {
  const broadcast = useBroadcast(message.broadcast_id);
  if (broadcast.error instanceof ApiError && broadcast.error.status === 404) {
    return (
      <MessageRow side="in">
        <Bubble tone="surface">Черновик рассылки удалён.</Bubble>
      </MessageRow>
    );
  }
  const current = broadcast.data;
  return (
    <MessageRow side="in" wide>
      <Bubble tone="surface" layout="flush">
        <div className={styles.cardWrap} aria-label="Черновик рассылки" role="group">
          <Announcement
            label={current?.status === 'draft' || !current ? 'Черновик рассылки' : 'Рассылка'}
            text={current?.text ?? message.text}
            photoUrl={current?.photo_url ?? null}
          />
          {current && <CardActions broadcast={current} />}
        </div>
      </Bubble>
    </MessageRow>
  );
}

function CardActions({ broadcast }: { readonly broadcast: Broadcast }) {
  const online = useOnline();
  const [confirming, setConfirming] = useState(false);
  const photo = useBroadcastChange(
    (gateway, file: File) => gateway.setPhoto(broadcast.id, file),
    'Фото добавлено',
  );
  const send = useBroadcastChange(
    (gateway, id: string) => gateway.send(id),
    'Рассылка отправляется',
  );
  const discard = useBroadcastChange(async (gateway, id: string) => {
    await gateway.discard(id);
  }, 'Черновик удалён');

  if (broadcast.status !== 'draft') {
    return <p className={styles.cardStatus}>{broadcastStatusText(broadcast)}</p>;
  }
  const busy = photo.isPending || send.isPending || discard.isPending || !online;
  return (
    <div className={styles.cardActions}>
      <p className={styles.cardStatus}>Получат {recipientsText(broadcast.recipients)}</p>
      {confirming ? (
        <div className={styles.confirm} role="group" aria-label="Подтверждение рассылки">
          <span>Отправить всем? Отменить отправку будет нельзя.</span>
          <div className={styles.row}>
            <Button
              disabled={busy}
              onClick={() => send.mutate(broadcast.id, { onSettled: () => setConfirming(false) })}
            >
              Да, отправить
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Отмена
            </Button>
          </div>
        </div>
      ) : (
        <div className={styles.row}>
          <Button disabled={busy || broadcast.recipients === 0} onClick={() => setConfirming(true)}>
            Отправить {recipientsText(broadcast.recipients)}
          </Button>
          <PhotoPicker
            label={broadcast.photo_url ? 'Другое фото' : 'Добавить фото'}
            disabled={busy}
            onPick={(file) => photo.mutate(file)}
          />
          <Button variant="ghost" disabled={busy} onClick={() => discard.mutate(broadcast.id)}>
            Удалить
          </Button>
        </div>
      )}
    </div>
  );
}
