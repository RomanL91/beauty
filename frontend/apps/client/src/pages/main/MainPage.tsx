import type { MasterPage as Master } from '@beauty/api';
import {
  Avatar,
  ErrorState,
  Icon,
  Notice,
  Skeleton,
  StateView,
  buttonClass,
  formatMoney,
  formatSlotShort,
  useOnline,
} from '@beauty/ui';
import { useState } from 'react';
import { Link } from 'react-router';
import { useMasterPage, useSlots } from '../../entities/master/queries';
import { useSession } from '../../entities/session/use-session';
import { chatHref, loginHref, type BookingIntent } from '../../shared/lib/booking-intent';
import { useMasterSlug } from '../../shared/lib/container-context';
import { hoursGenitive, plural } from '../../shared/lib/plural';
import styles from './MainPage.module.css';

/** Экран «Страница мастера» (макет Main). */
export function MainPage() {
  const page = useMasterPage();
  const online = useOnline();

  if (page.isPending) return <MainSkeleton />;
  if (page.isError) {
    const notFound = 'status' in page.error && page.error.status === 404;
    return notFound ? (
      <StateView
        icon="user"
        title="Мастер не найден"
        text="Возможно, страница переехала. Проверьте адрес."
      />
    ) : (
      <ErrorState offline={!online} onRetry={() => void page.refetch()} />
    );
  }
  return <MasterView master={page.data} />;
}

function MasterView({ master }: { readonly master: Master }) {
  const slug = useMasterSlug();
  const session = useSession();
  const authed = session.status === 'authenticated';
  /** Куда ведёт действие: сразу в чат или через вход с возвратом. */
  const to = (intent?: BookingIntent) => (authed ? chatHref(intent) : loginHref(chatHref(intent)));
  const { confirm_within_hours: confirmHours, change_deadline_hours: changeHours } =
    master.booking_rules;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.host}>{slug}.beautiful.kz</span>
        {authed ? (
          <Link to="/chat" className={styles.signIn}>
            <Icon name="chat" size={18} strokeWidth={1.8} />
            Чат
          </Link>
        ) : (
          <Link to={loginHref('/')} className={styles.signIn}>
            <Icon name="telegram" size={18} strokeWidth={1.8} />
            Войти
          </Link>
        )}
      </header>

      <section className={styles.hero} aria-labelledby="master-name">
        <div className={styles.profile}>
          <Avatar
            name={master.display_name}
            src={master.avatar_url}
            size={84}
            display
            initials={master.display_name[0]}
          />
          <div className={styles.who}>
            <h1 id="master-name" className={styles.name}>
              {master.display_name}
            </h1>
            <div className={styles.specialty}>{master.specialty}</div>
            <div className={styles.address}>{master.address}</div>
          </div>
        </div>
        <div className={styles.actions}>
          <Link to={to({})} className={buttonClass({ size: 'lg' })}>
            Записаться
          </Link>
          <Link to={to()} className={buttonClass({ variant: 'secondary', size: 'lg' })}>
            <Icon name="chat" size={20} strokeWidth={1.8} />
            Написать
          </Link>
        </div>
        <Notice icon="sparkle">
          Отвечает администратор {master.name_forms.genitive} — ИИ-ассистент. Пишите в любое время:
          запишет, перенесёт, напомнит. {master.name_forms.nominative} видит переписку и может
          подключиться сама.
        </Notice>
      </section>

      <NearestSlots master={master} link={to} />

      <section className={styles.section} aria-labelledby="services">
        <h2 id="services" className={styles.h2}>
          Услуги
        </h2>
        <div className={styles.card}>
          {master.services.map((s) => (
            <div key={s.id} className={styles.service}>
              <div className={styles.serviceText}>
                <div className={styles.serviceTitle}>{s.title}</div>
                <div className={styles.serviceMeta}>
                  {s.duration_min} мин · {formatMoney(s.price)}
                </div>
                {s.description && <ServiceDescription text={s.description} />}
              </div>
              <Link
                to={to({ serviceId: s.id })}
                className={buttonClass({ variant: 'soft' })}
                aria-label={`Выбрать: ${s.title}`}
              >
                Выбрать
              </Link>
            </div>
          ))}
        </div>
      </section>

      {master.photos.length > 0 && (
        <section className={styles.section} aria-labelledby="works">
          <h2 id="works" className={styles.h2}>
            Работы
          </h2>
          <div className={styles.gallery}>
            {master.photos.map((p) => (
              <img
                key={p.id}
                src={p.url}
                alt={p.alt ?? ''}
                className={styles.photo}
                loading="lazy"
              />
            ))}
          </div>
        </section>
      )}

      {master.about && (
        <section className={styles.section} aria-labelledby="about">
          <h2 id="about" className={styles.h2}>
            О мастере
          </h2>
          <p className={styles.about}>{master.about}</p>
        </section>
      )}

      <section className={styles.section} aria-labelledby="rules">
        <h2 id="rules" className={styles.h2}>
          Правила записи
        </h2>
        <div className={styles.rules}>
          <div className={styles.rule}>
            <Icon name="clock" size={18} strokeWidth={1.8} />
            <span>
              Заявку подтверждает {master.name_forms.nominative} — обычно в течение{' '}
              {hoursGenitive(confirmHours)}. Время держится за вами.
            </span>
          </div>
          <div className={styles.rule}>
            <Icon name="reschedule" size={18} strokeWidth={1.8} />
            <span>
              Перенос или отмена — не позднее чем за {changeHours}{' '}
              {plural(changeHours, ['час', 'часа', 'часов'])} до визита.
            </span>
          </div>
          <div className={styles.rule}>
            <Icon name="bell" size={18} strokeWidth={1.8} />
            <span>Напомним о визите уведомлением, а если оно не дойдёт — в Telegram.</span>
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <Link to={to({})} className={buttonClass({ size: 'lg', block: true })}>
          Записаться к {master.name_forms.dative}
        </Link>
        <span className={styles.powered}>Работает на beautiful.kz</span>
      </footer>
    </div>
  );
}

