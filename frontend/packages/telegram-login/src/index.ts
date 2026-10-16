/** Вход через Telegram: состояние, хук и общая панель экранов входа клиента и мастера. */
export { loginReducer, type LoginAction, type LoginState } from './login-state';
export { TelegramLoginPanel } from './TelegramLoginPanel';
export { useTelegramLogin, type TelegramLogin } from './use-telegram-login';
