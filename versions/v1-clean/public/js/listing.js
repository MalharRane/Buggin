// CHANGE-05: rotating promo banner - purely cosmetic, dynamic content that
// changes each time the page is viewed (and every few seconds while on it).
const PROMO_MESSAGES = [
  'Free shipping on orders over $50!',
  'New season arrivals just dropped.',
  'Members save an extra 10% at checkout.',
];

function startPromoBanner() {
  const banner = document.getElementById('promo-banner');
  if (!banner) return;
  let i = Math.floor(Math.random() * PROMO_MESSAGES.length);
  banner.textContent = PROMO_MESSAGES[i];
  setInterval(() => {
    i = (i + 1) % PROMO_MESSAGES.length;
    banner.textContent = PROMO_MESSAGES[i];
  }, 4000);
}

async function renderProductGrid() {
  const grid = document.getElementById('product-grid');
  const products = await Api.getProducts();

  grid.innerHTML = products
    .map(
      (p) => `
    <div class="product-card" data-id="${p.id}">
      <img src="${p.image}" alt="${p.name}">
      <div class="product-card-body">
        <div class="product-name">${p.name}</div>
        <div class="product-price">$${p.price.toFixed(2)}</div>
        <div class="product-card-actions">
          <a class="btn btn-secondary view-details" href="/product.html?id=${p.id}">View Details</a>
          <button class="wishlist-btn" data-id="${p.id}" title="Add to wishlist">&#9825;</button>
        </div>
      </div>
    </div>
  `
    )
    .join('');

  grid.querySelectorAll('.wishlist-btn').forEach((btn) => {
    const id = Number(btn.dataset.id);
    if (Wishlist.has(id)) {
      btn.classList.add('active');
      btn.innerHTML = '&#9829;';
    }
    btn.addEventListener('click', () => {
      const active = Wishlist.toggle(id);
      btn.classList.toggle('active', active);
      btn.innerHTML = active ? '&#9829;' : '&#9825;';
    });
  });
}

startPromoBanner();
renderProductGrid();
