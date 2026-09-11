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
        ${
          /* BUG-15 (category d, DOM-missing): the "View Details" link is
             omitted for product id 1, so there is no way to navigate from
             the listing page to its detail page. */
          p.id === 1
            ? ''
            : `<a class="btn btn-secondary btn-block view-details" href="/product.html?id=${p.id}">View Details</a>`
        }
      </div>
    </div>
  `
    )
    .join('');
}

renderProductGrid();
