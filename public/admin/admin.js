let products=[],orders=[],editing=null,csrfToken='';const $=s=>document.querySelector(s);const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(n);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt={}){opt.headers=opt.headers||{};if(csrfToken && ['POST','PUT','PATCH','DELETE'].includes((opt.method||'GET').toUpperCase()))opt.headers['X-CSRF-Token']=csrfToken;const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.error||'Request failed');return d}
async function boot(){try{const me=await api('/api/admin/me');csrfToken=me.csrfToken||'';$('#login').classList.add('hidden');$('#app').classList.remove('hidden');loadDashboard();loadProducts();loadOrders();loadSettings()}catch{}}
$('#loginForm').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));try{const login=await api('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});csrfToken=login.csrfToken||'';boot()}catch(x){$('#loginErr').textContent=x.message}};
document.querySelectorAll('aside [data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));function showTab(t){document.querySelectorAll('.tab').forEach(x=>x.classList.add('hidden'));$('#'+t).classList.remove('hidden');}
$('#logout').onclick=async()=>{await api('/api/admin/logout',{method:'POST'});location.reload()};
async function loadDashboard(){

    const d = await api('/api/admin/dashboard');

    $('#stats').innerHTML = `
        <div class="stat">
            <span>Products</span>
            <b>${d.activeProducts}</b>
        </div>

        <div class="stat">
            <span>Total orders</span>
            <b>${d.orders}</b>
        </div>

        <div class="stat">
            <span>Pending</span>
            <b>${d.pending}</b>
        </div>

        <div class="stat">
            <span>Revenue</span>
            <b>${money(d.revenue)}</b>
        </div>
    `;

    // Revenue Report
    if (!document.getElementById('revenueFilters')) {

        $('#stats').insertAdjacentHTML('beforebegin', `

            <div id="revenueFilters">

                <h3>Revenue Report</h3>

                <label>
                    Period
                    <select id="revenuePeriod">
                        <option value="yearly">Yearly</option>
                        <option value="monthly">Monthly</option>
                        <option value="daily">Daily</option>
                    </select>
                </label>

                <label>
                    Year
                    <select id="revenueYear"></select>
                </label>

                <label>
                    Month
                    <select id="revenueMonth"></select>
                </label>

                <label>
                    Day
                    <select id="revenueDay"></select>
                </label>

                <button id="viewRevenueBtn">
                    View Revenue
                </button>

                <div id="revenueResult"></div>

            </div>
        `);


        // -----------------------------
        // Year
        // -----------------------------
        const yearSelect =
            document.getElementById('revenueYear');

        const currentYear =
            new Date().getFullYear();

        for (
            let year = currentYear;
            year >= 2000;
            year--
        ) {

            const option =
                document.createElement('option');

            option.value = year;
            option.textContent = year;

            yearSelect.appendChild(option);
        }


        // -----------------------------
        // Month
        // -----------------------------
        const monthSelect =
            document.getElementById('revenueMonth');

        const months = [
            'January',
            'February',
            'March',
            'April',
            'May',
            'June',
            'July',
            'August',
            'September',
            'October',
            'November',
            'December'
        ];

        months.forEach((month, index) => {

            const option =
                document.createElement('option');

            option.value = index + 1;
            option.textContent = month;

            monthSelect.appendChild(option);
        });


        // Current month
        monthSelect.value =
            new Date().getMonth() + 1;


        // -----------------------------
        // Days
        // -----------------------------
        function updateDays(){

            const year =
                parseInt(yearSelect.value);

            const month =
                parseInt(monthSelect.value);

            const daysInMonth =
                new Date(year, month, 0).getDate();

            const daySelect =
                document.getElementById('revenueDay');

            daySelect.innerHTML = '';

            for (
                let day = 1;
                day <= daysInMonth;
                day++
            ) {

                const option =
                    document.createElement('option');

                option.value = day;
                option.textContent = day;

                daySelect.appendChild(option);
            }

            daySelect.value = 1;
        }


        updateDays();


        // -----------------------------
        // Period change
        // -----------------------------
        document
            .getElementById('revenuePeriod')
            .addEventListener('change', function(){

                const period = this.value;

                const month =
                    document.getElementById('revenueMonth');

                const day =
                    document.getElementById('revenueDay');

                if (period === 'yearly') {

                    month.disabled = true;
                    day.disabled = true;

                } else if (period === 'monthly') {

                    month.disabled = false;
                    day.disabled = true;

                } else {

                    month.disabled = false;
                    day.disabled = false;
                }
            });


        yearSelect.addEventListener(
            'change',
            updateDays
        );

        monthSelect.addEventListener(
            'change',
            updateDays
        );


        // -----------------------------
        // View Revenue
        // -----------------------------
        document
            .getElementById('viewRevenueBtn')
            .addEventListener(
                'click',
                loadRevenueReport
            );


        // Start with Yearly
        document.getElementById('revenueMonth').disabled = true;
        document.getElementById('revenueDay').disabled = true;
    }


    $('#recent').innerHTML =
        tableOrders(d.recent);
}
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
async function loadRevenueReport(){

    const period = document.getElementById('revenuePeriod').value;
    const year = document.getElementById('revenueYear').value;
    const month = document.getElementById('revenueMonth').value;
    const day = document.getElementById('revenueDay').value;

    const url =
        `/api/admin/dashboard?period=${period}` +
        `&year=${year}` +
        `&month=${month}` +
        `&day=${day}`;

    const d = await api(url);

    document.getElementById('revenueResult').innerHTML = `
        <div class="revenue-summary">

            <div>
                <span>Selected Period</span>
                <strong>${d.revenueLabel}</strong>
            </div>

            <div>
                <span>Paid Orders</span>
                <strong>${d.paidOrders}</strong>
            </div>

            <div>
                <span>Revenue</span>
                <strong>${money(d.revenue)}</strong>
            </div>

        </div>
    `;
}
function toast(t){const x=$('#toast');x.textContent=t;x.classList.add('show');setTimeout(()=>x.classList.remove('show'),2200)}
(function(){
const THEMES={
classic:{name:'Classic',btn:'#111111',bg:'#ffffff',surface:'#ffffff',ink:'#161616',muted:'#6b6b6b',line:'#e7e7e7',soft:'#f6f5f1',hero1:'#f4efe5',hero2:'#ffe0d6',radius:'18px'},
midnight:{name:'Midnight',btn:'#ff5a36',bg:'#0f1115',surface:'#181b22',ink:'#f2f3f5',muted:'#9aa0ab',line:'#2a2f3a',soft:'#20242d',hero1:'#1b1f2a',hero2:'#2b1f2e',radius:'16px'},
forest:{name:'Fresh Green',btn:'#14532d',bg:'#ffffff',surface:'#ffffff',ink:'#10231a',muted:'#5b6f64',line:'#dfe9e2',soft:'#f1f7f3',hero1:'#e8f5ec',hero2:'#d3eddc',radius:'14px'},
ocean:{name:'Ocean Blue',btn:'#1d4ed8',bg:'#ffffff',surface:'#ffffff',ink:'#0f172a',muted:'#64748b',line:'#e2e8f0',soft:'#f1f5f9',hero1:'#e0ecff',hero2:'#cfe0ff',radius:'14px'},
rose:{name:'Rose',btn:'#be185d',bg:'#fffafb',surface:'#ffffff',ink:'#2a1520',muted:'#7a5c69',line:'#f1dfe6',soft:'#fbf1f5',hero1:'#ffe4ec',hero2:'#ffd1df',radius:'22px'},
mono:{name:'Minimal',btn:'#000000',bg:'#ffffff',surface:'#ffffff',ink:'#000000',muted:'#666666',line:'#dddddd',soft:'#f5f5f5',hero1:'#f5f5f5',hero2:'#ebebeb',radius:'4px'}};
const FONTS={modern:'Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif',serif:'Georgia,"Times New Roman",serif'};
const HEX=/^#[0-9a-f]{6}$/i;
const lum=h=>{const c=[1,3,5].map(i=>parseInt(h.substr(i,2),16)/255).map(v=>v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4));return .2126*c[0]+.7152*c[1]+.0722*c[2]};
const FIELDS=[['btn','Main color (buttons, top bar, footer)'],['bg','Page background'],['ink','Text color'],['hero1','Banner color (left)'],['hero2','Banner color (right)']];
let st={preset:'classic',font:'modern',btn:'',bg:'',ink:'',hero1:'',hero2:'',banner1:'',banner2:'',banner3:''};
function vars(){const t=Object.assign({},THEMES[st.preset]||THEMES.classic);if(HEX.test(st.btn))t.btn=st.btn;if(HEX.test(st.bg)){t.bg=st.bg;t.surface=st.bg}if(HEX.test(st.ink))t.ink=st.ink;if(HEX.test(st.hero1))t.hero1=st.hero1;if(HEX.test(st.hero2))t.hero2=st.hero2;t.btnText=lum(t.btn)>.55?'#111111':'#ffffff';t.font=FONTS[st.font]||FONTS.modern;return t}
const css=document.createElement('style');css.textContent=`
.thH{margin:0 0 14px;font-size:18px}
.thGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.thOpt{border:2px solid #e7e7e7;background:#fff;border-radius:14px;padding:10px;cursor:pointer;text-align:left;font:inherit}
.thOpt.on{border-color:#111;box-shadow:0 0 0 3px rgba(0,0,0,.08)}
.thMini{height:64px;border-radius:10px;background:linear-gradient(115deg,var(--hero1),var(--hero2));position:relative;margin-bottom:8px;border:1px solid var(--line)}
.thMini i{position:absolute;left:10px;bottom:10px;width:46px;height:16px;border-radius:99px;background:var(--btn)}
.thMini b{position:absolute;left:10px;top:10px;width:60px;height:8px;border-radius:4px;background:var(--ink);opacity:.8}
.thName{font-weight:700;font-size:14px}
.thColors{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-bottom:12px}
.thColors label{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid #e7e7e7;border-radius:12px;padding:10px 12px;font-size:14px}
.thColors input[type=color]{width:46px;height:34px;border:0;background:none;padding:0;cursor:pointer}
.thLink{background:none;border:0;color:#1d4ed8;font-weight:700;cursor:pointer;padding:6px 0;font:inherit}
.thFont{display:flex;align-items:center;gap:10px;margin-top:10px;font-size:14px}
.thFont select{padding:9px 12px;border:1px solid #e7e7e7;border-radius:10px;font:inherit}
.thNote{color:#777;margin:0 0 14px;font-size:14px}
.thBn{display:grid;grid-template-columns:80px 1fr 120px;gap:10px;align-items:center;margin-bottom:10px}
.thBn input{padding:10px 12px;border:1px solid #e7e7e7;border-radius:10px;font:inherit;min-width:0}
.thBn img{width:120px;height:45px;object-fit:cover;border-radius:8px;border:1px solid #e7e7e7}
.thPrev{border:1px solid #e7e7e7;border-radius:14px;overflow:hidden;background:var(--bg);color:var(--ink);font-family:var(--font)}
.thTop{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--surface);border-bottom:1px solid var(--line)}
.thTop b{font-size:18px}
.thCartB{background:var(--btn);color:var(--btn-text);padding:6px 12px;border-radius:99px;font-size:12px;font-weight:700}
.thHero{padding:26px 18px;background:linear-gradient(115deg,var(--hero1),var(--hero2))}
.thHero h3{margin:0 0 6px;font-size:22px}
.thHero p{margin:0 0 12px;color:var(--muted)}
.thShop{display:inline-block;background:var(--btn);color:var(--btn-text);padding:9px 16px;border-radius:99px;font-weight:700;font-size:13px}
.thCards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:16px}
.thCard{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:10px;font-size:13px}
.thCard i{display:block;height:60px;border-radius:max(0px,calc(var(--radius) - 6px));background:var(--soft);margin-bottom:8px}
.thCard s{color:var(--muted);margin-left:4px}
.thAdd{margin-top:8px;border:1px solid var(--btn);color:var(--btn);border-radius:9px;padding:6px;text-align:center;font-weight:700;font-size:12px}
.thFoot{background:var(--btn);color:var(--btn-text);padding:12px 16px;font-size:12px}
@media(max-width:640px){.thCards{grid-template-columns:1fr 1fr}.thBn{grid-template-columns:1fr}}`;
document.head.appendChild(css);
const aside=document.querySelector('aside'),main=document.querySelector('main');
const tabBtn=document.createElement('button');tabBtn.dataset.tab='appearance';tabBtn.textContent='Appearance';
aside.insertBefore(tabBtn,aside.querySelector('a'));
const sec=document.createElement('section');sec.id='appearance';sec.className='tab hidden';
sec.innerHTML=`<div class="sectionHead"><div><h1>Appearance</h1><p>Choose a template and colors for your store. No coding needed.</p></div><button class="primary" id="thSave">Save &amp; Publish</button></div>
<div class="panel"><h2 class="thH">1. Choose a template</h2><div class="thGrid" id="thGrid"></div></div>
<div class="panel" style="margin-top:16px"><h2 class="thH">2. Customize colors (optional)</h2><div class="thColors" id="thColors"></div><button class="thLink" id="thReset">Reset to template colors</button><label class="thFont">Font style <select id="thFont"><option value="modern">Modern</option><option value="serif">Elegant serif</option></select></label></div>
<div class="panel" style="margin-top:16px"><h2 class="thH">3. Banner slider (1 to 3 images)</h2><p class="thNote">Paste a direct image link for each banner. Best size: 1600 × 600 px. Leave all three empty to keep the normal text banner. Banners slide automatically every 5 seconds.</p><div id="thBanners"></div></div>
<div class="panel" style="margin-top:16px"><h2 class="thH">4. Preview</h2><div class="thPrev" id="thPrev"></div></div>`;
main.appendChild(sec);
function vstyle(t){return `--btn:${t.btn};--btn-text:${t.btnText};--bg:${t.bg};--surface:${t.surface};--ink:${t.ink};--muted:${t.muted};--line:${t.line};--soft:${t.soft};--hero1:${t.hero1};--hero2:${t.hero2};--radius:${t.radius};--font:${t.font}`}
function renderAll(){
const t=vars();
document.getElementById('thGrid').innerHTML=Object.keys(THEMES).map(k=>{const p=Object.assign({},THEMES[k]);p.btnText=lum(p.btn)>.55?'#111111':'#ffffff';return `<button class="thOpt ${st.preset===k?'on':''}" data-k="${k}" style="--btn:${p.btn};--hero1:${p.hero1};--hero2:${p.hero2};--ink:${p.ink};--line:${p.line}"><div class="thMini"><b></b><i></i></div><div class="thName">${esc(p.name)}</div></button>`}).join('');
document.querySelectorAll('#thGrid .thOpt').forEach(b=>b.onclick=()=>{st.preset=b.dataset.k;st.btn=st.bg=st.ink=st.hero1=st.hero2='';renderAll()});
const box=document.getElementById('thColors');
if(!box.children.length){box.innerHTML=FIELDS.map(f=>`<label>${esc(f[1])}<input type="color" data-k="${f[0]}"></label>`).join('');box.querySelectorAll('input').forEach(i=>i.oninput=()=>{st[i.dataset.k]=i.value;renderPreview()})}
box.querySelectorAll('input').forEach(i=>{const k=i.dataset.k;i.value=HEX.test(st[k])?st[k]:t[k]});
document.getElementById('thFont').value=st.font;
const bb=document.getElementById('thBanners');
if(!bb.children.length){bb.innerHTML=[1,2,3].map(n=>`<div class="thBn"><span>Banner ${n}</span><input data-b="banner${n}" placeholder="https://i.ibb.co/.../banner${n}.jpg"><img alt="" style="display:none"></div>`).join('');bb.querySelectorAll('input').forEach(i=>{i.oninput=()=>{st[i.dataset.b]=i.value.trim();thumb(i)}})}
bb.querySelectorAll('input').forEach(i=>{i.value=st[i.dataset.b]||'';thumb(i)});
renderPreview()}
function thumb(i){const im=i.nextElementSibling;if(/^https?:\/\//i.test(i.value)){im.onerror=()=>{im.style.display='none'};im.src=i.value;im.style.display='block'}else{im.style.display='none'}}
function renderPreview(){const t=vars();const p=document.getElementById('thPrev');p.setAttribute('style',vstyle(t));
p.innerHTML=`<div class="thTop"><b>GRABIT</b><span class="thCartB">Cart 0</span></div><div class="thHero"><h3>Shop smart. GRAB it.</h3><p>Quality products at great prices.</p><span class="thShop">Shop now</span></div><div class="thCards">${[1,2,3].map(n=>`<div class="thCard"><i></i><b>Product ${n}</b><div>₹250<s>₹350</s></div><div class="thAdd">Add to cart</div></div>`).join('')}</div><div class="thFoot">© GRABIT</div>`}
document.getElementById('thReset').onclick=()=>{st.btn=st.bg=st.ink=st.hero1=st.hero2='';renderAll()};
document.getElementById('thFont').onchange=e=>{st.font=e.target.value;renderPreview()};
document.getElementById('thSave').onclick=async()=>{const b=document.getElementById('thSave');b.disabled=true;try{await api('/api/admin/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({themePreset:st.preset,themeFont:st.font,themeBtn:st.btn,themeBg:st.bg,themeInk:st.ink,themeHero1:st.hero1,themeHero2:st.hero2,banner1:st.banner1,banner2:st.banner2,banner3:st.banner3})});toast('Saved. Your store now uses this look.')}catch(e){toast(e.message)}finally{b.disabled=false}};
async function load(){try{const s=await api('/api/admin/settings');st={preset:THEMES[s.themePreset]?s.themePreset:'classic',font:FONTS[s.themeFont]?s.themeFont:'modern',btn:s.themeBtn||'',bg:s.themeBg||'',ink:s.themeInk||'',hero1:s.themeHero1||'',hero2:s.themeHero2||'',banner1:s.banner1||'',banner2:s.banner2||'',banner3:s.banner3||''}}catch(e){}renderAll()}
tabBtn.onclick=()=>{showTab('appearance');load()};
renderAll();
})();


(function(){
const FIELDS=[
['bizName','Business / legal name','e.g. GRABIT Traders'],
['gstin','GSTIN (optional)','e.g. 32ABCDE1234F1Z5'],
['hours','Working hours','e.g. Mon to Sat, 10 AM to 6 PM'],
['shipAreas','Delivery areas','across India'],
['dispatchDays','Dispatch time (business days)','1-2'],
['deliveryDays','Delivery time (business days)','3-7'],
['returnDays','Return window (days after delivery)','7'],
['refundDays','Refund time (business days)','5-7'],
['nonReturnable','Items that cannot be returned (optional)','e.g. opened personal-care items'],
['priceNote','Price note','Prices are inclusive of all applicable taxes.'],
['grievanceName','Grievance officer name','Your name'],
['grievanceEmail','Grievance officer email (uses store email if empty)','you@example.com'],
['jurisdiction','City and state for legal disputes','e.g. Kozhikode, Kerala']];
const PAGES=[['about-us','About Us'],['contact-us','Contact Us'],['pricing','Pricing Details'],['shipping-policy','Shipping Policy'],['refund-policy','Cancellation & Refund Policy'],['terms','Terms & Conditions'],['privacy-policy','Privacy Policy']];
const css=document.createElement('style');css.textContent=`
.plNote{color:#555;margin:0 0 14px;font-size:14px;line-height:1.55}
.plWarn{background:#fff4e5;border:1px solid #ffd8a8;border-radius:12px;padding:12px 14px;margin-bottom:14px;font-size:14px;line-height:1.6}
.plOk{background:#e4f6ea;border:1px solid #b7e4c7;border-radius:12px;padding:12px 14px;margin-bottom:14px;font-size:14px}
.plGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.plGrid label{display:grid;gap:6px;font-size:13px;font-weight:700}
.plGrid input{padding:11px 12px;border:1px solid #e7e7e7;border-radius:10px;font:inherit;font-weight:400}
.plLinks{display:grid;gap:8px;margin:0;padding:0;list-style:none;font-size:14px}
.plLinks li{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;border:1px solid #e7e7e7;border-radius:10px;padding:9px 12px}
.plLinks b{min-width:190px}
.plLinks code{background:#f6f5f1;padding:3px 8px;border-radius:6px;word-break:break-all}
`;document.head.appendChild(css);
const aside=document.querySelector('aside'),main=document.querySelector('main');
const tabBtn=document.createElement('button');tabBtn.dataset.tab='policies';tabBtn.textContent='Policies';
aside.insertBefore(tabBtn,aside.querySelector('a'));
const sec=document.createElement('section');sec.id='policies';sec.className='tab hidden';
sec.innerHTML=`<div class="sectionHead"><div><h1>Policies &amp; legal pages</h1><p>Razorpay needs these pages on your website before it gives you live keys. They are created automatically from the details below.</p></div><button class="primary" id="plSave">Save</button></div>
<div id="plCheck"></div>
<div class="panel"><h2 class="thH">1. Your details</h2><p class="plNote">Your phone, email and address come from <b>Store Settings</b>. Fill in the rest here. Short answers are fine, and anything left empty uses a sensible default.</p><div class="plGrid" id="plGrid"></div></div>
<div class="panel" style="margin-top:16px"><h2 class="thH">2. Your pages</h2><p class="plNote">Click a page to read it. Paste these links into Razorpay (Account &amp; Settings, then Business website details). The same links are in your store's footer.</p><ul class="plLinks" id="plLinks"></ul></div>
<div class="panel" style="margin-top:16px"><p class="plNote" style="margin:0"><b>Please note:</b> these pages are templates written for a small Indian online store. Read each one, make sure it matches how you really work (for example your return and refund promises), and have a professional review them if you can. They are not legal advice.</p></div>`;
main.appendChild(sec);
document.getElementById('plGrid').innerHTML=FIELDS.map(f=>`<label>${esc(f[1])}<input data-k="${f[0]}" placeholder="${esc(f[2])}"></label>`).join('');
document.getElementById('plLinks').innerHTML=PAGES.map(p=>{const u=location.origin+'/policy/'+p[0];return `<li><b><a href="/policy/${p[0]}" target="_blank">${esc(p[1])}</a></b><code>${esc(u)}</code></li>`}).join('');
async function load(){let s={};try{s=await api('/api/admin/settings')}catch(e){}
document.querySelectorAll('#plGrid input').forEach(i=>{i.value=s[i.dataset.k]||''});
const need=[];if(!(s.phone||'').trim())need.push('phone number');if(!(s.email||'').trim())need.push('email address');if(!(s.address||'').trim())need.push('business address');if(!(s.storeName||'').trim())need.push('store name');
document.getElementById('plCheck').innerHTML=need.length?`<div class="plWarn"><b>Still missing in Store Settings:</b> ${need.map(esc).join(', ')}. Razorpay checks your Contact Us page for these, so please add them in the <b>Store Settings</b> tab.</div>`:'<div class="plOk">Your store phone, email and address are filled in. Your Contact Us page is ready.</div>'}
document.getElementById('plSave').onclick=async()=>{const b=document.getElementById('plSave');b.disabled=true;const body={};document.querySelectorAll('#plGrid input').forEach(i=>{body[i.dataset.k]=i.value.trim()});try{await api('/api/admin/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});toast('Saved. Your policy pages are updated.')}catch(e){toast(e.message)}finally{b.disabled=false}};
tabBtn.onclick=()=>{showTab('policies');load()};
})();

boot();
