/**
 * Тихий WAV нужной длительности — заглушка аудио голосовых в моках
 * (8 кГц, 8 бит, моно: ~8 КБ на секунду).
 */
export function silentWav(seconds: number): Uint8Array<ArrayBuffer> {
  const rate = 8000;
  const samples = Math.max(1, Math.round(seconds * rate));
  const buffer = new ArrayBuffer(44 + samples);
  const view = new DataView(buffer);
  const ascii = (offset: number, text: string): void => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + samples, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate, true);
  view.setUint16(32, 1, true);
  view.setUint16(34, 8, true);
  ascii(36, 'data');
  view.setUint32(40, samples, true);
  new Uint8Array(buffer, 44).fill(128);
  return new Uint8Array(buffer);
}

/** Тихий WAV как `data:` URL — проигрывается `<audio>` без сети. */
export function silentWavDataUrl(seconds: number): string {
  const bytes = silentWav(seconds);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return `data:audio/wav;base64,${btoa(binary)}`;
}

const PALETTE = ['#E9DDE3', '#E8E4E0', '#F1E4EA', '#EAE7E3', '#E2DCD6', '#EFE6EA'];

/** Заглушка фото работы как `data:` URL (SVG). */
export function workPhotoDataUrl(index: number): string {
  const color = PALETTE[index % PALETTE.length] ?? '#E8E4E0';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><rect width="120" height="120" fill="${color}"/><circle cx="60" cy="52" r="18" fill="#fff" opacity=".55"/><rect x="30" y="80" width="60" height="8" rx="4" fill="#fff" opacity=".55"/></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
