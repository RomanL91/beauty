import { describe, expect, it } from 'vitest';
import { pageUrl } from './links';

describe('ссылка на страницу мастера', () => {
  it('поддомен рядом с панелью', () => {
    expect(pageUrl('alisa', { protocol: 'https:', host: 'admin.beautiful.kz' })).toBe(
      'https://alisa.beautiful.kz/',
    );
    expect(pageUrl('alisa', { protocol: 'http:', host: 'admin.localhost:8080' })).toBe(
      'http://alisa.localhost:8080/',
    );
    expect(pageUrl('alisa', { protocol: 'http:', host: 'localhost:5175' })).toBe(
      'https://alisa.beautiful.kz/',
    );
  });
});
