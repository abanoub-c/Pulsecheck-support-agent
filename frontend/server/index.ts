import './load-env.js';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import apiRouter from './routes/api.js';

const app = express();
const port = Number(process.env.PORT ?? process.env.FRONTEND_PORT ?? 3000);
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

app.set('trust proxy', 1);
app.disable('x-powered-by');
const allowedOrigins = new Set(
  [process.env.CORS_ORIGINS, process.env.CORS_ORIGIN]
    .filter(Boolean)
    .flatMap((value) => value!.split(','))
    .map((origin) => origin.trim())
    .filter(Boolean),
);
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  const origin = req.header('origin');
  if (origin && allowedOrigins.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  }
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  return next();
});
app.use(express.json({ limit: '16kb' }));
app.get('/_app/health', (_req, res) => res.status(200).json({ status: 'ok' }));
app.use('/api', apiRouter);

if (process.env.NODE_ENV === 'development') {
  const { createServer: createViteServer } = await import('vite');
  const vite = await createViteServer({
    root: projectRoot,
    configFile: path.join(projectRoot, 'vite.config.ts'),
    server: { middlewareMode: true, hmr: { clientPort: undefined } },
    appType: 'spa',
  });
  app.use(vite.middlewares);
  app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    vite.ssrFixStacktrace(error as Error);
    res.status(500).send('Development server error');
  });
} else {
  const distDir = path.join(projectRoot, 'dist');
  app.use(express.static(distDir, { index: false, maxAge: '1h' }));
  app.use((req, res, next) => {
    if (req.method !== 'GET' || req.path.startsWith('/api/') || req.path.startsWith('/_app/')) return next();
    return res.sendFile(path.join(distDir, 'index.html'));
  });
}

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error('Unhandled request error:', error instanceof Error ? error.message : 'unknown');
  if (!res.headersSent) res.status(500).json({ error: 'The request could not be completed.' });
});

app.listen(port, '0.0.0.0', () => {
  console.log(`Pulsecheck Support listening on 0.0.0.0:${port} (${process.env.NODE_ENV ?? 'development'})`);
});
