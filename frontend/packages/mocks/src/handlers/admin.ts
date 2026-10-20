import { delay } from 'msw';
import type { MockDb } from '../db';
import { http, intParam, run } from './support';

/** Админ-панель хозяина сервиса (группа `admin`): сессия — в хранилище моков, CSRF — заголовком. */
export function adminHandlers(db: MockDb) {
  const admin = db.admin;
  const guard = (request: Request) =>
    admin.authorize(request.headers.get('X-CSRF-Token'), request.method !== 'GET');

  return [
    http.post('/admin/auth/login', async ({ request, response }) => {
      await delay(300);
      const body = await request.json();
      return run(() => response(200).json(admin.login(body.login, body.password)));
    }),

    http.get('/admin/auth/me', ({ response }) => run(() => response(200).json(admin.me()))),

    http.post('/admin/auth/logout', ({ request, response }) =>
      run(() => {
        guard(request);
        admin.logout();
        return response(204).empty();
      }),
    ),

    http.post('/admin/auth/password', async ({ request, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        admin.changePassword(body.current_password, body.new_password);
        return response(204).empty();
      });
    }),

    http.get('/admin/dashboard', async ({ request, response }) => {
      await delay(200);
      return run(() => {
        guard(request);
        return response(200).json(admin.dashboard());
      });
    }),

    http.get('/admin/masters', async ({ request, query, response }) => {
      await delay(150);
      return run(() => {
        guard(request);
        return response(200).json({ items: admin.masters(query.get('q'), query.get('status')) });
      });
    }),

    http.post('/admin/masters', async ({ request, response }) => {
      await delay(300);
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(201).json(admin.createMaster(body));
      });
    }),

    http.get('/admin/masters/{master_id}', async ({ request, params, response }) => {
      await delay(150);
      return run(() => {
        guard(request);
        return response(200).json(admin.master(params.master_id));
      });
    }),

    http.put('/admin/masters/{master_id}/owner', async ({ request, params, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(200).json(admin.setOwner(params.master_id, body.phone));
      });
    }),

    http.put('/admin/masters/{master_id}/publication', async ({ request, params, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(200).json(admin.setPublication(params.master_id, body.published));
      });
    }),

    http.put('/admin/masters/{master_id}/agent', async ({ request, params, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(200).json(admin.setAgent(params.master_id, body.enabled));
      });
    }),

    http.put('/admin/masters/{master_id}/broadcasts', async ({ request, params, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(200).json(admin.setBroadcasts(params.master_id, body.allowed));
      });
    }),

    http.get('/admin/clients', async ({ request, query, response }) => {
      await delay(150);
      const blocked = query.get('blocked');
      return run(() => {
        guard(request);
        return response(200).json(
          admin.clients(
            query.get('q'),
            blocked === null ? null : blocked === 'true',
            intParam(query.get('limit'), 50),
            Math.max(0, Number(query.get('offset') ?? 0) || 0),
          ),
        );
      });
    }),

    http.put('/admin/clients/{client_id}/block', async ({ request, params, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(200).json(
          admin.setClientBlock(params.client_id, body.blocked, body.reason),
        );
      });
    }),

    http.get('/admin/agent', ({ request, response }) =>
      run(() => {
        guard(request);
        return response(200).json(admin.agent());
      }),
    ),

    http.get('/admin/system', ({ request, response }) =>
      run(() => {
        guard(request);
        return response(200).json(admin.system());
      }),
    ),

    http.get('/admin/admins', ({ request, response }) =>
      run(() => {
        guard(request);
        return response(200).json({ items: admin.admins() });
      }),
    ),

    http.post('/admin/admins', async ({ request, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(201).json(admin.createAdmin(body));
      });
    }),

    http.patch('/admin/admins/{admin_id}', async ({ request, params, response }) => {
      const body = await request.json();
      return run(() => {
        guard(request);
        return response(200).json(admin.updateAdmin(params.admin_id, body));
      });
    }),

    http.get('/admin/audit', ({ request, query, response }) =>
      run(() => {
        guard(request);
        return response(200).json(
          admin.audit(query.get('before'), intParam(query.get('limit'), 50)),
        );
      }),
    ),
  ];
}
