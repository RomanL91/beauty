/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE?: string;
  readonly VITE_VAPID_PUBLIC_KEY?: string;
  readonly VITE_API_PROXY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
