let products=[],orders=[],editing=null,csrfToken='';const $=s=>document.querySelector(s);const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(n);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt={}){opt.headers=opt.headers||{};if(csrfToken && ['POST','PUT','PATCH','DELETE'].includes((opt.method||'GET').toUpperCase()))opt.headers['X-CSRF-Token']=csrfToken;const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.error||'Request failed');return d}
async function boot(){try{const me=await api('/api/admin/me');csrfToken=me.csrfToken||'';$('#login').classList.add('hidden');$('#app').classList.remove('hidden');loadDashboard();loadProducts();loadOrders();loadSettings()}catch{}}
$('#loginForm').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));try{const login=await api('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});csrfToken=login.csrfToken||'';boot()}catch(x){$('#loginErr').textContent=x.message}};
document.querySelectorAll('aside [data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));function showTab(t){document.querySelectorAll('.tab').forEach(x=>x.classList.add('hidden'));$('#'+t).classList.remove('hidden');}
$('#logout').onclick=async()=>{await api('/api/admin/logout',{method:'POST'});location.reload()};
async function loadDashboard(){const d=await api('/api/admin/dashboard');$('#stats').innerHTML=`<div class="stat"><span>Products</span><b>${d.activeProducts}</b></div><div class="stat"><span>Total orders</span><b>${d.orders}</b></div><div class="stat"><span>Pending</span><b>${d.pending}</b></div><div class="stat"><span>Revenue</span><b>${money(d.revenue)}</b></div>`;$('#recent').innerHTML=tableOrders(d.recent)}
async function loadProducts(){products=await api('/api/products');renderProducts()}function renderProducts(){$('#productTable').innerHTML=`<table class="table"><tr><th></th><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Visible</th><th></th></tr>${products.map(p=>`<tr><td><img class="thumb" src="${esc(p.image||'')}" onerror="this.style.visibility='hidden'"></td><td><b>${esc(p.name)}</b></td><td>${esc(p.category)}</td><td>${money(p.price)}</td><td>${p.stock}</td><td>${p.active?'Yes':'No'}</td><td><button class="smallBtn" onclick="openProduct('${p.id}')">Edit</button> <button class="smallBtn danger" onclick="deleteProduct('${p.id}')">Delete</button></td></tr>`).join('')}</table>`}
function openProduct(id=''){editing=id?products.find(p=>p.id===id):null;const f=$('#productForm');f.reset();f.id.value=editing?.id||'';f.name.value=editing?.name||'';f.category.value=editing?.category||'';f.price.value=editing?.price||'';f.compareAtPrice.value=editing?.compareAtPrice||'';f.stock.value=editing?.stock||0;f.image.value=editing?.image||'';f.description.value=editing?.description||'';f.active.checked=editing?editing.active!==false:true;$('#productTitle').textContent=editing?'Edit Product':'Add Product';$('#productModal').classList.remove('hidden')}
function closeProduct(){$('#productModal').classList.add('hidden')}
$('#productForm').onsubmit=async e=>{e.preventDefault();const f=e.target;let image=f.image.value.trim();const data={name:f.name.value,category:f.category.value,price:f.price.value,compareAtPrice:f.compareAtPrice.value,image,description:f.description.value,stock:f.stock.value,active:f.active.checked};try{if(f.id.value)await api('/api/admin/products/'+f.id.value,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});else await api('/api/admin/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});closeProduct();await loadProducts();loadDashboard();toast('Product saved')}catch(x){toast(x.message)}};
async function deleteProduct(id){if(!confirm('Delete this product?'))return;await api('/api/admin/products/'+id,{method:'DELETE'});await loadProducts();loadDashboard();toast('Product deleted')}
async function loadOrders(){orders=await api('/api/admin/orders');$('#orderTable').innerHTML=tableOrders(orders,true)}function tableOrders(list, actions = false) {
    const trackingOptions = [
        { value: 'created', label: 'Order placed' },
        { value: 'paid', label: 'Payment received' },
        { value: 'processing', label: 'Processing' },
        { value: 'shipped', label: 'Shipped' },
        { value: 'delivered', label: 'Delivered' }
    ];

    return `
        <table class="table">
            <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Total</th>
                <th>Payment</th>
                <th>Tracking Status</th>
                <th>Date</th>
            </tr>

            ${list.map(o => `
                <tr>
                    <td>
                        <b>${esc(o.id)}</b><br>
                        <small>${o.items?.length || 0} item(s)</small>
                    </td>

                    <td>
                        ${esc(o.customer?.name)}<br>
                        <small>${esc(o.customer?.phone)}</small>
                    </td>

                    <td>${money(o.total)}</td>

                    <td>${esc(o.paymentStatus)}</td>

                    <td>
                        ${actions ? `
                            <select
                                class="status"
                                onchange="updateStatus('${o.id}', this.value)"
                            >
                                ${trackingOptions.map(s => `
                                    <option
                                        value="${s.value}"
                                        ${o.status === s.value ? 'selected' : ''}
                                    >
                                        ${s.label}
                                    </option>
                                `).join('')}
                            </select>
                        ` : esc(
                            trackingOptions.find(s => s.value === o.status)?.label || o.status
                        )}
                    </td>

                    <td>
                        ${new Date(o.createdAt).toLocaleString('en-IN')}
                    </td>
                </tr>
            `).join('')}
        </table>
    `;
}
async function updateStatus(id,status){await api('/api/admin/orders/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});await loadOrders();loadDashboard();toast('Order updated')}
async function loadSettings(){const s=await api('/api/admin/settings');const fields=[['storeName','Store name'],['tagline','Tagline'],['phone','Phone'],['whatsapp','WhatsApp'],['email','Email'],['address','Address'],['heroTitle','Hero title'],['heroSubtitle','Hero subtitle'],['heroButton','Hero button'],['announcement','Announcement'],['shippingCharge','Shipping charge'],['freeShippingAbove','Free shipping above']];$('#settingsForm').innerHTML=fields.map(([k,l])=>`<label class="${k==='address'||k==='heroSubtitle'||k==='announcement'?'full':''}">${l}<input data-key="${k}" value="${esc(s[k]??'')}"></label>`).join('')}
async function saveSettings(){const body={};document.querySelectorAll('#settingsForm [data-key]').forEach(x=>body[x.dataset.key]=['shippingCharge','freeShippingAbove'].includes(x.dataset.key)?Number(x.value||0):x.value);await api('/api/admin/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});toast('Settings saved')}
function toast(t){const x=$('#toast');x.textContent=t;x.classList.add('show');setTimeout(()=>x.classList.remove('show'),2200)}boot();
