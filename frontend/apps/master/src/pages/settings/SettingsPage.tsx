import type { MasterSettings } from '@beauty/api';
import { PushPrompt } from '@beauty/pwa/PushPrompt';
import { usePushSubscription } from '@beauty/pwa/push';
import {
  Avatar,
  Badge,
  Button,
  ErrorState,
  Icon,
  Sheet,
  Skeleton,
  buttonClass,
  useOnline,
  type IconName,
} from '@beauty/ui';
import { useState } from 'react';
import { Link } from 'react-router';
import { WEEKDAYS, pageUrl } from '../../entities/settings/model';
import { useSettings, useSettingsChange } from '../../entities/settings/queries';
import { plural } from '../../shared/lib/plural';
import { useContainer } from '../../shared/lib/container-context';
import { BottomNav } from '../../widgets/bottom-nav/BottomNav';
import styles from './Settings.module.css';

const count = (n: number, forms: readonly [string, string, string]) => `${n} ${plural(n, forms)}`;

/** «Настройки»: статус страницы, разделы, уведомления. */
export function SettingsPage() {
  const settings = useSettings();
  const online = useOnline();
  return (
    <>
      <main className={styles.page} style={{ minHeight: 0, flex: '1 1 auto' }}>
        <h1 className={styles.hubTitle}>Настройки</h1>
        <div className={styles.body}>
          {settings.data ? (
            <>
              <PageStatus settings={settings.data} />
              <Sections settings={settings.data} />
            </>
          ) : settings.isError ? (
            <ErrorState offline={!online} onRetry={() => void settings.refetch()} />
          ) : (
            <div aria-busy="true" style={{ display: 'grid', gap: 16 }}>
              <Skeleton height={150} radius={18} />
              <Skeleton height={320} radius={18} />
            </div>
          )}
          <Notifications />
        </div>
      </main>
      <BottomNav />
    </>
  );
}

/** Карточка страницы: опубликована ли, что мешает, открыть, скрыть или опубликовать. */
function PageStatus({ settings }: { readonly settings: MasterSettings }) {
  const { page, status, publish_blockers: blockers } = settings;
  const online = useOnline();
  const [confirmHide, setConfirmHide] = useState(false);
  const publish = useSettingsChange(
    (gateway) => gateway.publish(),
    'Страница открыта — клиенты могут записываться',
  );
  const unpublish = useSettingsChange((gateway) => gateway.unpublish(), 'Страница скрыта');
  const published = status === 'published';
  const busy = publish.isPending || unpublish.isPending;

  return (
    <section className={`${styles.card} ${styles.status}`} aria-labelledby="page-status">
      <div className={styles.row}>
        <Avatar name={page.display_name} src={page.avatar_url} size={48} display />
        <div className={styles.grow}>
          <h2 id="page-status" className={styles.strong}>
            {page.display_name}
          </h2>
          <p className={styles.muted}>{page.specialty || 'Специализация не указана'}</p>
        </div>
        <Badge tone={published ? 'ok' : 'warn'}>{published ? 'Опубликована' : 'Черновик'}</Badge>
      </div>
      {published ? (
        <p className={styles.muted}>Клиенты видят страницу и записываются через агента.</p>
      ) : blockers.length > 0 ? (
        <div className={styles.muted} role="status">
          Чтобы открыть страницу:
          <ul className={styles.blockers}>
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className={styles.muted}>Страница скрыта — клиенты её не видят.</p>
      )}
      <div className={styles.actions}>
        {published && (
          <a
            className={buttonClass({ variant: 'outline' })}
            href={pageUrl(page.slug, window.location)}
            target="_blank"
            rel="noreferrer"
          >
            Открыть страницу
          </a>
        )}
        {published ? (
          <Button variant="ghost" disabled={busy || !online} onClick={() => setConfirmHide(true)}>
            Скрыть
          </Button>
        ) : (
          <Button
            disabled={busy || !online || blockers.length > 0}
            onClick={() => publish.mutate(undefined)}
          >
            {publish.isPending ? 'Публикуем…' : 'Опубликовать'}
          </Button>
        )}
      </div>
      <Sheet open={confirmHide} title="Скрыть страницу?" onClose={() => setConfirmHide(false)}>
        <div className={styles.sheetForm}>
          <p className={styles.muted}>
            Клиенты не смогут открыть страницу и записаться. Подтверждённые записи и переписка
            сохранятся; открыть страницу снова можно здесь же.
          </p>
          <Button
            size="lg"
            block
            disabled={busy}
            onClick={() => unpublish.mutate(undefined, { onSettled: () => setConfirmHide(false) })}
          >
            Скрыть страницу
          </Button>
          <Button variant="ghost" block onClick={() => setConfirmHide(false)}>
            Отмена
          </Button>
        </div>
      </Sheet>
    </section>
  );
}

function Sections({ settings }: { readonly settings: MasterSettings }) {
  const { page, working_hours: hours, days_off: daysOff, booking_rules: rules } = settings;
  const days = WEEKDAYS.filter((d) => hours.some((h) => h.weekday === d.day)).map((d) => d.short);
  const items: Array<{ to: string; icon: IconName; label: string; hint: string }> = [
    {
      to: 'profile',
      icon: 'user',
      label: 'Профиль',
      hint: [page.display_name, page.address].filter(Boolean).join(' · '),
    },
    {
      to: 'services',
      icon: 'card',
      label: 'Услуги',
      hint:
        page.services.length === 0
          ? 'Нет услуг'
          : count(page.services.length, ['услуга', 'услуги', 'услуг']),
    },
    {
      to: 'hours',
      icon: 'calendar',
      label: 'График и выходные',
      hint:
        days.length === 0
          ? 'Рабочие часы не заданы'
          : `${days.join(', ')}${daysOff.length ? ` · ${count(daysOff.length, ['выходной', 'выходных', 'выходных'])}` : ''}`,
    },
    {
      to: 'rules',
      icon: 'clock',
      label: 'Правила записи',
      hint: `Подтверждение за ${rules.confirm_within_hours} ч · запись на ${rules.horizon_days} дн.`,
    },
    {
      to: 'photos',
      icon: 'eye',
      label: 'Фото работ',
      hint:
        page.photos.length === 0 ? 'Нет фото' : count(page.photos.length, ['фото', 'фото', 'фото']),
    },
  ];
  return (
    <nav aria-label="Разделы настроек">
      <ul className={styles.menu}>
        {items.map((item) => (
          <li key={item.to}>
            <Link to={item.to} className={styles.menuItem}>
              <span className={styles.menuIcon}>
                <Icon name={item.icon} size={20} strokeWidth={1.8} />
              </span>
              <span className={styles.menuText}>
                <span className={styles.menuLabel}>{item.label}</span>
                <span className={styles.menuHint}>{item.hint}</span>
              </span>
              <Icon name="forward" size={18} strokeWidth={2} className={styles.chevron} />
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Notifications() {
  const { push: gateway, env } = useContainer();
  const push = usePushSubscription({
    app: 'master',
    vapidKey: env.vapidPublicKey,
    register: (input) => gateway.register(input),
  });
  return (
    <section
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      aria-labelledby="notifications"
    >
      <h2 id="notifications" className={styles.sectionTitle}>
        Уведомления
      </h2>
      <PushPrompt
        push={push}
        variant="settings"
        reason="Новые заявки, вопросы, где нужны вы, и итоги поручений — сразу на телефон."
      />
    </section>
  );
}
