import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { host: '0.0.0.0', port: 5173 },
  // Spec 18 — logic-layer coverage gate. Scoped to src/logic (the
  // unit-tested surface); components/views are browser-smoke-tested.
  test: {
    coverage: {
      provider: 'v8',
      include: ['src/logic/**'],
      reporter: ['text', 'text-summary'],
      thresholds: {
        functions: 100,
        statements: 95,
        lines: 95,
        branches: 85
      }
    }
  }
})
