import { ApiError } from '../http/api-error';
import { call, unwrap, type HttpCore } from '../http/client';
import type { MasterSettingsGateway } from '../ports/master-settings-gateway';
import type {
  BookingRulesSettings,
  MasterSettings,
  ProfileInput,
  ServiceInput,
  WorkingDay,
} from '../types';

/** Адаптер настроек страницы мастера. */
export class HttpMasterSettingsGateway implements MasterSettingsGateway {
  constructor(private readonly core: HttpCore) {}

  get(): Promise<MasterSettings> {
    return unwrap(() => this.core.api.GET('/me/settings'));
  }

  updateProfile(input: ProfileInput): Promise<MasterSettings> {
    return unwrap(() => this.core.api.PUT('/me/profile', { body: input }));
  }

  addService(input: ServiceInput): Promise<MasterSettings> {
    return unwrap(() => this.core.api.POST('/me/services', { body: input }));
  }

  updateService(serviceId: string, input: ServiceInput): Promise<MasterSettings> {
    return unwrap(() =>
      this.core.api.PUT('/me/services/{service_id}', {
        params: { path: { service_id: serviceId } },
        body: input,
      }),
    );
  }

  archiveService(serviceId: string): Promise<MasterSettings> {
    return unwrap(() =>
      this.core.api.DELETE('/me/services/{service_id}', {
        params: { path: { service_id: serviceId } },
      }),
    );
  }

  setWorkingHours(days: WorkingDay[]): Promise<MasterSettings> {
    return unwrap(() => this.core.api.PUT('/me/working-hours', { body: { days } }));
  }

  setDaysOff(days: string[]): Promise<MasterSettings> {
    return unwrap(() => this.core.api.PUT('/me/days-off', { body: { days } }));
  }

  setBookingRules(rules: BookingRulesSettings): Promise<MasterSettings> {
    return unwrap(() => this.core.api.PUT('/me/booking-rules', { body: rules }));
  }

  addPhoto(file: Blob, alt = ''): Promise<MasterSettings> {
    return sendImage(this.core, 'POST', '/me/photos', file, alt);
  }

  removePhoto(photoId: string): Promise<MasterSettings> {
    return unwrap(() =>
      this.core.api.DELETE('/me/photos/{photo_id}', { params: { path: { photo_id: photoId } } }),
    );
  }

  setAvatar(file: Blob): Promise<MasterSettings> {
    return sendImage(this.core, 'PUT', '/me/avatar', file);
  }

  removeAvatar(): Promise<MasterSettings> {
    return unwrap(() => this.core.api.DELETE('/me/avatar'));
  }

  publish(): Promise<MasterSettings> {
    return unwrap(() => this.core.api.POST('/me/publish'));
  }

  unpublish(): Promise<MasterSettings> {
    return unwrap(() => this.core.api.POST('/me/unpublish'));
  }
}

/** Изображение `multipart/form-data` (как голосовые — напрямую через `fetch` с токеном). */
async function sendImage(
  core: HttpCore,
  method: 'POST' | 'PUT',
  path: string,
  file: Blob,
  alt = '',
): Promise<MasterSettings> {
  const form = new FormData();
  form.set('file', file, `photo.${extensionOf(file.type)}`);
  if (alt) form.set('alt', alt);
  const response = await call(() =>
    core.authorizedFetch(new Request(core.url(path), { method, body: form })),
  );
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw ApiError.fromBody(response.status, body);
  return body as MasterSettings;
}

function extensionOf(mime: string): string {
  if (mime === 'image/png') return 'png';
  if (mime === 'image/webp') return 'webp';
  return 'jpg';
}