function NearestSlots({
  master,
  link,
}: {
  readonly master: Master;
  readonly link: (i: BookingIntent) => string;
}) {
  const slots = useSlots(undefined, 4);
  return (
    <section className={styles.section} aria-labelledby="slots" aria-busy={slots.isPending}>
      <h2 id="slots" className={styles.h2}>
        Ближайшие окна
      </h2>
      {slots.isPending ? (
        <div className={styles.chips}>
          {[96, 72, 80, 76].map((w) => (
            <Skeleton key={w} width={w} height={44} radius={12} />
          ))}
        </div>
      ) : slots.isError ? (
        <p className={styles.hint}>
          Не удалось загрузить окна.{' '}
          <button
            type="button"
            className={buttonClass({ variant: 'ghost' })}
            onClick={() => void slots.refetch()}
          >
            Повторить
          </button>
        </p>
      ) : slots.data.length === 0 ? (
        <p className={styles.hint}>
          Свободных окон пока нет — напишите, администратор подберёт время.
        </p>
      ) : (
        <div className={styles.chips}>
          {slots.data.map((s) => (
            <Link
              key={s.start}
              to={link({ start: s.start, ...(s.service_id && { serviceId: s.service_id }) })}
              className={styles.chip}
            >
              {formatSlotShort(s.start, master.timezone)}
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

/** Скелетон страницы на время загрузки. */
function MainSkeleton() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Загрузка">
      <header className={styles.header}>
        <Skeleton width={130} height={14} />
        <Skeleton width={92} height={44} radius={22} />
      </header>
      <div className={styles.hero}>
        <div className={styles.profile}>
          <Skeleton width={84} height={84} radius="50%" />
          <div className={styles.who} style={{ flex: 1 }}>
            <Skeleton width="80%" height={22} />
            <Skeleton width="55%" height={14} />
            <Skeleton width="65%" height={12} />
          </div>
        </div>
        <div className={styles.actions}>
          <Skeleton height={52} radius={16} />
          <Skeleton height={52} radius={16} />
        </div>
        <Skeleton height={84} radius={14} />
      </div>
      <div className={styles.section}>
        <Skeleton width={150} height={16} />
        <Skeleton height={200} radius={18} />
      </div>
    </div>
  );
}

const LONG_DESCRIPTION = 140;

/** Описание услуги мастера: длинное — свёрнуто до трёх строк. */
function ServiceDescription({ text }: { readonly text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > LONG_DESCRIPTION;
  return (
    <>
      <p
        className={long && !open ? `${styles.serviceAbout} ${styles.clamped}` : styles.serviceAbout}
      >
        {text}
      </p>
      {long && (
        <button type="button" className={styles.more} onClick={() => setOpen((o) => !o)}>
          {open ? 'Свернуть' : 'Подробнее'}
        </button>
      )}
    </>
  );
}
