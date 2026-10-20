import type { Broadcast, BroadcastsGateway } from '@beauty/api';
import {
  Announcement,
  Badge,
  Button,
  ErrorState,
  Icon,
  Notice,
  Sheet,
  Skeleton,
  TextArea,
  formatDayShort,
  formatSlotShort,
  formatTime,
  iconButtonClass,
  useOnline,
} from '@beauty/ui';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import {
  MAX_BROADCAST,
  broadcastStatusText,
  recipientsText,
} from '../../entities/broadcasts/model';
import { useBroadcastChange, useBroadcasts } from '../../entities/broadcasts/queries';
import { useClients } from '../../entities/clients/queries';
import { useProfile } from '../../entities/schedule/queries';
import { PhotoPicker } from '../../features/broadcast/PhotoPicker';
import { DEFAULT_TZ } from '../../shared/lib/dates';
import styles from './Clients.module.css';

/** «Рассылка»: объявление всем клиентам (текст и фото) и история рассылок. */
export function BroadcastPage() {
  const list = useBroadcasts();
  const tz = useProfile().data?.timezone ?? DEFAULT_TZ;
  const online = useOnline();
  const draft = list.data?.items.find((b) => b.status === 'draft') ?? null;
  const history = list.data?.items.filter((b) => b.status !== 'draft') ?? [];
  return (
    <div className={styles.page}>
      <header className={styles.cardHeader}>
        <Link to="/clients" className={iconButtonClass()} aria-label="К клиентам">
          <Icon name="back" strokeWidth={2} />
        </Link>
        <h1 className={styles.cardTitle}>Рассылка</h1>
      </header>
      {list.data ? (
        <div className={styles.sections}>
          {!list.data.allowed && (
            <Notice tone="warn" role="status">
              Рассылки для вашей страницы отключены администрацией сервиса.
            </Notice>
          )}
          {list.data.allowed && list.data.next_at && (
            <Notice role="status">
              Не чаще одной рассылки в сутки — следующую можно отправить{' '}
              {formatSlotShort(list.data.next_at, tz).toLowerCase()}.
            </Notice>
          )}
          <Composer
            key={draft?.id ?? 'new'}
            draft={draft}
            canSend={list.data.allowed && !list.data.next_at}
          />
          <section className={styles.section} aria-labelledby="history">
            <h2 id="history" className={styles.sectionTitle}>
              Отправленные
            </h2>
            {history.length === 0 ? (
              <p className={styles.hint}>Здесь будут ваши рассылки.</p>
            ) : (
              <ul className={styles.visits} aria-label="Отправленные рассылки">
                {history.map((b) => (
                  <li key={b.id} className={styles.visit}>
                    <div className={styles.body}>
                      <span className={styles.visitWhen}>
                        {formatDayShort(b.started_at ?? b.created_at, tz)},{' '}
                        {formatTime(b.started_at ?? b.created_at, tz)}
                        {b.photo_url ? ' · с фото' : ''}
                      </span>
                      <span className={styles.noteText}>{b.text}</span>
                    </div>
                    <Badge tone={b.status === 'sent' ? 'ok' : 'accent'}>
                      {broadcastStatusText(b)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : list.isError ? (
        <ErrorState offline={!online} onRetry={() => void list.refetch()} />
      ) : (
        <div className={styles.sections} aria-busy="true">
          <Skeleton height={220} />
          <Skeleton height={120} />
        </div>
      )}
    </div>
  );
}

/** Черновик сохраняется на сервере: текст, фото; «Отправить» — после подтверждения. */
function Composer({
  draft,
  canSend,
}: {
  readonly draft: Broadcast | null;
  readonly canSend: boolean;
}) {
  const [text, setText] = useState(draft?.text ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [confirming, setConfirming] = useState(false);
  const online = useOnline();
  const clients = useClients('', 'all', 1);
  const recipients = draft?.recipients ?? clients.data?.total ?? 0;
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);
  const photoUrl = preview ?? draft?.photo_url ?? null;

  /** Сохранить черновик (создать или поправить) и фото, если выбрано новое. */
  const persist = async (gateway: BroadcastsGateway): Promise<Broadcast> => {
    let current = draft ? draft : await gateway.draft(text.trim());
    if (draft && draft.text !== text.trim()) current = await gateway.edit(draft.id, text.trim());
    if (file) current = await gateway.setPhoto(current.id, file);
    return current;
  };
  const save = useBroadcastChange(async (gateway, _: void) => {
    const saved = await persist(gateway);
    setFile(null);
    return saved;
  }, 'Черновик сохранён');
  const send = useBroadcastChange(async (gateway, _: void) => {
    const saved = await persist(gateway);
    return gateway.send(saved.id);
  }, 'Рассылка отправляется');
  const removePhoto = useBroadcastChange(
    (gateway, id: string) => gateway.removePhoto(id),
    'Фото убрано',
  );
  const discard = useBroadcastChange(async (gateway, id: string) => {
    await gateway.discard(id);
  }, 'Черновик удалён');

  const busy = save.isPending || send.isPending || removePhoto.isPending || discard.isPending;
  const empty = !text.trim();
  return (
    <section className={styles.section} aria-labelledby="compose">
      <h2 id="compose" className={styles.sectionTitle}>
        Объявление всем клиентам
      </h2>
      <p className={styles.hint}>
        Придёт в чат каждому клиенту и push-уведомлением. ИИ-администратор будет знать о нём и
        ответит на вопросы. Можно поручить и агенту: «Разошли всем: …».
      </p>
      <TextArea
        label="Текст объявления"
        value={text}
        maxLength={MAX_BROADCAST}
        rows={5}
        placeholder="Например: с 1 ноября — массаж лица, первую неделю −20%"
        hint={`${text.length} / ${MAX_BROADCAST}`}
        onChange={(e) => setText(e.target.value)}
      />
      {photoUrl && (
        <div className={styles.photoPreview}>
          <img src={photoUrl} alt="Фото объявления" />
          <Button
            variant="ghost"
            disabled={busy || !online}
            onClick={() => (file ? setFile(null) : draft && removePhoto.mutate(draft.id))}
          >
            Убрать фото
          </Button>
        </div>
      )}
      <div className={styles.actions}>
        <PhotoPicker
          label={photoUrl ? 'Другое фото' : 'Добавить фото'}
          disabled={busy || !online}
          onPick={setFile}
        />
        <Button variant="outline" disabled={busy || empty || !online} onClick={() => save.mutate()}>
          Сохранить черновик
        </Button>
      </div>
      <Button
        size="lg"
        block
        disabled={busy || empty || !online || !canSend || recipients === 0}
        onClick={() => setConfirming(true)}
      >
        Отправить {recipientsText(recipients)}
      </Button>
      {draft && (
        <Button
          variant="ghost"
          block
          disabled={busy || !online}
          onClick={() => discard.mutate(draft.id)}
        >
          Удалить черновик
        </Button>
      )}
      <Sheet open={confirming} title="Отправить рассылку?" onClose={() => setConfirming(false)}>
        <div className={styles.sheetForm}>
          <div className={styles.confirmPreview}>
            <Announcement label="Объявление" text={text.trim()} photoUrl={photoUrl} />
          </div>
          <p className={styles.hint}>
            Получат {recipientsText(recipients)}. Отменить отправку будет нельзя; следующая рассылка
            — не раньше чем через сутки.
          </p>
          <Button
            size="lg"
            block
            disabled={busy}
            onClick={() =>
              send.mutate(undefined, {
                onSuccess: () => {
                  setConfirming(false);
                  setText('');
                  setFile(null);
                },
              })
            }
          >
            {send.isPending ? 'Отправляем…' : 'Да, отправить'}
          </Button>
        </div>
      </Sheet>
    </section>
  );
}
