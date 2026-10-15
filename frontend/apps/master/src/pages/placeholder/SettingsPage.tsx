import { PushPrompt } from '@beauty/pwa/PushPrompt';
import { usePushSubscription } from '@beauty/pwa/push';
import { useContainer } from '../../shared/lib/container-context';
import { BottomNav } from '../../widgets/bottom-nav/BottomNav';

/** Настройки: в итерации 1 — только уведомления. */
export function SettingsPage() {
  const { push: gateway, env } = useContainer();
  const push = usePushSubscription({
    app: 'master',
    vapidKey: env.vapidPublicKey,
    register: (input) => gateway.register(input),
  });
  return (
    <>
      <main
        style={{
          flex: '1 1 auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          padding: '16px 20px',
        }}
      >
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 600 }}>
          Настройки
        </h1>
        <section
          style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
          aria-labelledby="notifications"
        >
          <h2
            id="notifications"
            style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600 }}
          >
            Уведомления
          </h2>
          <PushPrompt
            push={push}
            variant="settings"
            reason="Новые заявки, вопросы, где нужны вы, и итоги поручений — сразу на телефон."
          />
        </section>
        <p style={{ fontSize: 14, color: 'var(--c-text-muted)' }}>
          Профиль, услуги и правила записи появятся в следующей итерации.
        </p>
      </main>
      <BottomNav />
    </>
  );
}
