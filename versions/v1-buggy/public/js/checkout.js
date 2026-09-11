document.getElementById('checkout-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errorContainer = document.getElementById('order-error-container');
  errorContainer.innerHTML = '';

  const order = {
    name: document.getElementById('name').value,
    email: document.getElementById('email').value,
    address: document.getElementById('address').value,
    items: Cart.read(),
  };

  // BUG-11 (category c, console): scheduled separately so it never blocks or
  // changes the checkout flow itself (no visual or network difference) -
  // `trackCheckoutStart` is never defined, so this throws an uncaught
  // ReferenceError a moment later, independent of whether checkout succeeds.
  setTimeout(() => {
    trackCheckoutStart(order);
  }, 0);

  try {
    await Api.placeOrder(order);
    Cart.clear();
    document.getElementById('checkout-form').classList.add('hidden');
    document.getElementById('order-success').classList.remove('hidden');
  } catch (err) {
    errorContainer.innerHTML = `<div class="order-error">Something went wrong placing your order. Please try again.</div>`;
  }
});
