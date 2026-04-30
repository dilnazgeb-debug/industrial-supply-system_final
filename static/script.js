// Common load function
async function fetchData(endpoint) {
    try {
        const response = await fetch(`/api/${endpoint}`);
        return await response.json();
    } catch (error) {
        console.error('Error:', error);
        return [];
    }
}

// Load suppliers table
async function loadSuppliers() {
    const data = await fetchData('suppliers');
    const tbody = document.querySelector('#suppliers-table tbody');
    tbody.innerHTML = '';
    data.forEach(supplier => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${supplier.supplier_id}</td>
            <td>${supplier.company_name}</td>
            <td>${supplier.city || 'N/A'}</td>
            <td>${supplier.country}</td>
            <td><a href="${supplier.website}" target="_blank">${supplier.website}</a></td>
        `;
    });
}

// Load products table
async function loadProducts() {
    const data = await fetchData('products');
    const tbody = document.querySelector('#products-table tbody');
    tbody.innerHTML = '';
    
    const filter = document.getElementById('product-filter').value.toLowerCase();
    data.filter(p => 
        p.company_name.toLowerCase().includes(filter) || 
        p.product_type.toLowerCase().includes(filter)
    ).forEach(product => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${product.product_id}</td>
            <td>${product.company_name}</td>
            <td><strong>${product.model}</strong></td>
            <td><span class="badge bg-${product.product_type === 'Screw' ? 'primary' : product.product_type === 'Piston' ? 'secondary' : 'warning'}">${product.product_type}</span></td>
            <td>${product.pressure_bar || 'N/A'}</td>
            <td>${product.power_kw || 'N/A'}</td>
            <td class="fw-bold text-success">$${product.price_usd?.toLocaleString()}</td>
        `;
    });
}

// Load supply chain
async function loadSupplyChain() {
    const data = await fetchData('supply-chain');
    const tbody = document.querySelector('#supply-chain-table tbody');
    tbody.innerHTML = '';
    data.forEach(item => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${item.company_name}</td>
            <td><strong>${item.model}</strong></td>
            <td><span class="badge bg-primary">${item.product_type}</span></td>
            <td>$${item.price_usd?.toLocaleString()}</td>
            <td><span class="badge bg-info">${item.moq}</span></td>
            <td><span class="badge bg-warning">${item.lead_time_days} days</span></td>
            <td><span class="badge bg-success">${item.shipping_terms}</span></td>
        `;
    });
}

// Load forecast + chart
async function loadForecast() {
    const data = await fetchData('forecast');
    const tbody = document.querySelector('#forecast-table tbody');
    tbody.innerHTML = '';
    data.slice(0, 20).forEach(item => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${item.model}</td>
            <td>${item.year}-${item.month.toString().padStart(2, '0')}</td>
            <td class="fw-bold">${item.forecast_qty.toLocaleString()}</td>
        `;
    });

    // Chart
    const ctx = document.getElementById('forecastChart').getContext('2d');
    const monthly = data.reduce((acc, item) => {
        const key = `${item.year}-${item.month}`;
        acc[key] = (acc[key] || 0) + item.forecast_qty;
        return acc;
    }, {});

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: Object.keys(monthly),
            datasets: [{
                label: 'Total Forecasted Units',
                data: Object.values(monthly),
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

// Filter products
document.addEventListener('input', function(e) {
    if (e.target.id === 'product-filter') {
        loadProducts();
    }
});
