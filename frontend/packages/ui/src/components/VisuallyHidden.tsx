import type { ReactNode } from 'react';

/** Текст только для скринридеров. */
export function VisuallyHidden({
  children,
  as: Tag = 'span',
}: {
  readonly children: ReactNode;
  readonly as?: 'span' | 'label' | 'h1' | 'h2';
}) {
  return (
    <Tag
      style={{
        position: 'absolute',
        width: 1,
        height: 1,
        padding: 0,
        margin: -1,
        overflow: 'hidden',
        clip: 'rect(0 0 0 0)',
        whiteSpace: 'nowrap',
        border: 0,
      }}
    >
      {children}
    </Tag>
  );
}

/** Стиль визуально скрытого элемента (для `<label>` с `htmlFor`). */
export const visuallyHiddenStyle = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;
