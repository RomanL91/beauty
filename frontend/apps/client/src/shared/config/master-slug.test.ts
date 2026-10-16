import { describe, expect, it } from 'vitest';
import {
  FixedStrategy,
  MasterSlugResolver,
  QueryParamStrategy,
  SubdomainStrategy,
} from './master-slug';

const loc = (hostname: string, search = '') => ({ hostname, search });

describe('MasterSlugResolver', () => {
  const prod = MasterSlugResolver.forEnvironment({ dev: false, defaultMaster: 'alisa' });

  it('прод: поддомен beautiful.kz', () => {
    expect(prod.resolve(loc('alisa.beautiful.kz'))).toBe('alisa');
    expect(prod.resolve(loc('beautiful.kz'))).toBeNull();
    expect(prod.resolve(loc('master.beautiful.kz'))).toBeNull();
    expect(prod.resolve(loc('a.b.beautiful.kz'))).toBeNull();
    expect(prod.resolve(loc('alisa.beautiful.kz.evil.com'))).toBeNull();
    // В проде ?master= и значение по умолчанию игнорируются.
    expect(prod.resolve(loc('beautiful.kz', '?master=alisa'))).toBeNull();
  });

  it('стенд в локальной сети: <slug>.<ip>.nip.io', () => {
    expect(prod.resolve(loc('alisa.192-168-0-143.nip.io'))).toBe('alisa');
    expect(prod.resolve(loc('alisa.192.168.0.143.nip.io'))).toBe('alisa');
    expect(prod.resolve(loc('master.192-168-0-143.nip.io'))).toBeNull();
    expect(prod.resolve(loc('192-168-0-143.nip.io'))).toBeNull();
    expect(prod.resolve(loc('alisa.nip.io.evil.com'))).toBeNull();
  });

  it('dev: *.localhost, затем ?master= (запоминается), затем по умолчанию', () => {
    const memory = new Map<string, string>();
    const dev = new MasterSlugResolver(
      [
        new SubdomainStrategy(['beautiful.kz', 'localhost']),
        new QueryParamStrategy(),
        new FixedStrategy('alisa'),
      ],
      { getItem: (k) => memory.get(k) ?? null, setItem: (k, v) => void memory.set(k, v) },
    );
    expect(dev.resolve(loc('dana.localhost'))).toBe('dana');
    expect(dev.resolve(loc('localhost'))).toBe('alisa');
    expect(dev.resolve(loc('localhost', '?master=dana'))).toBe('dana');
    expect(dev.resolve(loc('localhost'))).toBe('dana');
    expect(dev.resolve(loc('localhost', '?master=BAD SLUG'))).toBe('dana');
  });
});
