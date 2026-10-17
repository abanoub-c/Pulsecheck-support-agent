import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

// Do not override environment values injected by Render, Vercel, or the shell.
dotenv.config({ path: path.join(projectRoot, '.env'), override: false });
