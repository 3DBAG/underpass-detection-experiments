/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FCB_URL?: string;
  readonly VITE_COPC_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
