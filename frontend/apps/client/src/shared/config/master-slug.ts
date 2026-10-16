/** Стратегия определения мастера по адресу страницы. */
export interface SlugStrategy {
  resolve(location: Pick<Location, 'hostname' | 'search'>): string | null;
}

const SLUG = /^[a-z0-9-]{2,40}$/;
/** Поддомены платформы, которые не являются мастерами. */
const RESERVED = new Set(['www', 'master', 'api', 'app', 'admin']);

/** `<slug>.beautiful.kz` в проде, `<slug>.localhost` в dev. */
export class SubdomainStrategy implements SlugStrategy {
  constructor(private readonly rootDomains: readonly string[]) {}

  resolve({ hostname }: Pick<Location, 'hostname'>): string | null {
    const host = hostname.toLowerCase();
    for (const root of this.rootDomains) {
      if (!host.endsWith(`.${root}`)) continue;
      const label = host.slice(0, -(root.length + 1));
      if (!label.includes('.') && SLUG.test(label) && !RESERVED.has(label)) return label;
    }
    return null;
  }
}

/** `<slug>.192-168-0-10.nip.io` — стенд с телефона в локальной сети (DNS nip.io отдаёт IP из имени). */
export class NipIoStrategy implements SlugStrategy {
  private static readonly HOST = /^([a-z0-9-]+)\.\d{1,3}(?:[.-]\d{1,3}){3}\.nip\.io$/;

  resolve({ hostname }: Pick<Location, 'hostname'>): string | null {
    const label = NipIoStrategy.HOST.exec(hostname.toLowerCase())?.[1];
    return label && SLUG.test(label) && !RESERVED.has(label) ? label : null;
  }
}

/** `?master=<slug>` — для dev и превью без поддоменов. */
export class QueryParamStrategy implements SlugStrategy {
  resolve({ search }: Pick<Location, 'search'>): string | null {
    const value = new URLSearchParams(search).get('master')?.toLowerCase() ?? null;
    return value && SLUG.test(value) ? value : null;
  }
}

/** Фиксированный мастер (переменная окружения в dev). */
export class FixedStrategy implements SlugStrategy {
  constructor(private readonly slug: string | null) {}

  resolve(): string | null {
    return this.slug && SLUG.test(this.slug) ? this.slug : null;
  }
}

/**
 * Определяет мастера, чья это страница: первая сработавшая стратегия.
 *
 * Прод: только поддомен. Dev: поддомен `*.localhost`, затем `?master=`
 * (запоминается на сессию вкладки, чтобы переходы по приложению его не теряли),
 * затем мастер по умолчанию.
 */
export class MasterSlugResolver {
  constructor(
    private readonly strategies: readonly SlugStrategy[],
    private readonly memory: Pick<Storage, 'getItem' | 'setItem'> | null = null,
  ) {}

  /** Резолвер под среду сборки. */
  static forEnvironment(options: {
    dev: boolean;
    defaultMaster: string | null;
  }): MasterSlugResolver {
    if (!options.dev)
      return new MasterSlugResolver([
        new SubdomainStrategy(['beautiful.kz', 'localhost']),
        new NipIoStrategy(),
      ]);
    return new MasterSlugResolver(
      [
        new SubdomainStrategy(['beautiful.kz', 'localhost']),
        new NipIoStrategy(),
        new QueryParamStrategy(),
        new FixedStrategy(options.defaultMaster),
      ],
      safeSessionStorage(),
    );
  }

  resolve(location: Pick<Location, 'hostname' | 'search'>): string | null {
    const [first, ...rest] = this.strategies;
    const fromHost = first?.resolve(location) ?? null;
    if (fromHost) return fromHost;
    for (const strategy of rest) {
      const slug = strategy.resolve(location);
      if (slug && !(strategy instanceof FixedStrategy)) {
        this.memory?.setItem('beauty.master', slug);
        return slug;
      }
      if (slug) return this.memory?.getItem('beauty.master') ?? slug;
    }
    return this.memory?.getItem('beauty.master') ?? null;
  }
}

function safeSessionStorage(): Pick<Storage, 'getItem' | 'setItem'> | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}
