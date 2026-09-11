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
          <span class="qty-value">${i.qty}</span>
          <button class="qty-increment" data-id="${i.id}">+</button>
        </div>
      </td>
      <td>$${(i.price * i.qty).toFixed(2)}</td>
    </tr>
  `
      // BUG-16 (category d, DOM-missing): the quantity decrement button is
      // gone from every cart row, so a shopper can add items but can never
      // reduce or remove a single unit from the cart.
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
    </div>
  `;
  // BUG-13 (category d, DOM-missing): the "Checkout" button has been removed
  // entirely from the cart page markup above, so the cart -> checkout flow
  // dead-ends here (there is no in-app way to reach /checkout.html).

  container.querySelectorAll('.qty-increment').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      const item = Cart.read().find((i) => i.id === id);
      Cart.setQty(id, item.qty + 1);
      renderCartPage();
      renderCartBadge();

      // BUG-10 (category c, console): fires after the quantity has already
      // been updated and re-rendered correctly, so there is no visual
      // symptom - but `logQuantityChange` is never defined anywhere, so this
      // throws an uncaught ReferenceError on every increment click.
      logQuantityChange(id, item.qty + 1);
    });
  });
}

renderCartPage();
