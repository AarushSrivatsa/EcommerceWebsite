/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Only if the backend runs somewhere else than the page. Default: same origin. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
