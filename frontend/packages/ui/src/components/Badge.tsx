import type { ReactNode } from 'react';

const TONES = {
  warn: { background: 'var(--c-warn-bg)', color: 'var(--c-warn-ink)' },
  accent: { background: 'var(--c-accent-soft)', color: 'var(--c-accent)' },
  muted: { background: 'var(--c-surface-muted)', color: 'var(--c-text-2)' },
  ok: { background: 'var(--c-ok-bg)', color: 'var(--c-ok-ink)' },
} as const;

/** Бейдж-метка («Нужны вы · заявка», «Ведёт агент»). */
export function Badge({
  tone,
  children,
}: {
  readonly tone: keyof typeof TONES;
  readonly children: ReactNode;
}) {
  return (
    <span
      style={{
        ...TONES[tone],
        alignSelf: 'flex-start',
        padding: '2px 8px',
        borderRadius: 'var(--r-badge)',
        fontSize: 12,
        fontWeight: 700,
        lineHeight: '18px',
      }}
    >
      {children}
    </span>
  );
}
