import { http, HttpResponse } from 'msw';
import { silentWav } from '../audio';
import type { MockDb } from '../db';

const PALETTE = ['#E9DDE3', '#E8E4E0', '#F1E4EA', '#EAE7E3', '#E2DCD6', '#EFE6EA'];

/** Медиа моков: заглушки фото работ и аудио голосовых (вне контракта API). */
export function mediaHandlers(db: MockDb) {
  return [
    http.get('*/mock-media/:name', ({ params }) => {
      const name = String(params['name']);
      const work = /^work-(\d+)\.svg$/.exec(name);
      if (work) {
        const color = PALETTE[Number(work[1]) % PALETTE.length] ?? PALETTE[0];
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><rect width="120" height="120" fill="${color}"/><circle cx="60" cy="52" r="18" fill="#fff" opacity=".55"/><rect x="30" y="80" width="60" height="8" rx="4" fill="#fff" opacity=".55"/></svg>`;
        return new HttpResponse(svg, { headers: { 'Content-Type': 'image/svg+xml' } });
      }
      const seconds = /^voice-(\d+)\.wav$/.exec(name);
      if (seconds) {
        return new HttpResponse(silentWav(Number(seconds[1])), {
          headers: { 'Content-Type': 'audio/wav' },
        });
      }
      const upload = db.upload(name);
      if (upload)
        return new HttpResponse(upload, {
          headers: { 'Content-Type': upload.type || 'audio/webm' },
        });
      return new HttpResponse(null, { status: 404 });
    }),
  ];
}
