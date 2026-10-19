import { describe, expect, it } from 'vitest';
import { isSlug, parsePhone, slugOf } from './slug';

describe('адрес страницы и телефон', () => {
  it('адрес — из первого слова имени, латиницей', () => {
    expect(slugOf('Дана Ахметова')).toBe('dana');
    expect(slugOf('Әсем')).toBe('asem');
    expect(slugOf('  Юлия-Мария ')).toBe('yuliya-mariya');
    expect(slugOf('')).toBe('');
    expect(isSlug('dana')).toBe(true);
    expect(isSlug('d')).toBe(false);
    expect(isSlug('Дана')).toBe(false);
  });

  it('телефон приводится к +7XXXXXXXXXX', () => {
    expect(parsePhone('+7 701 123-45-67')).toBe('+77011234567');
    expect(parsePhone('8 701 123 45 67')).toBe('+77011234567');
    expect(parsePhone('')).toBeNull();
    expect(parsePhone('12345')).toBeUndefined();
  });
});
