import { describe, expect, it } from 'vitest';
import { isIos, vapidKeyToBytes } from './push';
import { safePath } from './safe-path';

describe('push', () => {
  it('VAPID base64url → байты', () => {
    expect(Array.from(vapidKeyToBytes('AQID_-8'))).toEqual([1, 2, 3, 255, 239]);
  });

  it('iOS и iPadOS-как-Mac', () => {
    expect(
      isIos({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)',
        platform: 'iPhone',
        maxTouchPoints: 5,
      }),
    ).toBe(true);
    expect(
      isIos({ userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 5 }),
    ).toBe(true);
    expect(
      isIos({ userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 0 }),
    ).toBe(false);
  });

  it('уведомление открывает только внутренний путь', () => {
    expect(safePath('/chats/1')).toBe('/chats/1');
    expect(safePath('https://evil.example')).toBe('/');
    expect(safePath('//evil.example')).toBe('/');
    expect(safePath(undefined)).toBe('/');
  });
});
