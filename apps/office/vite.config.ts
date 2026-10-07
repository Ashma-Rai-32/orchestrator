import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    port: 5173, // the Keycloak client's redirect URI expects this port
    strictPort: true,
    // Vite rejects unknown Host headers (DNS-rebinding protection). Allow the name
    // containers use to reach this machine, for browser checks run from a container.
    allowedHosts: ['host.docker.internal'],
  },
  build: {
    chunkSizeWarningLimit: 1500, // Phaser alone is ~1.3 MB minified
  },
})
