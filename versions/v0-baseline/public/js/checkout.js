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

  try {
    await Api.placeOrder(order);
    Cart.clear();
    document.getElementById('checkout-form').classList.add('hidden');
    document.getElementById('order-success').classList.remove('hidden');
  } catch (err) {
    errorContainer.innerHTML = `<div class="order-error">Something went wrong placing your order. Please try again.</div>`;
  }
});
