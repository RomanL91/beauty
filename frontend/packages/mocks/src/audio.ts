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
