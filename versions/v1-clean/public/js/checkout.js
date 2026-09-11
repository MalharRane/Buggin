// CHANGE-11 (legitimate structural/flow change): checkout now goes through an
// intermediate "review your order" step before the order is actually placed.
// See fixtures/CHANGE_CATALOG.md.

let pendingOrder = null;

function renderReviewSummary(order) {
  const items = order.items;
  const total = items.reduce((sum, i) => sum + i.qty * i.price, 0);

  const rows = items
    .map((i) => `<li>${i.name} &times; ${i.qty} &mdash; $${(i.price * i.qty).toFixed(2)}</li>`)
    .join('');

  document.getElementById('order-review-summary').innerHTML = `
    <ul>${rows}</ul>
    <p><strong>Total: $${total.toFixed(2)}</strong></p>
    <p>${order.name} &middot; ${order.email}</p>
    <p>${order.address}${order.apartment ? ', ' + order.apartment : ''}</p>
  `;
}

document.getElementById('checkout-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const errorContainer = document.getElementById('order-error-container');
  errorContainer.innerHTML = '';

  pendingOrder = {
    name: document.getElementById('name').value,
    email: document.getElementById('email').value,
    address: document.getElementById('address').value,
    apartment: document.getElementById('apartment').value,
    items: Cart.read(),
  };

  renderReviewSummary(pendingOrder);
  document.getElementById('checkout-form').classList.add('hidden');
  document.getElementById('order-review').classList.remove('hidden');
});

document.getElementById('back-to-form-btn').addEventListener('click', () => {
  document.getElementById('order-review').classList.add('hidden');
  document.getElementById('checkout-form').classList.remove('hidden');
});

document.getElementById('confirm-order-btn').addEventListener('click', async () => {
  const reviewErrorContainer = document.getElementById('review-error-container');
  reviewErrorContainer.innerHTML = '';

  try {
    await Api.placeOrder(pendingOrder);
    Cart.clear();
    document.getElementById('order-review').classList.add('hidden');
    document.getElementById('order-success').classList.remove('hidden');
  } catch (err) {
    reviewErrorContainer.innerHTML = `<div class="order-error">Something went wrong placing your order. Please try again.</div>`;
  }
});
