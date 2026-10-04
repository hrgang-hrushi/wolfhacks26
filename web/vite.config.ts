import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import fs from 'node:fs'
import path from 'node:path'

function spaRoutesPlugin(): Plugin {
  return {
    name: 'spa-routes-plugin',
    closeBundle() {
      const distDir = path.resolve(import.meta.dirname || process.cwd(), 'dist')
      const indexPath = path.join(distDir, 'index.html')
      if (!fs.existsSync(indexPath)) return
      const html = fs.readFileSync(indexPath, 'utf-8')

      // Write 404.html for static fallback
      fs.writeFileSync(path.join(distDir, '404.html'), html)

      // Write explicit directory index.html and .html files for key SPA routes
      const routes = ['gov', 'm', 'dashboard']
      for (const r of routes) {
        const dir = path.join(distDir, r)
        fs.mkdirSync(dir, { recursive: true })
        fs.writeFileSync(path.join(dir, 'index.html'), html)
        fs.writeFileSync(path.join(distDir, `${r}.html`), html)
      }
    }
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), spaRoutesPlugin()],
  // MapLibre 6 ships its worker as an ES module.
  worker: { format: 'es' },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
