// Minimal static file + mock API server. No external dependencies.
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3001;
const PUBLIC_DIR = path.join(__dirname, 'public');
const DATA_DIR = path.join(__dirname, 'data');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
};

function send(res, status, body, headers = {}) {
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', ...headers });
  res.end(body);
}

function sendJSON(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (chunk) => (data += chunk));
    req.on('end', () => resolve(data));
  });
}

function loadProducts() {
  const raw = fs.readFileSync(path.join(DATA_DIR, 'products.json'), 'utf-8');
  return JSON.parse(raw);
}

function serveStatic(req, res, urlPath) {
  let filePath = urlPath === '/' ? '/index.html' : urlPath;
  filePath = path.join(PUBLIC_DIR, decodeURIComponent(filePath.split('?')[0]));

  // Prevent path traversal outside PUBLIC_DIR.
  if (!filePath.startsWith(PUBLIC_DIR)) {
    return send(res, 403, 'Forbidden');
  }

  fs.readFile(filePath, (err, content) => {
    if (err) {
      return send(res, 404, 'Not Found');
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(content);
  });
}

const server = http.createServer(async (req, res) => {
  const [urlPath] = req.url.split('?');

  // ---- API routes ----
  if (urlPath === '/api/products' && req.method === 'GET') {
    return sendJSON(res, 200, loadProducts());
  }

  const productMatch = urlPath.match(/^\/api\/products\/(\d+)$/);
  if (productMatch && req.method === 'GET') {
    const id = Number(productMatch[1]);
    // BUG-08 (category b, network): product id 6 always 404s, even though it exists in the catalog.
    if (id === 6) return sendJSON(res, 404, { error: 'Product not found' });
    const product = loadProducts().find((p) => p.id === id);
    if (!product) return sendJSON(res, 404, { error: 'Product not found' });
    return sendJSON(res, 200, product);
  }

  if (urlPath === '/api/checkout' && req.method === 'POST') {
    await readBody(req);
    // BUG-06 (category b, network): checkout always fails server-side.
    return sendJSON(res, 500, { error: 'Internal Server Error' });
  }

  if (urlPath === '/api/cart/track' && req.method === 'POST') {
    await readBody(req);
    // BUG-07 (category b, network): analytics beacon always fails; no visual impact.
    return sendJSON(res, 400, { error: 'Bad Request' });
  }

  // ---- Static files ----
  return serveStatic(req, res, urlPath);
});

server.listen(PORT, () => {
  console.log(`[v1-buggy] listening on http://localhost:${PORT}`);
});
