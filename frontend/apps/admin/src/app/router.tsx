import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { AdminsPage } from '../pages/AdminsPage';
import { AgentPage } from '../pages/AgentPage';
import { AuditPage } from '../pages/AuditPage';
import { ClientsPage } from '../pages/ClientsPage';
import { DashboardPage } from '../pages/DashboardPage';
import { LoginPage } from '../pages/LoginPage';
import { MasterPage } from '../pages/MasterPage';
import { MastersPage } from '../pages/MastersPage';
import { SystemPage } from '../pages/SystemPage';
import { Layout } from './Layout';

/** Маршруты панели. */
export const routes: RouteObject[] = [
  { path: 'login', element: <LoginPage /> },
  {
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'masters', element: <MastersPage /> },
      { path: 'masters/:id', element: <MasterPage /> },
      { path: 'clients', element: <ClientsPage /> },
      { path: 'agent', element: <AgentPage /> },
      { path: 'admins', element: <AdminsPage /> },
      { path: 'audit', element: <AuditPage /> },
      { path: 'system', element: <SystemPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
