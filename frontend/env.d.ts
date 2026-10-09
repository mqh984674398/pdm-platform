/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'memory' for a self-contained demo build without server URL rewrites. */
  readonly VITE_ROUTER?: string
  /** 'mock' runs the Data Source Studio on the offline snapshot instead of the backend. */
  readonly VITE_STUDIO_API?: string
}
