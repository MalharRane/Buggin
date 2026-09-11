// Tiny fetch wrappers around the mock API.
const Api = {
  async getProducts() {
    const res = await fetch('/api/products');
    if (!res.ok) throw new Error('Failed to load products: ' + res.status);
    return res.json();
  },

  async getProduct(id) {
    const res = await fetch('/api/products/' + id);
    if (!res.ok) throw new Error('Failed to load product ' + id + ': ' + res.status);
    return res.json();
  },

  async placeOrder(order) {
    const res = await fetch('/api/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(order),
    });
    if (!res.ok) throw new Error('Checkout failed: ' + res.status);
    return res.json();
  },

  trackAddToCart(productId) {
    // Fire-and-forget analytics beacon; failures here should never affect the UI.
    fetch('/api/cart/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ productId, at: Date.now() }),
    }).catch(() => {});
  },
};
