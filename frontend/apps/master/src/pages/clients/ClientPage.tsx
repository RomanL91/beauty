import type { ClientNote, ClientVisit, MasterClientCard } from '@beauty/api';
import {
  Avatar,
  Badge,
  Button,
  ErrorState,
  Icon,
  IconButton,
  Sheet,
  Skeleton,
  TextArea,
  TextField,
  buttonClass,
  formatDayShort,
  formatMoney,
  formatTime,
  iconButtonClass,
  useOnline,
} from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router';
import {
  MAX_NAME,
  MAX_NOTE,
  visitStatusText,
  visitTone,
  visitsText,
} from '../../entities/clients/model';
import { useClientCard, useClientChange } from '../../entities/clients/queries';
import { useProfile } from '../../entities/schedule/queries';
import { DEFAULT_TZ } from '../../shared/lib/dates';
import styles from './Clients.module.css';

/** Карточка клиента: имя, визиты, заметки мастера и ИИ-администратора. */
export function ClientPage() {
  const { id = '' } = useParams();
  const card = useClientCard(id);
  const tz = useProfile().data?.timezone ?? DEFAULT_TZ;
  const online = useOnline();
  return (
    <div className={styles.page}>
      <header className={styles.cardHeader}>
        <Link to="/clients" className={iconButtonClass()} aria-label="К клиентам">
          <Icon name="back" strokeWidth={2} />
        </Link>
        <h1 className={styles.cardTitle}>{card.data?.display_name ?? 'Клиент'}</h1>
      </header>
      {card.data ? (
        <ClientCard card={card.data} timeZone={tz} />
      ) : card.isError ? (
        <ErrorState offline={!online} onRetry={() => void card.refetch()} />
      ) : (
        <div className={styles.sections} aria-busy="true">
          <Skeleton height={140} />
          <Skeleton height={120} />
          <Skeleton height={160} />
        </div>
      )}
    </div>
  );
}

function ClientCard({
  card,
  timeZone,
}: {
  readonly card: MasterClientCard;
  readonly timeZone: string;
}) {
  const [renaming, setRenaming] = useState(false);
  const online = useOnline();
  return (
    <div className={styles.sections}>
      <section className={styles.section} aria-label="Клиент">
        <div className={styles.profile}>
          <Avatar name={card.display_name} size={56} anonymous={!card.named} />
          <div className={styles.body}>
            <span className={styles.bigName}>{card.display_name}</span>
            <span className={styles.meta}>{card.phone_masked}</span>
            <span className={styles.meta}>
              С нами с {formatDayShort(card.since, timeZone).split(', ')[1]}
            </span>
          </div>
        </div>
        <dl className={styles.stats}>
          <div>
            <dt>Визиты</dt>
            <dd>{card.visits}</dd>
          </div>
          <div>
            <dt>Отмены</dt>
            <dd>{card.cancelled}</dd>
          </div>
          <div>
            <dt>Заметки</dt>
            <dd>{card.note_items.length}</dd>
          </div>
        </dl>
        <div className={styles.actions}>
          <Link
            to={`/chats/${card.conversation_id}`}
            className={buttonClass({ variant: 'primary' })}
          >
            <Icon name="chat" size={18} /> Написать
          </Link>
          <Button variant="outline" disabled={!online} onClick={() => setRenaming(true)}>
            {card.named ? 'Изменить имя' : 'Дать имя'}
          </Button>
        </div>
        {!card.named && (
          <p className={styles.hint}>
            Подпишите клиента — имя будет в чатах и графике, а ИИ-администратор станет обращаться по
            нему.
          </p>
        )}
      </section>

      <Notes card={card} timeZone={timeZone} />

      <section className={styles.section} aria-labelledby="upcoming">
        <h2 id="upcoming" className={styles.sectionTitle}>
          Впереди
        </h2>
        {card.upcoming.length === 0 ? (
          <p className={styles.hint}>Заявок и записей нет.</p>
        ) : (
          <VisitList visits={card.upcoming} timeZone={timeZone} label="Записи впереди" />
        )}
      </section>

      <section className={styles.section} aria-labelledby="history">
        <h2 id="history" className={styles.sectionTitle}>
          История · {visitsText(card.visits)}
        </h2>
        {card.history.length === 0 ? (
          <p className={styles.hint}>Здесь будут прошедшие визиты и отмены.</p>
        ) : (
          <VisitList visits={card.history} timeZone={timeZone} label="История визитов" />
        )}
      </section>

      <Sheet open={renaming} title="Имя клиента" onClose={() => setRenaming(false)}>
        {renaming && <RenameForm card={card} onDone={() => setRenaming(false)} />}
      </Sheet>
    </div>
  );
}

