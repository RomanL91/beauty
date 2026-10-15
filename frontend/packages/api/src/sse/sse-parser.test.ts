import { describe, expect, it } from 'vitest';
import { SseParser, type SseFrame } from './sse-parser';

function parse(chunks: string[], initialId: string | null = null) {
  const frames: SseFrame[] = [];
  const retries: number[] = [];
  const parser = new SseParser(
    (f) => frames.push(f),
    (ms) => retries.push(ms),
    initialId,
  );
  chunks.forEach((c) => parser.push(c));
  return { frames, retries, parser };
}

describe('SseParser', () => {
  it('разбирает кадры, разрезанные в любом месте', () => {
    const text = 'id: 1\nevent: message.created\ndata: {"a":1}\n\nid: 2\ndata: {"b":2}\n\n';
    for (let cut = 1; cut < text.length; cut += 1) {
      const { frames } = parse([text.slice(0, cut), text.slice(cut)]);
      expect(frames).toEqual([
        { event: 'message.created', data: '{"a":1}', id: '1' },
        { event: 'message', data: '{"b":2}', id: '2' },
      ]);
    }
  });

  it('CRLF, разрезанный между кусками, — один перевод строки', () => {
    const { frames } = parse(['data: x\r', '\n\r', '\n']);
    expect(frames).toEqual([{ event: 'message', data: 'x', id: null }]);
  });

  it('склеивает многострочный data и пропускает комментарии', () => {
    const { frames } = parse([': ping\n\ndata: a\ndata: b\n\n']);
    expect(frames).toEqual([{ event: 'message', data: 'a\nb', id: null }]);
  });

  it('retry и id сохраняются между кадрами', () => {
    const { frames, retries, parser } = parse(['retry: 3000\nid: 7\n\ndata: z\n\n'], '5');
    expect(retries).toEqual([3000]);
    expect(frames).toEqual([{ event: 'message', data: 'z', id: '7' }]);
    expect(parser.lastEventId).toBe('7');
  });
});
