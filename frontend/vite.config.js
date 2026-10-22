import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  // "npm run preview" imita a Vercel (vercel.json): /api va al backend local, en el mismo
  // dominio que la app, igual que en producción.
  preview: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.png', 'apple-touch-icon.png'],
      manifest: {
        name: 'Zola - Gestión de Impresión 3D',
        short_name: 'Zola',
        description: 'Calculadora de precios, ventas, inventario e impresoras para negocios de impresión 3D.',
        lang: 'es',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // Fondo de la pantalla de carga en Android: el mismo azul oscuro del logo de Zola.
        background_color: '#050a1b',
        theme_color: '#5b4bf5',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'pwa-maskable-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: 'pwa-maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Never let the service worker intercept/cache API calls — this is a
        // live business app (stock, pricing, sales); data must always come
        // fresh from the network. Only the built app shell gets precached.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [],
      },
    }),
  ],
})
