import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { AssistantPage } from '../pages/assistant/AssistantPage';
import { ChatsPage } from '../pages/chats/ChatsPage';
import { DialogPage } from '../pages/dialog/DialogPage';
import { PlaceholderPage } from '../pages/placeholder/PlaceholderPage';
import { SettingsPage } from '../pages/placeholder/SettingsPage';
import { SchedulePage } from '../pages/schedule/SchedulePage';
import { RootLayout } from './RootLayout';
import { RouteError } from './RouteError';

/** Маршруты кабинета (см. README макетов). */
export const routes: RouteObject[] = [
  {
    element: <RootLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Navigate to="/schedule" replace /> },
      { path: 'schedule/:date?', element: <SchedulePage /> },
      { path: 'chats', element: <ChatsPage /> },
      { path: 'chats/:id', element: <DialogPage /> },
      { path: 'assistant', element: <AssistantPage /> },
      {
        path: 'clients',
        element: (
          <PlaceholderPage
            title="Клиенты"
            text="Карточки клиентов появятся в следующей итерации."
          />
        ),
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
      { path: '*', element: <Navigate to="/schedule" replace /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
