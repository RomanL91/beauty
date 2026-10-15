import { StateView } from '@beauty/ui';
import { BottomNav } from '../../widgets/bottom-nav/BottomNav';

/** Раздел вне итерации 1 (Клиенты, Настройки). */
export function PlaceholderPage({
  title,
  text,
}: {
  readonly title: string;
  readonly text: string;
}) {
  return (
    <>
      <main style={{ flex: '1 1 auto' }}>
        <h1
          style={{
            padding: '16px 20px 0',
            fontFamily: 'var(--font-display)',
            fontSize: 20,
            fontWeight: 600,
          }}
        >
          {title}
        </h1>
        <StateView icon="settings" title="Скоро" text={text} />
      </main>
      <BottomNav />
    </>
  );
}
