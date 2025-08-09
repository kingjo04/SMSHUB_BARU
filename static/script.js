// Event Listeners
document.getElementById('createOrderBtn').addEventListener('click', createOrder);
document.getElementById('refreshBtn').addEventListener('click', updateStatuses);

// Objek untuk menyimpan interval polling per order
const pollingIntervals = {};

// Fungsi utama
async function createOrder() {
    try {
        const btn = document.getElementById('createOrderBtn');
        btn.innerHTML = '⏳ Membuat...';
        btn.disabled = true;

        const service = document.getElementById('serviceSelect').value;
        const country = document.getElementById('countrySelect').value;

        const response = await fetch('/api/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ service, country })
        });
        
        const result = await response.json();
        if (!result.success) throw result.error || 'Gagal membuat order';
        
        alert(`✅ Order ${result.order.id} berhasil dibuat!`);
        fetchOrders();
        
    } catch (error) {
        alert(`❌ Error: ${error}`);
    } finally {
        const btn = document.getElementById('createOrderBtn');
        btn.innerHTML = '🚀 Buat Order Baru';
        btn.disabled = false;
    }
}

async function fetchOrders() {
    try {
        const response = await fetch('/api/orders');
        const result = await response.json();
        if (result.success) {
            displayOrders(result.orders);
        } else {
            throw result.error || 'Gagal memuat orders';
        }
    } catch (error) {
        console.error('Error fetching orders:', error);
        document.getElementById('ordersTable').innerHTML = '<tr><td colspan="7">Error loading orders</td></tr>';
    }
}

async function fetchBalance() {
    try {
        const response = await fetch('/api/balance');
        const result = await response.json();
        if (result.success) {
            document.getElementById('balance').textContent = `Saldo: ${result.balance}`;
        } else {
            document.getElementById('balance').textContent = 'Saldo: Error';
        }
    } catch (error) {
        console.error('Error fetching balance:', error);
        document.getElementById('balance').textContent = 'Saldo: Error';
    }
}

async function updateStatuses() {
    const orders = document.querySelectorAll('#ordersTable tr[data-order-id]');
    for (const row of orders) {
        const orderId = row.dataset.orderId;
        try {
            const response = await fetch(`/api/status/${orderId}`);
            const result = await response.json();
            if (result.status === 'COMPLETED') {
                row.cells[4].textContent = 'COMPLETED';
                row.cells[5].textContent = result.sms || '-';
                // Hentikan polling untuk order ini jika ada
                if (pollingIntervals[orderId]) {
                    clearInterval(pollingIntervals[orderId]);
                    delete pollingIntervals[orderId];
                }
            } else {
                row.cells[4].textContent = result.status;
            }
        } catch (error) {
            console.error(`Error updating status for order ${orderId}:`, error);
        }
    }
}

async function requestAgain(orderId) {
    try {
        const response = await fetch(`/api/request_again/${orderId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        const result = await response.json();
        if (result.success) {
            alert(`✅ SMS untuk order ${orderId} diminta ulang!`);
            fetchOrders(); // Soft refresh orders list
            // Mulai polling status untuk order ini
            startPollingStatus(orderId);
        } else {
            throw result.error || 'Gagal meminta ulang SMS';
        }
    } catch (error) {
        alert(`❌ Error: ${error}`);
    }
}

function startPollingStatus(orderId) {
    // Hentikan polling sebelumnya jika ada
    if (pollingIntervals[orderId]) {
        clearInterval(pollingIntervals[orderId]);
    }

    // Mulai polling baru setiap 5 detik
    pollingIntervals[orderId] = setInterval(async () => {
        try {
            const response = await fetch(`/api/status/${orderId}`);
            const result = await response.json();
            if (result.status === 'COMPLETED') {
                // Update UI untuk order ini
                const row = document.querySelector(`#ordersTable tr[data-order-id="${orderId}"]`);
                if (row) {
                    row.cells[4].textContent = 'COMPLETED';
                    row.cells[5].textContent = result.sms || '-';
                    row.cells[6].innerHTML = `<button onclick="requestAgain('${orderId}')">Minta Ulang</button><button onclick="removeOrder('${orderId}')">Hapus</button>`;
                }
                // Hentikan polling setelah status COMPLETED
                clearInterval(pollingIntervals[orderId]);
                delete pollingIntervals[orderId];
            } else {
                // Update status jika bukan COMPLETED
                const row = document.querySelector(`#ordersTable tr[data-order-id="${orderId}"]`);
                if (row) {
                    row.cells[4].textContent = result.status;
                }
            }
        } catch (error) {
            console.error(`Error polling status for order ${orderId}:`, error);
        }
    }, 5000); // Polling setiap 5 detik

    // Hentikan polling setelah 5 menit (300000 ms) jika tidak COMPLETED
    setTimeout(() => {
        if (pollingIntervals[orderId]) {
            clearInterval(pollingIntervals[orderId]);
            delete pollingIntervals[orderId];
            console.log(`Polling untuk order ${orderId} dihentikan setelah 5 menit`);
        }
    }, 300000);
}

function displayOrders(orders) {
    const tableBody = document.getElementById('ordersTable');
    tableBody.innerHTML = '';

    orders.forEach(order => {
        const row = document.createElement('tr');
        row.dataset.orderId = order.id;
        row.innerHTML = `
            <td>${order.id}</td>
            <td>${order.number}</td>
            <td>${order.service}</td>
            <td>${order.country}</td>
            <td>${order.status}</td>
            <td>${order.status === 'COMPLETED' ? (order.sms || '-') : 'Waiting'}</td>
            <td>
                ${order.status === 'COMPLETED' ? 
                    `<button onclick="requestAgain('${orderId}')">Minta Ulang</button>` : 
                    `<button onclick="cancelOrder('${orderId}')">Batal</button>`}
                <button onclick="removeOrder('${orderId}')">Hapus</button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

async function cancelOrder(orderId) {
    try {
        const response = await fetch(`/api/cancel/${orderId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        const result = await response.json();
        if (result.success) {
            alert(`✅ Order ${orderId} dibatalkan!`);
            // Hentikan polling jika ada
            if (pollingIntervals[orderId]) {
                clearInterval(pollingIntervals[orderId]);
                delete pollingIntervals[orderId];
            }
            fetchOrders(); // Soft refresh orders list
        } else {
            throw result.error || 'Gagal membatalkan order';
        }
    } catch (error) {
        alert(`❌ Error: ${error}`);
    }
}

async function removeOrder(orderId) {
    try {
        const response = await fetch(`/api/remove_order/${orderId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        const result = await response.json();
        if (result.success) {
            alert(`✅ Order ${orderId} dihapus!`);
            // Hentikan polling jika ada
            if (pollingIntervals[orderId]) {
                clearInterval(pollingIntervals[orderId]);
                delete pollingIntervals[orderId];
            }
            fetchOrders(); // Soft refresh orders list
        } else {
            throw result.error || 'Gagal menghapus order';
        }
    } catch (error) {
        alert(`❌ Error: ${error}`);
    }
}

function startAutoRefresh() {
    setInterval(() => {
        fetchBalance();
        updateStatuses();
    }, 30000); // Refresh setiap 30 detik
}

// Initialize
fetchBalance();
fetchOrders();
startAutoRefresh();