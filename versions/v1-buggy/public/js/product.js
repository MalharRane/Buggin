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
      <div class="product-rating" id="product-rating">★ New</div>
      <p>${product.description}</p>
      <div class="product-price">$${product.price.toFixed(2)}</div>
      <br>
      <button id="add-to-cart-btn" class="btn btn-primary">Add to Cart</button>
      <div class="add-to-cart-feedback" id="atc-feedback"></div>
    </div>
  `;

  // BUG-12 (category c, console): the initial render uses a "★ New" placeholder,
  // then this enhancement fills in the real rating. Product id 4 has no
  // `rating` field, so this throws an uncaught TypeError - but by this point
  // the page has already rendered fine with the placeholder.
  document.getElementById('product-rating').textContent =
    `★ ${product.rating.value.toFixed(1)} (${product.rating.count} reviews)`;

  document.getElementById('add-to-cart-btn').addEventListener('click', () => {
    // BUG-14 (category d, DOM-missing): this looks up the old element id
    // ("add-to-cart-feedback") which no longer exists in the markup above
    // (it was renamed to "atc-feedback"), so the confirmation message never
    // appears - silently, with no console/network error.
    const feedback = document.getElementById('add-to-cart-feedback');
    if (feedback) feedback.textContent = 'Added to cart!';

    // BUG-09 (category c, console): product id 2 has no `sku` field, so
    // reading `.sku.toUpperCase()` throws an uncaught TypeError here, which
    // aborts the handler before Cart.add() runs. The page shows no visible
    // error - it just silently fails to add the item to the cart.
    if (product.id === 2) {
      console.log('Preparing SKU label: ' + product.sku.toUpperCase());
    }

    Cart.add(product, 1);
    Api.trackAddToCart(product.id);
    renderCartBadge();
  });
}

renderProductDetail();
