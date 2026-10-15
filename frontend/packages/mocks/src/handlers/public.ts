import { delay } from 'msw';
import type { MockDb } from '../db';
import { http, intParam, run } from './support';

/** Публичная страница мастера и окна. */
export function publicHandlers(db: MockDb) {
  return [
    http.get('/masters/{slug}', async ({ params, response }) => {
      await delay(250);
      return run(() => response(200).json(db.getPage(params.slug)));
    }),
    http.get('/masters/{slug}/slots', async ({ params, query, response }) => {
      await delay(200);
      return run(() =>
        response(200).json({
          items: db.listSlots(params.slug, {
            service: query.get('service'),
            from: query.get('from'),
            to: query.get('to'),
            limit: intParam(query.get('limit'), 20),
          }),
        }),
      );
    }),
  ];
}
