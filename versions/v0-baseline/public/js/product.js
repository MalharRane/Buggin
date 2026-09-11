function getProductIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return Number(params.get('id'));
}

async function renderProductDetail() {
  const container = document.getElementById('product-detail');
  const id = getProductIdFromUrl();

  let product;
  try {
    product = await Api.getProduct(id);
  } catch (e) {
    container.innerHTML = `<p>Sorry, we couldn't load this product. Please go back to <a href="/index.html">Products</a>.</p>`;
    return;
  }

  container.innerHTML = `
    <img src="${product.image}" alt="${product.name}">
    <div>
      <h1>${product.name}</h1>
      <div class="product-rating">★ ${product.rating.value.toFixed(1)} (${product.rating.count} reviews)</div>
      <p>${product.description}</p>
      <div class="product-price">$${product.price.toFixed(2)}</div>
      <br>
      <button id="add-to-cart-btn" class="btn btn-primary">Add to Cart</button>
      <div class="add-to-cart-feedback" id="add-to-cart-feedback"></div>
    </div>
  `;

  document.getElementById('add-to-cart-btn').addEventListener('click', () => {
    Cart.add(product, 1);
    Api.trackAddToCart(product.id);
    document.getElementById('add-to-cart-feedback').textContent = 'Added to cart!';
    renderCartBadge();
  });
}

renderProductDetail();
