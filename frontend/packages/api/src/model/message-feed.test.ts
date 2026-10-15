import { describe, expect, it } from 'vitest';
import type { Message } from '../types';
import {
  EMPTY_FEED,
  feedReducer,
  oldestMessageId,
  type FeedAction,
  type FeedState,
} from './message-feed';

let seq = 0;
function msg(minute: number, extra: Partial<Message> & { text?: string } = {}): Message {
  seq += 1;
  return {
    id: `m-${seq}`,
    client_id: null,
    author: 'agent',
    ai_generated: true,
    sources: [],
    created_at: new Date(Date.UTC(2026, 9, 15, 10, minute)).toISOString(),
    kind: 'text',
    text: extra.text ?? `t${seq}`,
    ...extra,
  } as Message;
}

const run = (actions: FeedAction[], from: FeedState = EMPTY_FEED): FeedState =>
  actions.reduce(feedReducer, from);
const texts = (s: FeedState) =>
  s.items.map((i) => (i.message.kind === 'text' ? i.message.text : i.message.kind));

describe('feedReducer', () => {
  it('история: первая страница и подгрузка вверх без дублей', () => {
    const [a, b, c, d] = [
      msg(1, { text: 'a' }),
      msg(2, { text: 'b' }),
      msg(3, { text: 'c' }),
      msg(4, { text: 'd' }),
    ];
    const s1 = run([
      { type: 'history/loaded', page: { items: [c, d], has_more: true }, older: false },
    ]);
    expect(oldestMessageId(s1)).toBe(c.id);
    const s2 = run(
      [{ type: 'history/loaded', page: { items: [a, b, c], has_more: false }, older: true }],
      s1,
    );
    expect(texts(s2)).toEqual(['a', 'b', 'c', 'd']);
    expect(s2.hasMore).toBe(false);
  });

  it('оптимистичное: pending → sent по ответу POST', () => {
    const local = msg(5, { id: 'tmp', client_id: 'c1', author: 'client', text: 'привет' });
    const server = { ...local, id: 'srv-1' };
    const s1 = run([
      { type: 'local/added', message: local, draft: { kind: 'text', text: 'привет' } },
    ]);
    expect(s1.items[0]).toMatchObject({ key: 'local:c1', delivery: 'pending' });
    const s2 = run([{ type: 'local/sent', clientId: 'c1', message: server }], s1);
    expect(s2.items).toHaveLength(1);
    expect(s2.items[0]).toMatchObject({ key: 'srv-1', delivery: 'sent' });
  });

  it('SSE пришёл раньше ответа POST — без дубля', () => {
    const local = msg(5, { id: 'tmp', client_id: 'c2', author: 'client' });
    const server = { ...local, id: 'srv-2' };
    const s = run([
      { type: 'local/added', message: local, draft: { kind: 'text', text: 'x' } },
      { type: 'remote/created', message: server },
      { type: 'local/sent', clientId: 'c2', message: server },
    ]);
    expect(s.items.map((i) => i.key)).toEqual(['srv-2']);
  });

  it('ошибка отправки и повтор', () => {
    const local = msg(5, { client_id: 'c3', author: 'client' });
    const s = run([
      { type: 'local/added', message: local, draft: { kind: 'text', text: 'x' } },
      { type: 'local/failed', clientId: 'c3' },
    ]);
    expect(s.items[0]?.delivery).toBe('failed');
    expect(run([{ type: 'local/retry', clientId: 'c3' }], s).items[0]?.delivery).toBe('pending');
    expect(run([{ type: 'local/discarded', clientId: 'c3' }], s).items).toHaveLength(0);
  });

  it('повтор события SSE после переподключения игнорируется', () => {
    const a = msg(1);
    const s = run([
      { type: 'remote/created', message: a },
      { type: 'remote/created', message: a },
    ]);
    expect(s.items).toHaveLength(1);
  });

  it('обновление заменяет сообщение на месте', () => {
    const a = msg(1, { text: 'old' });
    const b = msg(2);
    const s = run([
      { type: 'history/loaded', page: { items: [a, b], has_more: false }, older: false },
      { type: 'remote/updated', message: { ...a, text: 'new' } as Message },
    ]);
    expect(texts(s)[0]).toBe('new');
    expect(s.items).toHaveLength(2);
  });

  it('новые серверные сообщения встают перед ещё не отправленными локальными', () => {
    const local = msg(10, { client_id: 'c4', author: 'client', text: 'мой' });
    const incoming = msg(9, { text: 'агент' });
    const s = run([
      { type: 'local/added', message: local, draft: { kind: 'text', text: 'мой' } },
      { type: 'remote/created', message: incoming },
    ]);
    expect(texts(s)).toEqual(['агент', 'мой']);
  });

  it('событие из прошлого встаёт по времени', () => {
    const [a, c] = [msg(1, { text: 'a' }), msg(3, { text: 'c' })];
    const b = msg(2, { text: 'b' });
    const s = run([
      { type: 'history/loaded', page: { items: [a, c], has_more: false }, older: false },
      { type: 'remote/created', message: b },
    ]);
    expect(texts(s)).toEqual(['a', 'b', 'c']);
  });
});
