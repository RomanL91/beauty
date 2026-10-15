import type { ReactNode } from 'react';
import styles from './AppShell.module.css';

/** Колонка приложения: на широком экране — до 480 px по центру. */
export function AppShell({ children }: { readonly children: ReactNode }) {
  return <div className={styles.shell}>{children}</div>;
}
