let currentBusinessId = null;

// Initialization
document.addEventListener('DOMContentLoaded', fetchBusinesses);

// --- Businesses ---
async function fetchBusinesses() {
    try {
        const response = await fetch('/api/businesses');
        const businesses = await response.json();
        
        const grid = document.getElementById('business-grid');
        grid.innerHTML = '';
        
        if (businesses.length === 0) {
            grid.innerHTML = '<div class="empty-state">No businesses found. Add one to get started.</div>';
            return;
        }

        businesses.forEach(b => {
            const card = document.createElement('div');
            card.className = 'business-card';
            card.onclick = () => openSalesmenPanel(b.id, b.name, b.salesmen_count);
            card.innerHTML = `
                <div class="card-header" style="display:flex; justify-content:space-between">
                    <h3>${b.name}</h3>
                    <button class="btn btn-danger" onclick="deleteBusiness(event, ${b.id})"><i class="fa-solid fa-trash"></i></button>
                </div>
                <div class="business-stats">
                    <span><i class="fa-solid fa-users"></i> ${b.salesmen_count} Salesmen</span>
                    <span><i class="fa-solid fa-phone"></i> ${b.whatsapp_number_id}</span>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (error) {
        console.error('Error fetching businesses:', error);
    }
}

async function handleBusinessSubmit(e) {
    e.preventDefault();
    const data = {
        name: document.getElementById('b-name').value,
        whatsapp_number_id: document.getElementById('b-phone-id').value,
        access_token: document.getElementById('b-access-token').value,
        verify_token: document.getElementById('b-verify-token').value
    };

    try {
        const res = await fetch('/api/businesses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (res.ok) {
            closeBusinessModal();
            fetchBusinesses();
            e.target.reset();
        } else {
            const err = await res.json();
            alert(err.error || 'Failed to add business');
        }
    } catch (error) {
        console.error(error);
    }
}

async function deleteBusiness(e, id) {
    e.stopPropagation(); // prevent opening the panel
    if(!confirm("Are you sure you want to delete this business? All salesmen and data will be lost.")) return;
    
    try {
        await fetch(`/api/businesses/${id}`, { method: 'DELETE' });
        fetchBusinesses();
    } catch(err) {
        console.error(err);
    }
}


// --- Salesmen ---
async function openSalesmenPanel(businessId, businessName, currentCount) {
    currentBusinessId = businessId;
    document.getElementById('panel-business-name').textContent = businessName;
    document.getElementById('salesmen-count').textContent = currentCount;
    
    document.getElementById('salesmen-panel').classList.add('active');
    document.getElementById('overlay').classList.add('active');
    
    fetchSalesmen(businessId);
}

async function fetchSalesmen(businessId) {
    try {
        const response = await fetch(`/api/businesses/${businessId}/salesmen`);
        const salesmen = await response.json();
        
        document.getElementById('salesmen-count').textContent = salesmen.length;
        
        const list = document.getElementById('salesmen-list');
        list.innerHTML = '';
        
        salesmen.forEach(s => {
            const item = document.createElement('div');
            item.className = 'salesman-item';
            item.innerHTML = `
                <div class="s-info" id="s-info-${s.id}">
                    <h4 class="${!s.is_active ? 'text-muted' : ''}">${s.name}</h4>
                    <p class="${!s.is_active ? 'text-muted' : ''}">${s.phone_number}</p>
                    <span class="status-badge ${s.is_active ? 'active' : 'paused'}">${s.is_active ? 'Active' : 'Paused'}</span>
                </div>
                <div class="s-actions">
                    <label class="switch" title="Toggle Active Status">
                        <input type="checkbox" onchange="toggleActiveStatus(${s.id}, this.checked)" ${s.is_active ? 'checked' : ''}>
                        <span class="slider round"></span>
                    </label>
                    <button class="btn btn-secondary btn-sm" onclick="editSalesman(${s.id}, '${s.name.replace(/'/g, "\\'")}', '${s.phone_number.replace(/'/g, "\\'")}')" title="Edit"><i class="fa-solid fa-pen"></i></button>
                    <button class="btn btn-danger btn-sm" onclick="deleteSalesman(${s.id})" title="Delete"><i class="fa-solid fa-trash"></i></button>
                </div>
            `;
            list.appendChild(item);
        });
    } catch (error) {
        console.error('Error fetching salesmen:', error);
    }
}

async function toggleActiveStatus(id, isActive) {
    try {
        const res = await fetch(`/api/salesmen/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive })
        });
        if (res.ok) {
            fetchSalesmen(currentBusinessId);
        } else {
            const err = await res.json();
            alert(err.error || 'Failed to update status');
            fetchSalesmen(currentBusinessId); // revert the UI
        }
    } catch(err) {
        console.error(err);
    }
}

function editSalesman(id, currentName, currentPhone) {
    const infoDiv = document.getElementById(`s-info-${id}`);
    infoDiv.innerHTML = `
        <input type="text" id="edit-name-${id}" value="${currentName}" class="edit-input">
        <input type="text" id="edit-phone-${id}" value="${currentPhone}" class="edit-input">
        <div style="margin-top: 5px;">
            <button class="btn btn-primary btn-sm" onclick="saveSalesman(${id})"><i class="fa-solid fa-check"></i></button>
            <button class="btn btn-secondary btn-sm" onclick="fetchSalesmen(currentBusinessId)"><i class="fa-solid fa-xmark"></i></button>
        </div>
    `;
}

async function saveSalesman(id) {
    const newName = document.getElementById(`edit-name-${id}`).value;
    const newPhone = document.getElementById(`edit-phone-${id}`).value;

    try {
        const res = await fetch(`/api/salesmen/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName, phone_number: newPhone })
        });
        if (res.ok) {
            fetchSalesmen(currentBusinessId);
        } else {
            const err = await res.json();
            alert(err.error || 'Failed to update salesman');
        }
    } catch(err) {
        console.error(err);
    }
}

async function handleSalesmanSubmit(e) {
    e.preventDefault();
    if (!currentBusinessId) return;

    const data = {
        name: document.getElementById('s-name').value,
        phone_number: document.getElementById('s-phone').value
    };

    try {
        const res = await fetch(`/api/businesses/${currentBusinessId}/salesmen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (res.ok) {
            fetchSalesmen(currentBusinessId);
            fetchBusinesses(); // to update count on main dashboard
            e.target.reset();
        } else {
            const err = await res.json();
            alert(err.error || 'Failed to add salesman');
        }
    } catch (error) {
        console.error(error);
    }
}

async function deleteSalesman(id) {
    if(!confirm("Delete this salesman?")) return;
    try {
        await fetch(`/api/salesmen/${id}`, { method: 'DELETE' });
        fetchSalesmen(currentBusinessId);
        fetchBusinesses();
    } catch(err) {
        console.error(err);
    }
}

// --- UI Helpers ---
function openBusinessModal() {
    document.getElementById('business-modal').classList.add('active');
}

function closeBusinessModal() {
    document.getElementById('business-modal').classList.remove('active');
    document.getElementById('business-form').reset();
}

function closeSalesmenPanel() {
    document.getElementById('salesmen-panel').classList.remove('active');
    document.getElementById('overlay').classList.remove('active');
    currentBusinessId = null;
}

function closeAllPanels() {
    closeBusinessModal();
    closeSalesmenPanel();
}
