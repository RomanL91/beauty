import type { Appointment, ConversationSummary, MessageOf } from '@beauty/api';
import {
  Avatar,
  buttonClass,
  ChatFeed,
  ErrorState,
  FeedSkeleton,
  Icon,
  IconButton,
  Sheet,
  Skeleton,
  cx,
  iconButtonClass,
  useOnline,
  useToast,
  visuallyHiddenStyle,
} from '@beauty/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useId, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router';
import { MasterMessageView } from '../../entities/conversation/MasterMessageView';
import { inboxKeys, useConversation } from '../../entities/conversation/queries';
import { useAppointmentDecision, useProfile } from '../../entities/schedule/queries';
import { markHandledByMaster, useSetHandler } from '../../features/handler-switch/use-handler';
import { newClientId } from '../../shared/lib/client-id';
import { useContainer } from '../../shared/lib/container-context';
import { DEFAULT_TZ } from '../../shared/lib/dates';
import { localMessage, useLiveFeed } from '../../shared/lib/use-live-feed';
import styles from './DialogPage.module.css';

/** Экран «Диалог и пульт агента» (макет MasterDialog). */
export function DialogPage() {
  const { id = '' } = useParams();
  const conversation = useConversation(id);
  const online = useOnline();
  if (conversation.isError) {
    return (
      <div className={styles.page}>
        <ErrorState
          offline={!online}
          onRetry={() => void conversation.refetch()}
          title="Диалог не открылся"
        />
      </div>
    );
  }
  return <Dialog id={id} conversation={conversation.data} />;
}

