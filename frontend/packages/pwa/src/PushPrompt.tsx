import { Button, Icon, Notice } from '@beauty/ui';
import type { usePushSubscription } from './push';

type Push = ReturnType<typeof usePushSubscription>;

/**
 * Плашка «включить уведомления». Показывается по поводу (после записи или в
 * настройках), не при первом заходе. На iOS вне PWA — подсказка про экран «Домой».
 */
export function PushPrompt({
  push,
  reason,
  variant = 'banner',
}: {
  readonly push: Push;
  /** Зачем уведомления: «Сообщим, когда мастер подтвердит запись». */
  readonly reason: string;
  /** `banner` — можно отложить; `settings` — всегда видна. */
  readonly variant?: 'banner' | 'settings';
}) {
  if (variant === 'banner' && (push.dismissed || push.subscribed)) return null;
  if (push.availability === 'unsupported') {
    return variant === 'settings' ? (
      <Notice tone="muted" icon="bell">
        Этот браузер не поддерживает уведомления.
      </Notice>
    ) : null;
  }
  if (push.availability === 'ios-install') {
    return (
      <Notice tone="accent" icon="bell" role="status">
        <strong>Уведомления на iPhone</strong> работают, когда сайт добавлен на экран «Домой»:
        нажмите «Поделиться» → «На экран „Домой“» и откройте приложение оттуда.
        {variant === 'banner' && (
          <div style={{ marginTop: 8 }}>
            <Button variant="ghost" onClick={push.dismiss}>
              Понятно
            </Button>
          </div>
        )}
      </Notice>
    );
  }
  if (push.availability === 'denied') {
    return variant === 'settings' ? (
      <Notice tone="muted" icon="bell">
        Уведомления запрещены в настройках браузера — разрешите их для этого сайта.
      </Notice>
    ) : null;
  }
  if (push.subscribed || push.availability === 'granted') {
    return variant === 'settings' ? (
      <Notice tone="ok" icon="check">
        Уведомления включены на этом устройстве.
      </Notice>
    ) : null;
  }
  if (push.availability === 'no-key') {
    return variant === 'settings' ? (
      <Notice tone="muted" icon="bell">
        Уведомления пока не настроены на сервере.
      </Notice>
    ) : null;
  }
  return (
    <Notice tone="accent" icon="bell" role="status">
      <span>{reason}</span>
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <Button size="md" disabled={push.busy} onClick={() => void push.subscribe()}>
          <Icon name="bell" size={18} strokeWidth={1.9} />
          {push.busy ? 'Включаем…' : 'Включить уведомления'}
        </Button>
        {variant === 'banner' && (
          <Button variant="ghost" onClick={push.dismiss}>
            Не сейчас
          </Button>
        )}
      </div>
      {push.error && <div style={{ marginTop: 6, fontSize: 13 }}>{push.error}</div>}
    </Notice>
  );
}
