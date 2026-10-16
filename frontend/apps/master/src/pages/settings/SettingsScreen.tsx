import type { MasterSettings } from '@beauty/api';
import { Button, ErrorState, Icon, Notice, Skeleton, iconButtonClass, useOnline } from '@beauty/ui';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useSettings } from '../../entities/settings/queries';
import styles from './Settings.module.css';

/** Экран раздела настроек: шапка «назад», загрузка и ошибка настроек. */
export function SettingsScreen({
  title,
  children,
}: {
  readonly title: string;
  readonly children: (settings: MasterSettings) => ReactNode;
}) {
  const settings = useSettings();
  const online = useOnline();
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to="/settings" className={iconButtonClass()} aria-label="К настройкам">
          <Icon name="back" strokeWidth={2} />
        </Link>
        <h1 className={styles.h1}>{title}</h1>
      </header>
      {settings.data ? (
        children(settings.data)
      ) : settings.isError ? (
        <ErrorState offline={!online} onRetry={() => void settings.refetch()} />
      ) : (
        <div className={styles.body} aria-busy="true">
          <Skeleton height={56} />
          <Skeleton height={56} />
          <Skeleton height={120} />
        </div>
      )}
    </div>
  );
}

/** Нижняя панель «Сохранить» (офлайн — сохранение недоступно). */
export function SaveBar({
  dirty,
  saving,
  label = 'Сохранить',
}: {
  readonly dirty: boolean;
  readonly saving: boolean;
  readonly label?: string;
}) {
  const online = useOnline();
  return (
    <div className={styles.saveBar}>
      {!online && <p className={styles.muted}>Нет соединения — сохранение недоступно</p>}
      <Button
        type="submit"
        size="lg"
        block
        disabled={!dirty || saving || !online}
        aria-busy={saving || undefined}
      >
        {saving ? 'Сохраняем…' : label}
      </Button>
    </div>
  );
}

/** Ошибка формы целиком (ошибка сервера, которую не отнести к полю). */
export function FormError({ text }: { readonly text: string | null }) {
  return text ? (
    <Notice tone="warn" role="alert">
      {text}
    </Notice>
  ) : null;
}