function Dialog({
  id,
  conversation,
}: {
  readonly id: string;
  readonly conversation: ConversationSummary | undefined;
}) {
  const { inbox } = useContainer();
  const profile = useProfile();
  const tz = profile.data?.timezone ?? DEFAULT_TZ;
  const masterName = profile.data?.name_forms.nominative ?? 'мастер';
  const online = useOnline();
  const toast = useToast();
  const queryClient = useQueryClient();
  const setHandler = useSetHandler(id);
  const decision = useAppointmentDecision(null);
  const [cardOpen, setCardOpen] = useState(false);

  const load = useCallback(
    (cursor: Parameters<typeof inbox.listMessages>[1]) => inbox.listMessages(id, cursor),
    [inbox, id],
  );
  const source = useMemo(
    () => ({
      channel: id,
      load,
      deliver: async (clientId: string, draft: { kind: string; text?: string }) => {
        const result = await inbox.send(id, {
          kind: 'text',
          client_id: clientId,
          text: draft.text ?? '',
        });
        return result.message;
      },
    }),
    [id, inbox, load],
  );
  const live = useLiveFeed(source);

  const handler = conversation?.handler ?? 'agent';

  const sendText = (text: string) => {
    const clientId = newClientId();
    const before = markHandledByMaster(queryClient, id);
    void live
      .send(clientId, { kind: 'text', text }, localMessage(clientId, { kind: 'text', text }))
      .then((sent) => {
        if (!sent) {
          // Не отправилось — обработчик на сервере не менялся: вернуть как было.
          void queryClient.invalidateQueries({ queryKey: inboxKeys.conversation(id) });
          return;
        }
        if (before === 'agent') {
          toast({
            text: 'Диалог теперь ведёте вы — агент на паузе',
            action: { label: 'Вернуть агенту', onClick: () => setHandler.mutate('agent') },
            duration: 6000,
          });
        }
      });
  };

  const decide = (appointment: Appointment, kind: 'confirm' | 'offer') => {
    const card = live.feed.items.find(
      (i): i is typeof i & { message: MessageOf<'booking_card'> } =>
        i.message.kind === 'booking_card' && i.message.appointment.id === appointment.id,
    )?.message;
    decision.mutate(
      {
        appointment,
        decision:
          kind === 'confirm' ? { kind: 'confirm' } : { kind: 'decline', offerAlternatives: true },
      },
      { onSuccess: (updated) => card && live.applyUpdate({ ...card, appointment: updated }) },
    );
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.top}>
          <Link to="/chats" className={iconButtonClass()} aria-label="К чатам">
            <Icon name="back" strokeWidth={2} />
          </Link>
          {conversation ? (
            <>
              <Avatar
                name={conversation.client.display_name}
                size={40}
                anonymous={conversation.client.visit_number === 1}
              />
              <div className={styles.who}>
                <span className={styles.name}>{conversation.client.display_name}</span>
                <span className={styles.phone}>
                  {conversation.client.phone_masked ?? 'телефон скрыт'} ·{' '}
                  {visitText(conversation.client.visit_number)}
                </span>
              </div>
            </>
          ) : (
            <div className={styles.who}>
              <Skeleton width={140} height={16} />
              <Skeleton width={180} height={12} style={{ marginTop: 6 }} />
            </div>
          )}
          <IconButton
            label="Карточка клиента"
            onClick={() => setCardOpen(true)}
            disabled={!conversation}
          >
            <Icon name="card" strokeWidth={1.8} />
          </IconButton>
        </div>

        <div className={styles.handlerRow}>
          <span className={styles.handlerLabel} id="handler-label">
            Диалог ведёт
          </span>
          <div role="group" aria-labelledby="handler-label" className={styles.segment}>
            {(['agent', 'master'] as const).map((h) => (
              <button
                key={h}
                type="button"
                className={styles.segButton}
                aria-pressed={handler === h}
                disabled={!conversation}
                onClick={() => handler !== h && setHandler.mutate(h)}
              >
                {h === 'agent' ? 'Агент' : 'Я'}
              </button>
            ))}
          </div>
        </div>
        <div
          className={cx(styles.state, handler === 'agent' ? styles.stateAgent : styles.stateMe)}
          role="status"
        >
          <span className={styles.stateDot} aria-hidden="true" />
          {handler === 'agent'
            ? 'Агент отвечает сам. Если напишете вы — он встанет на паузу.'
            : 'Агент на паузе и молчит, пока вы не вернёте ему диалог.'}
        </div>
      </header>

      <div className={styles.body}>
        {live.initial.status === 'error' ? (
          <ErrorState offline={!online} onRetry={live.retryInitial} />
        ) : live.initial.status === 'loading' ? (
          <FeedSkeleton />
        ) : (
          <ChatFeed
            label="Переписка с клиентом"
            feed={live.feed}
            timeZone={tz}
            older={live.older}
            onLoadOlder={() => void live.loadOlder()}
            renderItem={(index) => {
              const item = live.feed.items[index];
              return item ? (
                <MasterMessageView
                  item={item}
                  timeZone={tz}
                  actions={{
                    onRetry: live.retry,
                    onConfirm: (a) => decide(a, 'confirm'),
                    onOfferOther: (a) => decide(a, 'offer'),
                    busyAppointmentId: decision.isPending
                      ? (decision.variables?.appointment.id ?? null)
                      : null,
                  }}
                />
              ) : null;
            }}
          />
        )}
      </div>

      <ReplyBox masterName={masterName} onSend={sendText} />

      <Sheet open={cardOpen} title="Карточка клиента" onClose={() => setCardOpen(false)}>
        {conversation && (
          <div className={styles.cardList}>
            <span>
              <strong>{conversation.client.display_name}</strong>
            </span>
            <span>{conversation.client.phone_masked ?? 'Телефон скрыт'}</span>
            <span>{visitText(conversation.client.visit_number)}</span>
            <Link
              to={`/clients/${conversation.client.id}`}
              className={buttonClass({ variant: 'outline', block: true })}
            >
              Карточка: заметки и история визитов
            </Link>
          </div>
        )}
      </Sheet>
    </div>
  );
}

function visitText(n: number): string {
  return n === 1 ? 'первый визит' : `${n}-й визит`;
}

function ReplyBox({
  masterName,
  onSend,
}: {
  readonly masterName: string;
  readonly onSend: (text: string) => void;
}) {
  const [text, setText] = useState('');
  const id = useId();
  const submit = () => {
    const value = text.trim();
    if (!value) return;
    onSend(value);
    setText('');
  };
  return (
    <footer className={styles.footer}>
      <div className={styles.inputRow}>
        <label htmlFor={id} style={visuallyHiddenStyle}>
          Ответ от вашего имени
        </label>
        <textarea
          id={id}
          rows={1}
          className={styles.field}
          placeholder="Ответить от своего имени"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <IconButton label="Отправить" look="accent" onClick={submit} disabled={!text.trim()}>
          <Icon name="send" size={20} strokeWidth={2} />
        </IconButton>
      </div>
      <span className={styles.hint}>
        Клиент увидит сообщение с подписью «{masterName}», без пометки ИИ.
      </span>
    </footer>
  );
}
