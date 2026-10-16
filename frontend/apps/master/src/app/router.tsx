import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { AssistantRoute } from '../pages/assistant/AssistantRoute';
import { LoginPage } from '../pages/login/LoginPage';
import { ChatsPage } from '../pages/chats/ChatsPage';
import { DialogPage } from '../pages/dialog/DialogPage';
import { PlaceholderPage } from '../pages/placeholder/PlaceholderPage';
import { HoursSettings } from '../pages/settings/HoursSettings';
import { PhotosSettings } from '../pages/settings/PhotosSettings';
import { ProfileSettings } from '../pages/settings/ProfileSettings';
import { RulesSettings } from '../pages/settings/RulesSettings';
import { ServicesSettings } from '../pages/settings/ServicesSettings';
import { SettingsPage } from '../pages/settings/SettingsPage';
import { SchedulePage } from '../pages/schedule/SchedulePage';
import { RootLayout } from './RootLayout';
import { RouteError } from './RouteError';

/** Маршруты кабинета (см. README макетов). */
export const routes: RouteObject[] = [
  { path: 'login', element: <LoginPage />, errorElement: <RouteError /> },
  {
    element: <RootLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Navigate to="/schedule" replace /> },
      { path: 'schedule/:date?', element: <SchedulePage /> },
      { path: 'chats', element: <ChatsPage /> },
      { path: 'chats/:id', element: <DialogPage /> },
      { path: 'assistant', element: <AssistantRoute /> },
      {
        path: 'clients',
        element: (
          <PlaceholderPage
            title="Клиенты"
            text="Карточки клиентов появятся в следующей итерации."
          />
        ),
      },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'settings/profile', element: <ProfileSettings /> },
      { path: 'settings/services', element: <ServicesSettings /> },
      { path: 'settings/hours', element: <HoursSettings /> },
      { path: 'settings/rules', element: <RulesSettings /> },
      { path: 'settings/photos', element: <PhotosSettings /> },
      { path: '*', element: <Navigate to="/schedule" replace /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
