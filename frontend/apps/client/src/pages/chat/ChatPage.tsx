import type { Appointment, MasterPage, Message } from '@beauty/api';
import {
  Avatar,
  ChatFeed,
  ErrorState,
  FeedSkeleton,
  Icon,
  IconButton,
  Skeleton,
  StateView,
  formatDayShort,
  formatTime,
  iconButtonClass,
  useOnline,
} from '@beauty/ui';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { ClientMessageView } from '../../entities/message/ClientMessageView';
import { useMasterPage } from '../../entities/master/queries';
import {
  CancelSheet,
  MyBookingsSheet,
  RescheduleSheet,
} from '../../features/booking-actions/BookingSheets';
import { useClientConversation } from '../../features/send-message/use-client-conversation';
import { readIntent } from '../../shared/lib/booking-intent';
import { PushPrompt } from '@beauty/pwa/PushPrompt';
import { usePushSubscription } from '@beauty/pwa/push';
import { clearApiCache } from '@beauty/pwa/register';
import { useContainer } from '../../shared/lib/container-context';
import { Composer } from '../../widgets/composer/Composer';
import styles from './ChatPage.module.css';

/** Экран «Чат с администратором» (макет ClientChat). */
export function ChatPage() {
  const master = useMasterPage();
  const online = useOnline();
  if (master.isPending) return <ChatSkeleton />;
  if (master.isError) return <ErrorState offline={!online} onRetry={() => void master.refetch()} />;
  return <Chat master={master.data} />;
}

function Chat({ master }: { readonly master: MasterPage }) {
  const chat = useClientConversation();
  const online = useOnline();
  const { push: pushGateway, env, masterSlug, auth } = useContainer();
  const push = usePushSubscription({
    app: 'client',
    ...(masterSlug && { masterSlug }),
    vapidKey: env.vapidPublicKey,
    register: (input) => pushGateway.register(input),
  });
  const navigate = useNavigate();
  const [cancelTarget, setCancelTarget] = useState<Appointment | null>(null);
  const [rescheduleTarget, setRescheduleTarget] = useState<Appointment | null>(null);
  const [bookingsOpen, setBookingsOpen] = useState(false);
  useBookingIntent(chat, master);

  const tz = master.timezone;
  const appointments = useMemo(
    () => activeAppointments(chat.feed.items.map((i) => i.message)),
    [chat.feed.items],
  );
  const updateCard = (updated: Appointment) => {
    for (const item of chat.feed.items) {
      if (item.message.kind === 'booking_card' && item.message.appointment.id === updated.id) {
        chat.applyUpdate({ ...item.message, appointment: updated });
      }
    }
  };

  const loadFailed = chat.conversation.isError
    ? chat.conversation.error
    : chat.initial.status === 'error'
      ? chat.initial.error
      : null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to="/" className={iconButtonClass()} aria-label="На страницу мастера">
          <Icon name="back" strokeWidth={2} />
        </Link>
        <Avatar
          name={master.display_name}
          src={master.avatar_url}
          size={40}
          display
          initials={master.display_name[0]}
        />
        <div className={styles.title}>
          <span className={styles.name}>{master.display_name}</span>
          <span className={styles.role}>Администратор · ИИ-ассистент</span>
        </div>
        <IconButton label="Мои записи" onClick={() => setBookingsOpen(true)}>
          <Icon name="calendar" strokeWidth={1.8} />
        </IconButton>
      </header>
      {online && chat.stream === 'reconnecting' && (
        <div className={styles.reconnecting} role="status">
          Переподключаемся — новые сообщения появятся автоматически
        </div>
      )}

      <div className={styles.body}>
        {loadFailed ? (
          <ErrorState
            offline={!online}
            onRetry={() =>
              chat.conversation.isError ? void chat.conversation.refetch() : void chat.loadInitial()
            }
          />
        ) : chat.initial.status === 'loading' || !chat.conversationId ? (
          <FeedSkeleton />
        ) : (
          <ChatFeed
            label={`Переписка с администратором ${master.name_forms.genitive}`}
            feed={chat.feed}
            timeZone={tz}
            older={chat.older}
            onLoadOlder={() => void chat.loadOlder()}
            empty={
              <StateView
                icon="chat"
                title="Напишите администратору"
                text={`Ответит сразу: запишет к ${master.name_forms.dative}, подскажет по услугам, перенесёт визит.`}
              />
            }
            renderItem={(index) => {
              const item = chat.feed.items[index];
              return item ? (
                <ClientMessageView
                  item={item}
                  master={master}
                  picked={chat.picked}
                  actions={{
                    onPickSlot: (offerId, start) =>
                      chat.pickSlot(offerId, start, formatTime(start, tz)),
                    onRetry: chat.retry,
                    onReschedule: setRescheduleTarget,
                    onCancel: setCancelTarget,
                  }}
                />
              ) : null;
            }}
          />
        )}
      </div>

      {appointments.length > 0 && (
        <div style={{ padding: '0 12px 8px' }}>
          <PushPrompt
            push={push}
            reason={`Сообщим, когда ${master.name_forms.nominative} подтвердит запись, и напомним о визите.`}
          />
        </div>
      )}
      <Composer onSendText={chat.sendText} onSendVoice={chat.sendVoice} />

      <CancelSheet
        appointment={cancelTarget}
        master={master}
        onClose={() => setCancelTarget(null)}
        onDone={updateCard}
      />
      <RescheduleSheet
        appointment={rescheduleTarget}
        master={master}
        onClose={() => setRescheduleTarget(null)}
        onDone={updateCard}
      />
      <MyBookingsSheet
        open={bookingsOpen}
        appointments={appointments}
        master={master}
        onClose={() => setBookingsOpen(false)}
        push={push}
        onLogout={() => {
          setBookingsOpen(false);
          void auth.logout().finally(() => {
            clearApiCache();
            void navigate('/', { replace: true });
          });
        }}
        onShow={(a) => {
          setBookingsOpen(false);
          document
            .getElementById(`appointment-${a.id}`)
            ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }}
      />
    </div>
  );
}

