import { useQuery } from '@tanstack/react-query';
import { useContainer, useMasterSlug } from '../../shared/lib/container-context';

/** Ключи кэша страницы мастера. */
export const masterKeys = {
  page: (slug: string) => ['master', slug] as const,
  slots: (slug: string, serviceId?: string) =>
    ['master', slug, 'slots', serviceId ?? 'any'] as const,
};

/** Публичная страница мастера. */
export function useMasterPage() {
  const { masters } = useContainer();
  const slug = useMasterSlug();
  return useQuery({
    queryKey: masterKeys.page(slug),
    queryFn: () => masters.getPage(slug),
    staleTime: 5 * 60_000,
  });
}

/** Ближайшие окна (для услуги или любые). */
export function useSlots(serviceId?: string, limit = 4, enabled = true) {
  const { masters } = useContainer();
  const slug = useMasterSlug();
  return useQuery({
    queryKey: [...masterKeys.slots(slug, serviceId), limit],
    queryFn: () => masters.listSlots(slug, { ...(serviceId && { serviceId }), limit }),
    staleTime: 30_000,
    enabled,
  });
}