function VisitList({
  visits,
  timeZone,
  label,
}: {
  readonly visits: ClientVisit[];
  readonly timeZone: string;
  readonly label: string;
}) {
  return (
    <ul className={styles.visits} aria-label={label}>
      {visits.map((v) => (
        <li key={v.id} className={styles.visit}>
          <div className={styles.body}>
            <span className={styles.visitWhen}>
              {formatDayShort(v.start, timeZone)}, {formatTime(v.start, timeZone)}
            </span>
            <span className={styles.meta}>
              {v.service_title} · {formatMoney(v.price)}
            </span>
          </div>
          <Badge tone={visitTone(v)}>{visitStatusText(v)}</Badge>
        </li>
      ))}
    </ul>
  );
}

function Notes({ card, timeZone }: { readonly card: MasterClientCard; readonly timeZone: string }) {
  const [text, setText] = useState('');
  const online = useOnline();
  const add = useClientChange(card.id, (gateway, note: string) => gateway.addNote(card.id, note));
  const remove = useClientChange(
    card.id,
    (gateway, noteId: string) => gateway.removeNote(card.id, noteId),
    'Заметка удалена',
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    add.mutate(value, { onSuccess: () => setText('') });
  };
  return (
    <section className={styles.section} aria-labelledby="notes">
      <h2 id="notes" className={styles.sectionTitle}>
        Заметки
      </h2>
      <p className={styles.hint}>
        Видны только вам и ИИ-администратору: он учитывает их в разговоре и сам записывает то, что
        клиент рассказал о себе.
      </p>
      {card.note_items.length > 0 && (
        <ul className={styles.notes} aria-label="Заметки о клиенте">
          {card.note_items.map((note) => (
            <NoteItem
              key={note.id}
              note={note}
              timeZone={timeZone}
              busy={remove.isPending && remove.variables === note.id}
              onRemove={() => remove.mutate(note.id)}
            />
          ))}
        </ul>
      )}
      <form className={styles.noteForm} onSubmit={submit}>
        <TextArea
          label="Новая заметка"
          value={text}
          maxLength={MAX_NOTE}
          rows={2}
          placeholder="Например: аллергия на лаванду"
          onChange={(e) => setText(e.target.value)}
        />
        <Button
          type="submit"
          variant="secondary"
          disabled={!text.trim() || add.isPending || !online}
        >
          {add.isPending ? 'Сохраняем…' : 'Добавить заметку'}
        </Button>
      </form>
    </section>
  );
}

function NoteItem({
  note,
  timeZone,
  busy,
  onRemove,
}: {
  readonly note: ClientNote;
  readonly timeZone: string;
  readonly busy: boolean;
  readonly onRemove: () => void;
}) {
  const online = useOnline();
  const byAgent = note.author === 'agent';
  return (
    <li className={styles.note}>
      <div className={styles.body}>
        <span className={styles.noteText}>{note.text}</span>
        <span className={styles.noteMeta}>
          {byAgent ? (
            <>
              <Icon name="sparkle" size={14} /> ИИ-администратор
            </>
          ) : (
            'Вы'
          )}{' '}
          · {formatDayShort(note.created_at, timeZone)}
        </span>
      </div>
      <IconButton
        label={`Удалить заметку «${note.text}»`}
        disabled={busy || !online}
        onClick={onRemove}
      >
        <Icon name="trash" size={18} />
      </IconButton>
    </li>
  );
}

function RenameForm({
  card,
  onDone,
}: {
  readonly card: MasterClientCard;
  readonly onDone: () => void;
}) {
  const [name, setName] = useState(card.named ? card.display_name : '');
  const online = useOnline();
  const rename = useClientChange(
    card.id,
    (gateway, value: string | null) => gateway.rename(card.id, value),
    'Имя сохранено',
    { renames: true },
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    rename.mutate(name.trim() || null, { onSuccess: onDone });
  };
  return (
    <form className={styles.sheetForm} onSubmit={submit}>
      <TextField
        label="Как зовут клиента"
        value={name}
        maxLength={MAX_NAME}
        placeholder="Например: Айгерим"
        hint="Пустое имя — снова подпись по телефону."
        onChange={(e) => setName(e.target.value)}
      />
      <Button type="submit" size="lg" block disabled={rename.isPending || !online}>
        {rename.isPending ? 'Сохраняем…' : 'Сохранить'}
      </Button>
    </form>
  );
}
