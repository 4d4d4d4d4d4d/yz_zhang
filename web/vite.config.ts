/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': loadEnv(mode, '.', '').PLATFORM_API_PROXY || 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // 打开 CSS 处理，否则 `import '*.css?raw'` 会被短路成空串，
    // 移动端样式约束（MOB-001/003）就无从断言
    css: true,
  },
}));
