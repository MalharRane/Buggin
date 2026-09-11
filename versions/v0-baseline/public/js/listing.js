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
        <a class="btn btn-secondary btn-block view-details" href="/product.html?id=${p.id}">View Details</a>
      </div>
    </div>
  `
    )
    .join('');
}

renderProductGrid();
