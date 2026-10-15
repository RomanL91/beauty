/** Псевдо-волна голосового (как в макете): высоты столбиков из seed. */
const BARS = [6, 12, 20, 10, 16, 24, 12, 6, 14, 20, 10, 16, 8, 18, 12, 6, 14, 8, 16, 10, 6, 12, 6];

/** Волна голосового; `progress` 0..1 подсвечивает проигранную часть. */
export function Waveform({
  color,
  playedColor,
  progress = 0,
  width = 150,
}: {
  readonly color: string;
  readonly playedColor?: string;
  readonly progress?: number;
  readonly width?: number;
}) {
  const step = width / BARS.length;
  return (
    <svg width={width} height={28} viewBox={`0 0 ${width} 28`} aria-hidden="true" focusable="false">
      {BARS.map((h, i) => (
        <rect
          key={i}
          x={i * step}
          y={(28 - h) / 2}
          width={3}
          height={h}
          rx={1.5}
          fill={playedColor && i / BARS.length < progress ? playedColor : color}
        />
      ))}
    </svg>
  );
}
