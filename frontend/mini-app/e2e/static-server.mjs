import { createServer } from 'node:http';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { createReadStream, existsSync, statSync } from 'node:fs';

const root = resolve(process.argv[2] || 'out');
const port = Number(process.argv[3] || process.env.PORT || 3017);
const host = '127.0.0.1';

const types = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.webp', 'image/webp'],
  ['.ico', 'image/x-icon'],
  ['.woff2', 'font/woff2'],
]);

function safeFile(urlPath) {
  let pathname = decodeURIComponent(urlPath.split('?')[0] || '/');
  if (pathname === '/' || pathname === '/mini-app' || pathname === '/mini-app/') pathname = '/index.html';
  if (pathname.startsWith('/mini-app/')) pathname = pathname.slice('/mini-app'.length);
  if (pathname === '/') pathname = '/index.html';
  const candidate = normalize(join(root, pathname));
  if (!candidate.startsWith(root + sep) && candidate !== root) return null;
  if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  return join(root, 'index.html');
}

const server = createServer((req, res) => {
  const file = safeFile(req.url || '/');
  if (!file || !existsSync(file)) {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
    return;
  }
  res.writeHead(200, {
    'content-type': types.get(extname(file)) || 'application/octet-stream',
    'cache-control': 'no-store',
  });
  createReadStream(file).pipe(res);
});

server.listen(port, host, () => {
  console.log(`ROXY static server listening on http://${host}:${port}/mini-app/ from ${root}`);
});
