/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the FastAPI backend. Defaults to http://localhost:8000 */
  readonly VITE_API_BASE_URL?: string
  /** Must match API_KEY on the backend. It ends up in the built JavaScript, so it is not a secret from site visitors. */
  readonly VITE_API_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
