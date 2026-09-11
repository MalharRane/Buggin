// Cart state, persisted in localStorage (scoped to this app's origin/port).
const Cart = {
  KEY: 'buggin_cart',

  read() {
    try {
      const raw = localStorage.getItem(this.KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  },

  write(items) {
    localStorage.setItem(this.KEY, JSON.stringify(items));
  },

  add(product, qty = 1) {
    const items = this.read();
    const existing = items.find((i) => i.id === product.id);
    if (existing) {
      existing.qty += qty;
    } else {
      items.push({ id: product.id, name: product.name, price: product.price, image: product.image, qty });
    }
    this.write(items);
  },

  setQty(id, qty) {
    let items = this.read();
    if (qty <= 0) {
      items = items.filter((i) => i.id !== id);
    } else {
      const item = items.find((i) => i.id === id);
      if (item) item.qty = qty;
    }
    this.write(items);
  },

  totalCount() {
    return this.read().reduce((sum, i) => sum + i.qty, 0);
  },

  totalPrice() {
    return this.read().reduce((sum, i) => sum + i.qty * i.price, 0);
  },

  clear() {
    this.write([]);
  },
};

function renderCartBadge() {
  const badge = document.querySelector('.cart-badge');
  if (badge) badge.textContent = Cart.totalCount();
}

document.addEventListener('DOMContentLoaded', renderCartBadge);
