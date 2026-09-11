function renderCartPage() {
  const container = document.getElementById('cart-content');
  const items = Cart.read();

  if (items.length === 0) {
    container.innerHTML = `<p class="empty-cart">Your cart is empty. <a href="/index.html">Continue shopping</a>.</p>`;
    return;
  }

  const rows = items
    .map(
      (i) => `
    <tr data-id="${i.id}">
      <td>${i.name}</td>
      <td>$${i.price.toFixed(2)}</td>
      <td>
        <div class="qty-controls">
          <button class="qty-decrement" data-id="${i.id}">-</button>
          <span class="qty-value">${i.qty}</span>
          <button class="qty-increment" data-id="${i.id}">+</button>
        </div>
      </td>
      <td>$${(i.price * i.qty).toFixed(2)}</td>
    </tr>
  `
    )
    .join('');

  container.innerHTML = `
    <table class="cart-table">
      <thead>
        <tr><th>Product</th><th>Price</th><th>Quantity</th><th>Subtotal</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="cart-summary">
      <div class="total">Total: $${Cart.totalPrice().toFixed(2)}</div>
      <button id="checkout-btn" class="btn btn-primary">Proceed to Payment</button>
    </div>
  `;

  container.querySelectorAll('.qty-increment').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      const item = Cart.read().find((i) => i.id === id);
      Cart.setQty(id, item.qty + 1);
      renderCartPage();
      renderCartBadge();
    });
  });

  container.querySelectorAll('.qty-decrement').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      const item = Cart.read().find((i) => i.id === id);
      Cart.setQty(id, item.qty - 1);
      renderCartPage();
      renderCartBadge();
    });
  });

  document.getElementById('checkout-btn').addEventListener('click', () => {
    window.location.href = '/checkout.html';
  });
}

renderCartPage();