/**
 * Продолжить запись, начатую на странице мастера до входа: один раз
 * отправить запрос и убрать намерение из адреса (перезагрузка не повторит).
 */
function useBookingIntent(chat: ReturnType<typeof useClientConversation>, master: MasterPage) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const done = useRef(false);
  const ready = chat.initial.status === 'ready';

  useEffect(() => {
    if (!ready || done.current) return;
    const intent = readIntent(params);
    if (!intent) return;
    done.current = true;
    const service = master.services.find((s) => s.id === intent.serviceId);
    if (intent.start && service) {
      const label = `Хочу записаться: ${service.title.toLowerCase()}, ${formatDayShort(intent.start, master.timezone).toLowerCase()} в ${formatTime(intent.start, master.timezone)}`;
      chat.bookSlot(service.id, intent.start, label);
    } else if (service) {
      chat.sendText(`Хочу записаться: ${service.title.toLowerCase()}. Какое время свободно?`);
    } else {
      chat.sendText('Хочу записаться. Какое время свободно?');
    }
    void navigate('/chat', { replace: true });
  }, [ready, params, master, chat, navigate]);
}

/** Активные записи: последнее состояние каждой из карточек ленты. */
function activeAppointments(messages: readonly Message[]): Appointment[] {
  const byId = new Map<string, Appointment>();
  for (const m of messages)
    if (m.kind === 'booking_card') byId.set(m.appointment.id, m.appointment);
  return [...byId.values()]
    .filter(
      (a) =>
        (a.status === 'requested' || a.status === 'confirmed') && Date.parse(a.end) > Date.now(),
    )
    .sort((x, y) => Date.parse(x.start) - Date.parse(y.start));
}

/** Скелетон экрана чата (пока восстанавливается сессия или грузится мастер). */
export function ChatSkeleton() {
  return (
    <div className={styles.page} aria-busy="true">
      <header className={styles.header}>
        <Skeleton width={44} height={44} radius="50%" />
        <Skeleton width={40} height={40} radius="50%" />
        <div className={styles.title}>
          <Skeleton width={150} height={16} />
          <Skeleton width={190} height={12} style={{ marginTop: 6 }} />
        </div>
      </header>
      <div className={styles.body}>
        <FeedSkeleton />
      </div>
    </div>
  );
}
