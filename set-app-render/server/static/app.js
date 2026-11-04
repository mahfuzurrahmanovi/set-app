
let currentSet = null;
let allSets = [];
let selectedPid = null;
// Fixed print area (mockup fix, Ovi 2026-11-03 22:43): the dashed box
// is ONE fixed chest area, left 25%, top 20%, width 50%, height 50%
// of the mockup image. Only the design inside it moves. The box
// geometry never changes with placement.
const PRINT_AREA = { left: 0.25, top: 0.20, width: 0.50, height: 0.50 };
// Clamp a placement to the fixed print area, in one place, so the
// centre preview, the sliders, and every save path agree. Scale is
// capped at 0.5 because the box is 50% of the mockup width: a larger
// scale would spill past the box. Rotation is about the design
// centre and may extend past the box corners at large angles; only
// the centre and the width are clamped.
function clampPlacement(pl) {
  const p = pl || {};
  return {
    x: Math.min(PRINT_AREA.left + PRINT_AREA.width, Math.max(PRINT_AREA.left, (p.x === undefined ? 0.5 : +p.x))),
    y: Math.min(PRINT_AREA.top + PRINT_AREA.height, Math.max(PRINT_AREA.top, (p.y === undefined ? 0.45 : +p.y))),
    scale: Math.min(0.5, Math.max(0.1, (p.scale === undefined ? 0.5 : +p.scale))),
    angle: (p.angle === undefined ? 0 : +p.angle)
  };
}
// Printify flat-photo templates, loaded from /api/catalog/templates.
let catalogTemplates = null;
let catalogTemplatesTried = false;
function slugify(name) {
  return (name || '').toLowerCase().trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}
let slugManual = false;
let campaignSlugManual = false;
function bindSlugAuto() {
  const nameEl = document.getElementById('campName');
  const slugEl = document.getElementById('campSlug');
  if (nameEl && slugEl && !nameEl._slugBound) {
    nameEl._slugBound = true;
    nameEl.addEventListener('input', function() {
      if (slugManual) return;
      slugEl.value = slugify(nameEl.value);
      const pv = document.getElementById('campUrlPreview');
      if (pv) pv.textContent = 'fansfit.shop/' + slugEl.value;
    });
    slugEl.addEventListener('input', function() { slugManual = true; });
  }
  const cName = document.getElementById('campaignName');
  const cSlug = document.getElementById('campaignSlug');
  if (cName && cSlug && !cName._slugBound) {
    cName._slugBound = true;
    cName.addEventListener('input', function() {
      if (campaignSlugManual) return;
      cSlug.value = slugify(cName.value);
      const pv = document.getElementById('campaignSlugPreview');
      if (pv) pv.textContent = 'fansfit.shop/' + cSlug.value;
    });
    cSlug.addEventListener('input', function() { campaignSlugManual = true; });
  }
}
function flatTemplateForTitle(title) {
  if (!title || !catalogTemplates) return null;
  const t = String(title).toLowerCase();
  // Classic first, before v-neck: a "Classic Long Sleeve" title must
  // not fall through to the Ultra Cotton template, which is a
  // different product. (No real title is both, but the order must
  // match the plan, not contradict it.)
  if (t.indexOf('classic') !== -1 && t.indexOf('long sleeve') !== -1) {
    return catalogTemplates.filter(function(x) { return x.title && x.title.toLowerCase().indexOf('classic long sleeve') !== -1; })[0] || null;
  }
  if (t.indexOf('v-neck') !== -1 || t.indexOf('v neck') !== -1) {
    return catalogTemplates.filter(function(x) { return x.title && x.title.toLowerCase().indexOf('v-neck') !== -1; })[0] || null;
  }
  if (t.indexOf('long sleeve') !== -1) {
    return catalogTemplates.filter(function(x) { return x.title && x.title.toLowerCase().indexOf('ultra cotton long sleeve') !== -1; })[0]
      || catalogTemplates.filter(function(x) { return x.title && x.title.toLowerCase().indexOf('long sleeve') !== -1; })[0] || null;
  }
  return null;
}
function printifyImageOf(p) {
  // Exact Printify photo already on file for this store product, if
  // any. Never invented: only a stored URL containing
  // images.printify.com counts.
  if (!p) return '';
  const urls = [];
  if (p.image) urls.push(p.image);
  (p.images || []).forEach(function(u) { urls.push(u); });
  for (let i = 0; i < urls.length; i++) {
    if (urls[i] && urls[i].indexOf('images.printify.com') !== -1) return urls[i];
  }
  return '';
}
let viewSide = 'front';
let lastSearchResults = [];
let csrfToken = null;
let dirty = false;
let editingLayerId = null;
// CSRF + login handling: every POST carries the session token; a 401
// anywhere opens the login form instead of failing silently.
const _realFetch = window.fetch.bind(window);
async function ensureCsrf() {
  if (csrfToken) return csrfToken;
  const r = await _realFetch('/api/csrf-token');
  const j = await r.json();
  csrfToken = j.csrf_token;
  return csrfToken;
}
window.fetch = async function(url, opts) {
  opts = opts || {};
  const method = (opts.method || 'GET').toUpperCase();
  if (method === 'POST') {
    const token = await ensureCsrf();
    opts.headers = Object.assign({}, opts.headers, {'X-CSRF-Token': token});
    let r = await _realFetch(url, opts);
    if (r.status === 403) {
      csrfToken = null;
      const token2 = await ensureCsrf();
      opts.headers = Object.assign({}, opts.headers, {'X-CSRF-Token': token2});
      r = await _realFetch(url, opts);
    }
    if (r.status === 401) showLoginForm();
    return r;
  }
  const r = await _realFetch(url, opts);
  if (r.status === 401) showLoginForm();
  return r;
};
function showLoginForm() {
  document.getElementById('loginCard').style.display = 'block';
}
function markDirty() {
  dirty = true;
  const n = document.getElementById('dirtyNote');
  if (n) n.style.display = 'block';
}
function clearDirty() {
  dirty = false;
  const n = document.getElementById('dirtyNote');
  if (n) n.style.display = 'none';
}
document.addEventListener('input', function(e) {
  const t = e.target;
  if (!t || !t.id) return;
  if (['productSearch', 'setName', 'loginPassword', 'productId'].indexOf(t.id) !== -1) return;
  if (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA') markDirty();
});
document.addEventListener('change', function(e) {
  const t = e.target;
  if (!t || !t.id) return;
  if (['productSearch', 'setName', 'loginPassword', 'productId'].indexOf(t.id) !== -1) return;
  if (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA') markDirty();
});
async function checkAuth() {
  try {
    const r = await fetch('/api/auth-status');
    const j = await r.json();
    if (!j.password_configured) {
      document.getElementById('authBannerText').textContent = 'Warning: no app password is set, so anyone with this link can edit sets. Set SET_APP_PASSWORD on the server.';
      document.getElementById('authBanner').style.display = 'block';
    } else if (!j.authenticated) {
      showLoginForm();
    }
  } catch (e) {}
}
async function doLogin() {
  const pw = document.getElementById('loginPassword').value;
  const box = document.getElementById('loginResult');
  try {
    const r = await fetch('/api/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ password: pw }) });
    const j = await r.json();
    if (!r.ok) { box.innerHTML = '<p class="warn">' + esc(j.error || 'Login failed.') + '</p>'; return; }
    document.getElementById('loginCard').style.display = 'none';
    document.getElementById('loginPassword').value = '';
    loadSetList();
    loadCatalogTemplates();
  } catch (e) { box.innerHTML = '<p class="warn">Login failed. Try again.</p>'; }
}
async function doLogout() {
  try { await fetch('/api/logout', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) }); } catch (e) {}
  currentSet = null;
  showLoginForm();
}
function downloadSetJson() {
  if (!currentSet) return alert('Open a set first.');
  const blob = new Blob([JSON.stringify(currentSet, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = currentSet.id + '.json';
  a.click();
  URL.revokeObjectURL(a.href);
}
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function safeId(pid) { return String(pid).replace(/[^A-Za-z0-9]/g, '_'); }
function updateCurrentSetLine() {
  const line = document.getElementById('currentSetLine');
  const top = document.getElementById('topSetName');
  const ph = document.getElementById('productsHeader');
  if (!currentSet) {
    if (line) line.innerHTML = '<small>No set selected yet.</small>';
    if (top) top.textContent = 'No set open';
    if (ph) ph.textContent = 'PRODUCTS (0)';
    return;
  }
  const n = currentSet.products.length;
  if (line) line.innerHTML = '<small>Open: <b>' + esc(currentSet.name) + '</b> (' + n + (n === 1 ? ' product' : ' products') + ')</small>';
  if (top) top.textContent = currentSet.name || 'Untitled set';
  if (ph) ph.textContent = 'PRODUCTS (' + n + ')';
}
function syncCache() {
  if (!currentSet) return;
  for (let i = 0; i < allSets.length; i++) {
    if (allSets[i].id === currentSet.id) { allSets[i] = currentSet; break; }
  }
}
function campaignOf(s) { return (s && s.campaign) || {}; }
function renderSetList() {
  const tbody = document.getElementById('campaignsTbody');
  const box = document.getElementById('campaignsList');
  const q = (document.getElementById('campaignFilter') ? document.getElementById('campaignFilter').value : '').trim().toLowerCase();
  const rows = allSets.filter(function(s) {
    if (!q) return true;
    const hay = ((s.name || '') + ' /' + (s.slug || '') + ' ' + (s.tags || []).join(' ')).toLowerCase();
    return hay.indexOf(q) !== -1;
  });
  if (tbody) {
    if (!rows.length) { tbody.innerHTML = '<tr><td colspan="9"><small>No campaigns yet. Create one above.</small></td></tr>'; return; }
    tbody.innerHTML = rows.map(function(s) {
      const n = s.products.length;
      const camp = campaignOf(s);
      const status = camp.status || 'draft';
      const pillCls = status === 'active' ? 'pill active' : status === 'inactive' ? 'pill inactive' : status === 'locked' ? 'pill locked' : 'pill';
      const first = s.products[0];
      const art = s.design_url || (first && (first.hero_image || (first.mockups && first.mockups[0]) || (first.images && first.images[0]) || first.image)) || '';
      const artHtml = art ? '<img class="thumb" src="' + esc(art) + '" alt="">' : '<span class="thumb" style="display:inline-block"></span>';
      return '<tr><td><input type="checkbox" class="campaignCheck" value="' + esc(s.id) + '"></td>'
        + '<td>' + artHtml + '</td>'
        + '<td class="wrap"><a href="/campaigns/' + esc(s.id) + '">' + esc(s.name) + '</a><br><a href="/campaigns/' + esc(s.id) + '/designer">Designer</a></td>'
        + '<td>/' + esc(s.slug || '') + '</td>'
        + '<td class="wrap">' + esc((s.tags || []).join(', ') || '-') + '</td>'
        + '<td>-</td><td>' + n + '</td>'
        + '<td><span class="' + pillCls + '">' + esc(status.toUpperCase()) + '</span></td>'
        + '<td>' + esc(camp.fulfillment || 'LAUNCH_END') + '</td>'
        + '<td>' + esc(camp.end_date || '-') + '</td></tr>';
    }).join('');
    return;
  }
  if (!box) return;
  if (!rows.length) { box.innerHTML = '<small>No campaigns yet. Create one above.</small>'; return; }
  box.innerHTML = rows.map(function(s) {
    return '<div><b>' + esc(s.name) + '</b></div>';
  }).join('');
}
function checkedCampaignIds() {
  const ids = [];
  document.querySelectorAll('.campaignCheck').forEach(function(cb) { if (cb.checked) ids.push(cb.value); });
  return ids;
}
async function createCampaign() {
  const name = document.getElementById('campaignName').value.trim();
  if (!name) return alert('Type a campaign name first.');
  const slugEl = document.getElementById('campaignSlug');
  const slug = slugEl ? slugEl.value.trim() : slugify(name);
  try {
    const r = await fetch('/api/campaigns', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name: name, slug: slug }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Create campaign failed.');
    document.getElementById('campaignName').value = '';
    allSets.push(j);
    if (document.getElementById('campaignsTbody')) { window.location.href = '/campaigns/' + j.id; return; }
    selectSet(j.id);
  } catch (e) { alert(e.message); }
}
async function bulkCampaign(action) {
  const ids = checkedCampaignIds();
  if (!ids.length) return alert('Tick at least one campaign first.');
  let body = { action: action, ids: ids };
  if (action === 'tag') {
    const tag = document.getElementById('bulkTag').value.trim();
    if (!tag) return alert('Type a tag first.');
    body.tag = tag;
  }
  if (action === 'delete' && !confirm('Delete the selected campaigns? This cannot be undone.')) return;
  try {
    const r = await fetch('/api/sets/bulk-campaign', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Bulk action failed.');
    if (currentSet && ids.indexOf(currentSet.id) !== -1 && action === 'delete') {
      currentSet = null; selectedPid = null;
      updateCurrentSetLine();
    }
    await loadSetList();
    if (j.skipped && j.skipped.length) alert('Skipped locked campaigns: ' + j.skipped.join(', '));
  } catch (e) { alert(e.message); }
}
function openCampaignSettings(id) {
  window.location.href = '/campaigns/' + id;
}
function scrollToDesigner() {
  if (currentSet) window.location.href = '/campaigns/' + currentSet.id + '/designer';
}
function fillCampaignSettings() {
  if (!currentSet) return;
  // Settings fields live ONLY on the settings page. On the designer
  // page (which also calls this via refreshAfterSet) there are no
  // camp* elements, so skip instead of throwing on a null element
  // and aborting the rest of the designer render.
  if (!document.getElementById('campStorefrontHomepage')) return;
  const c = campaignOf(currentSet);
  const nameEl = document.getElementById('campName');
  if (nameEl) nameEl.value = currentSet.name || '';
  const slugEl = document.getElementById('campSlug');
  if (slugEl) slugEl.value = currentSet.slug || '';
  const tagsEl = document.getElementById('campTags');
  if (tagsEl) tagsEl.value = (currentSet.tags || []).join(', ');
  const hdr = document.getElementById('campHeaderName');
  if (hdr) hdr.textContent = currentSet.name || 'Untitled campaign';
  const pill = document.getElementById('campStatusPill');
  if (pill) pill.textContent = (c.status || 'draft').toUpperCase();
  const fb = c.facebook || {};
  document.getElementById('campStorefrontHomepage').checked = !!c.storefront_homepage;
  document.getElementById('campShowCountdown').checked = !!c.show_countdown;
  document.getElementById('campHidePurchases').checked = !!c.hide_purchases;
  document.getElementById('campFudge').value = (c.fudge_factor === undefined || c.fudge_factor === null) ? 0 : c.fudge_factor;
  document.getElementById('campHideSearch').checked = !!c.hide_from_search_engines;
  document.getElementById('campSocialButtons').checked = !!c.social_buttons;
  document.getElementById('campUpsell').value = (c.upsell_discount === undefined || c.upsell_discount === null) ? '' : c.upsell_discount;
  // Pixel + End fields were removed from settings (Ovi 2026-11-03
  // 22:43). Old values stay in stored data and are tolerated by the
  // server, but the UI neither shows nor sends them.
  document.getElementById('campDesc').value = currentSet.description || '';
  document.getElementById('campUrlPreview').textContent = 'fansfit.shop/' + (currentSet.slug || '');
  bindSlugAuto();
}
async function saveCampaignSettings() {
  if (!currentSet) return alert('Open a campaign first.');
  if (!document.getElementById('campDesc')) return alert('Campaign settings are on the settings page.');
  const nameEl = document.getElementById('campName') || document.getElementById('detailName');
  const slugEl = document.getElementById('campSlug') || document.getElementById('detailSlug');
  const tagsEl = document.getElementById('campTags') || document.getElementById('detailTags');
  const body = {
    name: nameEl ? nameEl.value.trim() : currentSet.name,
    slug: slugEl ? slugEl.value.trim() : currentSet.slug,
    description: document.getElementById('campDesc').value,
    tags: tagsEl ? tagsEl.value.trim() : '',
    campaign: {
      storefront_homepage: document.getElementById('campStorefrontHomepage').checked,
      show_countdown: document.getElementById('campShowCountdown').checked,
      hide_purchases: document.getElementById('campHidePurchases').checked,
      fudge_factor: document.getElementById('campFudge').value.trim(),
      hide_from_search_engines: document.getElementById('campHideSearch').checked,
      social_buttons: document.getElementById('campSocialButtons').checked,
      upsell_discount: document.getElementById('campUpsell').value.trim()
      // Pixel + End fields removed from settings: not sent.
    }
  };
  try {
    const j = await postSet('/campaign', body);
    currentSet.name = j.name;
    currentSet.slug = j.slug;
    currentSet.tags = j.tags;
    currentSet.description = j.description;
    currentSet.campaign = j.campaign;
    syncCache(); updateCurrentSetLine(); renderSetList(); fillDetails(); fillCampaignSettings(); clearDirty();
    document.getElementById('campaignSettingsResult').innerHTML = '<p class="ok">Campaign settings saved.</p>';
  } catch (e) { alert(e.message); }
}
function useHowToOrder() {
  const d = document.getElementById('campDesc');
  if (!d) return;
  d.value = 'How To Order:\nSelect Product Color/Size\nClick "Add To Cart"\nClick "Secure Checkout" and Enter Shipping & Billing Information.\n100% Printed and Made in the USA - Shipping Worldwide!\nEnjoy a 100% Secure Checkout experience.';
  markDirty();
}
async function duplicateSet(id) {
  try {
    const r = await fetch('/api/sets/' + id + '/duplicate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Duplicate failed.');
    allSets.push(j);
    if (document.getElementById('campaignsTbody')) { await loadSetList(); return; }
    selectSet(j.id);
  } catch (e) { alert(e.message); }
}
async function deleteSet(id) {
  if (!confirm('Delete this set? This cannot be undone.')) return;
  try {
    const r = await fetch('/api/sets/' + id + '/delete', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Delete failed.');
    allSets = allSets.filter(function(s) { return s.id !== id; });
    if (currentSet && currentSet.id === id) {
      currentSet = null;
      selectedPid = null;
      updateCurrentSetLine();
      const pr = document.getElementById('products'); if (pr) pr.innerHTML = '<small>No set selected yet. Create a set first.</small>';
    }
    renderSetList();
    updateCurrentSetLine();
    if (document.getElementById('campHeaderName')) { window.location.href = '/campaigns'; return; }
  } catch (e) { alert(e.message); }
}
async function loadSetList() {
  const box = document.getElementById('campaignsList');
  const tbody = document.getElementById('campaignsTbody');
  let r;
  try {
    r = await fetch('/api/sets');
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="9"><small>Could not load sets. Check connection and reload.</small></td></tr>';
    else if (box) box.innerHTML = '<small>Could not load sets. Check connection and reload.</small>';
    return;
  }
  if (!r.ok) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="9"><small>Could not load sets. Reload and try again.</small></td></tr>';
    else if (box) box.innerHTML = '<small>Could not load sets. Reload and try again.</small>';
    return;
  }
  allSets = await r.json();
  renderSetList();
}
async function loadSetById(id) {
  const r = await fetch('/api/sets');
  if (!r.ok) throw new Error('Could not load sets.');
  allSets = await r.json();
  const found = allSets.filter(function(s) { return s.id === id; })[0];
  if (!found) throw new Error('Campaign not found.');
  currentSet = found;
  selectedPid = (found.products[0] && found.products[0].product_id) || null;
  return found;
}
function selectedProduct() {
  if (!currentSet) return null;
  const found = currentSet.products.filter(function(p) { return p.product_id === selectedPid; })[0];
  return found || currentSet.products[0] || null;
}
function effectivePlacementOf(p) {
  if (p && !p.locked && p.override_placement) return p.override_placement;
  return (currentSet && currentSet.master_placement) || { x: 0.5, y: 0.45, scale: 0.5, angle: 0 };
}
function selectSet(id) {
  if (dirty && currentSet && currentSet.id !== id) {
    if (!confirm('Switch set without saving? Unsaved changes will be lost.')) return;
  }
  const found = allSets.filter(function(s) { return s.id === id; })[0];
  if (!found) return;
  currentSet = found;
  selectedPid = (found.products[0] && found.products[0].product_id) || null;
  const mp = currentSet.master_placement || {};
  const setVal = function(id, v) { const e = document.getElementById(id); if (e) e.value = v; };
  setVal('x', (mp.x === undefined ? 0.5 : mp.x));
  setVal('y', (mp.y === undefined ? 0.45 : mp.y));
  setVal('s', (mp.scale === undefined ? 0.5 : mp.scale));
  setVal('angle', (mp.angle === undefined ? 0 : mp.angle));
  setVal('layerX', (mp.x === undefined ? 0.5 : mp.x));
  setVal('layerY', (mp.y === undefined ? 0.47 : mp.y));
  const lx = document.getElementById('layerX'); if (lx) document.getElementById('layerXVal').textContent = (+lx.value).toFixed(2);
  const ly = document.getElementById('layerY'); if (ly) document.getElementById('layerYVal').textContent = (+ly.value).toFixed(2);
  showVals();
  clearDirty();
  updateCurrentSetLine();
  renderSetList();
  renderProducts();
  fillDetails();
  fillCampaignSettings();
  renderVariantCount();
  renderPublishStatus();
  renderDraftLine();
  renderCentreMockup();
  renderArtworkSpec();
  renderLayers();
  const ps = document.getElementById('productSearch'); if (ps && ps.value.trim().length >= 2) searchProducts();
}
function designSizeAppliesText() {
  const sel = selectedProduct();
  if (!sel) return '';
  return sel.locked ? 'Locked: follows master' : 'Unlocked: this product only';
}
function syncDesignSize() {
  const el = document.getElementById('designSize');
  if (!el) return;
  const sel = selectedProduct();
  const pl = clampPlacement(effectivePlacementOf(sel));
  if (document.activeElement !== el) el.value = pl.scale.toFixed(2);
  const val = document.getElementById('designSizeVal');
  if (val) val.textContent = Math.round((pl.scale / PRINT_AREA.width) * 100) + '% of print area';
  const ap = document.getElementById('designSizeApplies');
  if (ap) ap.textContent = designSizeAppliesText();
  // Review blockers B1/B2: the master slider #s must ONLY follow the
  // master placement. Syncing it from an unlocked override corrupted
  // the master on the next Save (B2). For an unlocked product, sync
  // the per-product sliders instead, so "Save placement for this
  // product" POSTs the Design-size value rather than a stale one (B1).
  if (sel && !sel.locked) {
    const sid = safeId(sel.product_id);
    const syncOne = function(id, v) {
      const e = document.getElementById(id);
      if (e && document.activeElement !== e) e.value = v;
    };
    syncOne('px-' + sid, pl.x.toFixed(2));
    syncOne('py-' + sid, pl.y.toFixed(2));
    syncOne('ps-' + sid, pl.scale.toFixed(2));
    syncOne('pa-' + sid, (pl.angle || 0).toFixed(0));
  } else {
    const sEl = document.getElementById('s');
    if (sEl && document.activeElement !== sEl) sEl.value = pl.scale.toFixed(2);
  }
}
function setDesignSize(scale) {
  if (!currentSet) return;
  const clamped = clampPlacement({ scale: scale });
  const sel = selectedProduct();
  if (sel && !sel.locked) {
    const base = clampPlacement(effectivePlacementOf(sel));
    sel.override_placement = { x: base.x, y: base.y, scale: clamped.scale, angle: base.angle };
  } else {
    currentSet.master_placement = currentSet.master_placement || { x: 0.5, y: 0.45, scale: 0.5, angle: 0 };
    currentSet.master_placement.scale = clamped.scale;
  }
  markDirty();
  syncDesignSize();
  positionPlaceBox();
}
function onDesignSizeInput(ev) {
  setDesignSize(+ev.target.value);
}
function liveProductPlacement(pid) {
  // Per-product sliders live-update the preview too (previously they
  // only took effect on Save, and only for unlocked products).
  if (!currentSet) return;
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  if (!p || p.locked) return;
  const sid = safeId(pid);
  const get = function(id) { const e = document.getElementById(id); return e ? +e.value : undefined; };
  const pl = clampPlacement({
    x: get('px-' + sid), y: get('py-' + sid),
    scale: get('ps-' + sid), angle: get('pa-' + sid)
  });
  p.override_placement = pl;
  markDirty();
  syncDesignSize();
  positionPlaceBox();
}
function showVals() {
  const setTxt = function(id, el, fmt) { const t = document.getElementById(id); const e = document.getElementById(el); if (t && e) t.textContent = fmt(+e.value); };
  setTxt('xVal', 'x', function(v) { return v.toFixed(2); });
  setTxt('yVal', 'y', function(v) { return v.toFixed(2); });
  setTxt('sVal', 's', function(v) { return v.toFixed(2); });
  setTxt('angleVal', 'angle', function(v) { return v.toFixed(0); });
  // Master sliders live-preview: write their values into the in-memory
  // master placement so positionPlaceBox reflects them at once, without
  // waiting for Save. Save still persists them via saveMaster/saveAll.
  // Unlocked products are unaffected here: their preview uses the
  // override, not the master, and the Design size slider shows that.
  if (currentSet) {
    const xv = document.getElementById('x'); const yv = document.getElementById('y');
    const sv = document.getElementById('s'); const av = document.getElementById('angle');
    if (xv || yv || sv || av) {
      const mp = currentSet.master_placement || { x: 0.5, y: 0.45, scale: 0.5, angle: 0 };
      currentSet.master_placement = clampPlacement({
        x: xv ? +xv.value : mp.x, y: yv ? +yv.value : mp.y,
        scale: sv ? +sv.value : mp.scale, angle: av ? +av.value : mp.angle
      });
    }
  }
  positionPlaceBox();
  syncDesignSize();
}
async function createSet() {
  const nameEl = document.getElementById('setName');
  if (!nameEl) return alert('Create a campaign from the Campaigns page.');
  const name = nameEl.value.trim();
  if (!name) return alert('Type a set name first.');
  const r = await fetch('/api/sets', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
  currentSet = await r.json();
  const setsEl = document.getElementById('sets'); if (setsEl) setsEl.innerHTML = '<p>Set created: <b>' + currentSet.name + '</b></p>';
  allSets.push(currentSet);
  selectedPid = null;
  updateCurrentSetLine();
  renderSetList();
  renderProducts();
  fillDetails();
  fillCampaignSettings();
  renderVariantCount();
  renderPublishStatus();
  renderDraftLine();
  renderCentreMockup();
  renderArtworkSpec();
  renderLayers();
}
function variantCountOf(p) {
  const c = (p.colours || []).length, s = (p.sizes || []).length;
  return (c && s) ? (c * s) : null;
}
function money(v) {
  if (v === undefined || v === null || v === '') return 'not set';
  return (+v).toFixed(2);
}
const COLOR_HEX = {
  black: '#111111', white: '#f5f5f5', navy: '#1f3864', red: '#c00000',
  royal: '#274e9d', gold: '#d4af37', 'irish green': '#0e7a3e',
  'kelly green': '#1fae5f', 'forest green': '#1e5631', orange: '#ed7d31',
  purple: '#7030a0', 'sport grey': '#8a8d93', grey: '#8a8d93',
  'cardinal red': '#9e1b32', 'carolina blue': '#7fb3d5', 'light blue': '#a9cce3',
  'light pink': '#f5c6d6', maroon: '#800000', 'dark heather': '#5d6d7e',
  'dark chocolate': '#3e2723', 'safety green': '#a8d08d', ash: '#c9c9c9',
  'athletic heather': '#9aa0a6', sand: '#e6d3b3', asphalt: '#2f2f2f',
  'dark grey heather': '#6b7280', 'deep heather': '#4b5563',
  'heather true royal': '#3b5bb5', 'team purple': '#5b2c8a', 'true royal': '#2b4c9b'
};
function swatchHex(name) {
  const key = String(name).toLowerCase().trim();
  return COLOR_HEX[key] || '#cccccc';
}
function productThumb(p) {
  const url = (p.mockups && p.mockups[0]) || p.hero_image || (p.images && p.images[0]) || p.image || '';
  if (!url) return '<span class="thumb" style="display:inline-block"></span>';
  return '<img class="thumb" src="' + esc(url) + '" alt="">';
}
function priceRangeOf(p) {
  const prices = [];
  const vp = p.variant_prices || {};
  Object.keys(vp).forEach(function(k) {
    const n = parseFloat(vp[k]);
    if (!isNaN(n)) prices.push(n);
  });
  if (!prices.length) return null;
  const lo = Math.min.apply(null, prices), hi = Math.max.apply(null, prices);
  return lo === hi ? lo.toFixed(2) : lo.toFixed(2) + ' to ' + hi.toFixed(2);
}
function mockupIsCurrent(p) {
  if (!currentSet) return true;
  const dv = currentSet.design_version === undefined ? 1 : currentSet.design_version;
  const mockups = p.mockups || [];
  const display = (p.hero_image && mockups.indexOf(p.hero_image) !== -1) ? p.hero_image : (mockups[0] || null);
  if (!display) return true;
  if (display.indexOf('/static/mockups/') !== 0) return true;
  const versions = p.mockup_versions || {};
  if (versions[display] === dv) return true;
  return p.mockup_version === dv;
}
function renderProducts() {
  const box = document.getElementById('products');
  if (!box) return;
  if (!currentSet) { box.innerHTML = '<small>No set selected yet. Create a set first.</small>'; return; }
  if (!currentSet.products.length) { box.innerHTML = '<small>No products in this set yet. Add one below.</small>'; return; }
  box.innerHTML = currentSet.products.map(function(p) {
    const sid = safeId(p.product_id);
    const isSel = selectedPid === p.product_id || (!selectedPid && currentSet.products[0] === p);
    const action = p.locked ? 'Unlock' : 'Lock';
    const title = esc(p.title || p.product_id);
    const badge = p.kind === 'catalog' ? ' <span class="badge">Catalog template, not a store product yet</span>' : '';
    const vc = variantCountOf(p);
    const range = priceRangeOf(p);
    let priceLine;
    if (p.sale_price !== undefined && p.sale_price !== null && p.sale_price !== '') {
      priceLine = '<small>Selling price: ' + money(p.sale_price) + ' | Unit cost: ' + money(p.base_cost) + '</small>';
      if (range) priceLine += '<br><small class="warn">This replaces the store\'s per-variant prices for all variants.</small>';
    } else if (range) {
      priceLine = '<small>Price: ' + range + ' (from the store listing) | Unit cost: ' + money(p.base_cost) + '</small>';
    } else {
      priceLine = '<small>Selling price: not set | Unit cost: ' + money(p.base_cost) + '</small>';
    }
    const defaultColor = esc(p.default_color || (p.colours && p.colours[0]) || 'not set');
    const position = p.position || 'front';
    const positionRadios = '<div onclick="event.stopPropagation()"><small>Position: </small>'
      + '<label><input type="radio" name="pos-' + sid + '" value="front"' + (position === 'front' ? ' checked' : '') + ' onchange="savePosition(\'' + esc(p.product_id) + '\', \'front\')"> Front</label> '
      + '<label><input type="radio" name="pos-' + sid + '" value="back"' + (position === 'back' ? ' checked' : '') + ' onchange="savePosition(\'' + esc(p.product_id) + '\', \'back\')"> Back</label>'
      + (position === 'back' ? '<br><small>Back side is not printed in this app yet. FRONT is the working side.</small>' : '') + '</div>';
    const swatches = (p.colours || []).map(function(c) {
      return '<span class="swatch" title="' + esc(c) + '" style="background:' + swatchHex(c) + ';cursor:pointer" onclick="event.stopPropagation();openPickColors(\'' + esc(p.product_id) + '\')"></span>';
    }).join('');
    const colourOpts = p.all_colours || p.colours || [];
    const sizeOpts = p.all_sizes || p.sizes || [];
    const colourChips = colourOpts.map(function(c) {
      const checked = (p.colours || []).indexOf(c) !== -1 ? ' checked' : '';
      return '<label><input type="checkbox" data-prod="' + esc(p.product_id) + '" data-kind="colour" value="' + esc(c) + '"' + checked + '> ' + esc(c) + '</label>';
    }).join('');
    const sizeChips = sizeOpts.map(function(s) {
      const checked = (p.sizes || []).indexOf(s) !== -1 ? ' checked' : '';
      return '<label><input type="checkbox" data-prod="' + esc(p.product_id) + '" data-kind="size" value="' + esc(s) + '"' + checked + '> ' + esc(s) + '</label>';
    }).join('');
    const mockups = [];
    (p.mockups || []).forEach(function(u) { if (mockups.indexOf(u) === -1) mockups.push(u); });
    if (p.hero_image && mockups.indexOf(p.hero_image) === -1) mockups.push(p.hero_image);
    if (p.image && mockups.indexOf(p.image) === -1) mockups.push(p.image);
    (p.images || []).forEach(function(u) { if (mockups.indexOf(u) === -1) mockups.push(u); });
    const heroOpts = mockups.map(function(u) {
      const sel = p.hero_image === u ? ' selected' : '';
      return '<option value="' + esc(u) + '"' + sel + '>' + esc(u.split('/').pop()) + '</option>';
    }).join('');
    const reorderRows = (p.mockups || []).map(function(u, i) {
      return '<div class="layerrow"><span><small>' + esc(u.split('/').pop()) + '</small></span>'
        + '<button class="secondary" onclick="reorderMockup(\'' + esc(p.product_id) + '\', ' + i + ', -1)">Up</button>'
        + '<button class="secondary" onclick="reorderMockup(\'' + esc(p.product_id) + '\', ' + i + ', 1)">Down</button></div>';
    }).join('');
    const reorderBlock = ((p.mockups || []).length >= 2)
      ? '<div><h3>Mockup order</h3><p><small>Hero is the first Shopify image by definition; reorder changes the rest.</small></p>' + reorderRows + '</div>'
      : '';
    const staleNote = (!mockupIsCurrent(p))
      ? '<p><span class="warn">Mockup outdated: tap Preview mockup again before publishing.</span></p>' : '';
    const defColOpts = (p.colours || []).map(function(c) {
      const sel = (p.default_color || p.colours[0]) === c ? ' selected' : '';
      return '<option value="' + esc(c) + '"' + sel + '>' + esc(c) + '</option>';
    }).join('');
    const refreshBtn = p.kind === 'catalog' ? '' : '<button class="secondary" onclick="refreshProduct(\'' + esc(p.product_id) + '\')">Refresh from Shopify</button>';
    let placementBlock = '';
    if (!p.locked) {
      const pl = p.override_placement || effectivePlacementOf(p);
      placementBlock = '<div onclick="event.stopPropagation()"><h3>This product\'s placement</h3>'
        + '<label>Left / right</label><input type="range" id="px-' + sid + '" min="0" max="1" step="0.01" value="' + (pl.x === undefined ? 0.5 : pl.x) + '" oninput="liveProductPlacement(\'' + esc(p.product_id) + '\')">'
        + '<label>Up / down</label><input type="range" id="py-' + sid + '" min="0" max="1" step="0.01" value="' + (pl.y === undefined ? 0.45 : pl.y) + '" oninput="liveProductPlacement(\'' + esc(p.product_id) + '\')">'
        + '<label>Size</label><input type="range" id="ps-' + sid + '" min="0.1" max="0.5" step="0.01" value="' + (pl.scale === undefined ? 0.5 : pl.scale) + '" oninput="liveProductPlacement(\'' + esc(p.product_id) + '\')">'
        + '<label>Angle</label><input type="range" id="pa-' + sid + '" min="-180" max="180" step="1" value="' + (pl.angle === undefined ? 0 : pl.angle) + '" oninput="liveProductPlacement(\'' + esc(p.product_id) + '\')">'
        + '<button class="secondary" onclick="saveProductPlacement(\'' + esc(p.product_id) + '\')">Save placement for this product</button></div>';
    }
    return '<div class="prodcard' + (isSel ? ' selected' : '') + '" onclick="selectProduct(\'' + esc(p.product_id) + '\')">'
      + '<div style="display:flex;gap:10px;align-items:flex-start">' + productThumb(p)
      + '<div style="flex:1;min-width:0"><b style="overflow-wrap:anywhere">' + title + '</b>' + badge
      + '<br>' + priceLine
      + '<br><small>Default color: ' + defaultColor + ' | ' + (p.locked ? 'Locked' : 'Unlocked') + ' | Variants: ' + (vc === null ? 'not set' : vc) + '</small>'
      + '<div class="swatches">' + swatches + '</div>' + positionRadios + '</div>'
      + '<button class="secondary" onclick="event.stopPropagation();removeProduct(\'' + esc(p.product_id) + '\')">Remove product</button></div>'
      + staleNote
      + '<div class="row" onclick="event.stopPropagation()"><button class="secondary" onclick="selectAllColours(\'' + esc(p.product_id) + '\')">Colours: Select all</button><button class="secondary" onclick="clearColours(\'' + esc(p.product_id) + '\')">Colours: Clear</button><button class="secondary" onclick="selectAllSizes(\'' + esc(p.product_id) + '\')">Sizes: Select all</button><button class="secondary" onclick="clearSizes(\'' + esc(p.product_id) + '\')">Sizes: Clear</button></div>'
      + '<div class="row" onclick="event.stopPropagation()"><button class="secondary" onclick="toggleLock(\'' + esc(p.product_id) + '\', ' + p.locked + ')">' + action + '</button>'
      + '<button class="secondary" onclick="previewMockup(\'' + esc(p.product_id) + '\')">Preview mockup</button></div>'
      + '<div id="preview-' + sid + '"></div>'
      + placementBlock
      + '<div onclick="event.stopPropagation()"><button class="secondary" onclick="openPickColors(\'' + esc(p.product_id) + '\')">Pick colors</button></div>'
      + '<details onclick="event.stopPropagation()"><summary>Sizes + price</summary>'
      + '<p><small>Sizes (tick to include):</small></p><div class="chips">' + sizeChips + '</div>'
      + '<button class="secondary" onclick="saveVariants(\'' + esc(p.product_id) + '\')">Save sizes</button>'
      + '<label>Default color</label><select id="defcol-' + sid + '" onchange="saveDefaultColor(\'' + esc(p.product_id) + '\')">' + defColOpts + '</select>'
      + '<label>Sale price</label><input id="sale-' + sid + '" inputmode="decimal" placeholder="e.g. 27.99" value="' + (p.sale_price === undefined || p.sale_price === null ? '' : esc(p.sale_price)) + '">'
      + '<label>Compare-at price (optional, must be higher than sale)</label><input id="cmp-' + sid + '" inputmode="decimal" placeholder="e.g. 34.99" value="' + (p.compare_at_price === undefined || p.compare_at_price === null ? '' : esc(p.compare_at_price)) + '">'
      + '<label>Base cost</label><input id="cost-' + sid + '" inputmode="decimal" placeholder="e.g. 12.50" value="' + (p.base_cost === undefined || p.base_cost === null ? '' : esc(p.base_cost)) + '">'
      + '<button class="secondary" onclick="savePricing(\'' + esc(p.product_id) + '\')">Save price</button>'
      + '<div id="priceResult-' + sid + '"></div>' + refreshBtn + '</details>'
      + (mockups.length ? '<details onclick="event.stopPropagation()"><summary>Mockups + hero</summary><label>Main image for the listing</label><select id="hero-' + sid + '">' + heroOpts + '</select><button class="secondary" onclick="saveHero(\'' + esc(p.product_id) + '\')">Save hero</button></details>' : '')
      + reorderBlock
      + '</div>';
  }).join('');
}
async function postSet(path, body) {
  const r = await fetch('/api/sets/' + currentSet.id + path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(function(){ return {}; });
  if (!r.ok) throw new Error(j.error || ('Request failed (' + r.status + ')'));
  return j;
}
function refreshAfterSet(j) {
  currentSet = j.set || j;
  syncCache(); updateCurrentSetLine(); renderSetList(); renderProducts();
  fillDetails(); fillCampaignSettings();
  renderVariantCount(); renderPublishStatus(); renderDraftLine();
  renderCentreMockup(); renderArtworkSpec(); renderLayers();
  clearDirty();
}
async function refreshSelectedProduct() {
  const p = selectedProduct();
  if (!p) return alert('Open a set with a product first.');
  try { const j = await postSet('/products/' + encodeURIComponent(p.product_id) + '/refresh', {}); refreshAfterSet(j); }
  catch (e) { alert(e.message); }
}
async function savePosition(pid, position) {
  if (!currentSet) return;
  try { const j = await postSet('/products/' + encodeURIComponent(pid) + '/position', { position: position }); refreshAfterSet(j); }
  catch (e) { alert(e.message); }
}
let pickPid = null;
let pickColours = [];
let pickAllColours = [];
function openPickColors(pid) {
  if (!currentSet) return;
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  if (!p) return;
  pickPid = pid;
  pickAllColours = (p.all_colours && p.all_colours.length ? p.all_colours : p.colours || []).slice();
  pickColours = (p.colours || []).slice();
  document.getElementById('pickColorsTitle').textContent = 'Pick colors: ' + (p.title || pid);
  document.getElementById('pickColorsResult').innerHTML = '';
  renderPickColors();
  document.getElementById('pickColorsModal').style.display = 'block';
}
function renderPickColors() {
  const avail = document.getElementById('pickColorsAvailable');
  avail.innerHTML = pickAllColours.map(function(c) {
    const sel = pickColours.indexOf(c) !== -1;
    return '<button class="' + (sel ? 'sel' : 'secondary') + '" onclick="togglePickColor(\'' + esc(c) + '\')">' + (sel ? '✓ ' : '') + esc(c) + '</button>';
  }).join('');
  const selBox = document.getElementById('pickColorsSelected');
  if (!pickColours.length) { selBox.innerHTML = '<small>No colors selected yet.</small>'; }
  else {
    selBox.innerHTML = pickColours.map(function(c) {
      return '<span class="chipX">' + esc(c) + '<button class="secondary" onclick="togglePickColor(\'' + esc(c) + '\')">x</button></span>';
    }).join('');
  }
  const def = document.getElementById('pickColorsDefault');
  const cur = currentSet.products.filter(function(x) { return x.product_id === pickPid; })[0];
  const curDef = (cur && cur.default_color) || pickColours[0] || '';
  def.innerHTML = pickColours.map(function(c) {
    return '<option value="' + esc(c) + '"' + (c === curDef ? ' selected' : '') + '>' + esc(c) + '</option>';
  }).join('');
}
function togglePickColor(c) {
  const i = pickColours.indexOf(c);
  if (i === -1) pickColours.push(c); else pickColours.splice(i, 1);
  renderPickColors();
}
function pickColorsSelectAll() {
  pickColours = pickAllColours.slice();
  renderPickColors();
}
function closePickColors() {
  document.getElementById('pickColorsModal').style.display = 'none';
  pickPid = null;
}
async function savePickColors() {
  if (!currentSet || !pickPid) return;
  const def = document.getElementById('pickColorsDefault').value;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pickPid) + '/colors', { colours: pickColours, default_color: def });
    refreshAfterSet(j);
    closePickColors();
  } catch (e) { document.getElementById('pickColorsResult').innerHTML = '<p class="warn">' + esc(e.message) + '</p>'; }
}
async function saveAll() {
  if (!currentSet) return alert('Create a set first.');
  const products = (currentSet.products || []).map(function(p) {
    const sid = safeId(p.product_id);
    const colours = [], sizes = [];
    let colourBoxes = 0;
    document.querySelectorAll('input[data-prod="' + p.product_id + '"]').forEach(function(cb) {
      if (cb.getAttribute('data-kind') === 'colour') colourBoxes++;
      if (!cb.checked) return;
      if (cb.getAttribute('data-kind') === 'colour') colours.push(cb.value); else sizes.push(cb.value);
    });
    // Colours now live in the Pick colors modal and save immediately
    // through the API, so when no colour checkboxes are on the page,
    // keep the saved selection instead of wiping it to empty.
    const finalColours = colourBoxes ? colours : (p.colours || []).slice();
    const saleEl = document.getElementById('sale-' + sid);
    const cmpEl = document.getElementById('cmp-' + sid);
    const costEl = document.getElementById('cost-' + sid);
    return {
      product_id: p.product_id,
      colours: finalColours,
      sizes: sizes,
      sale_price: saleEl ? saleEl.value.trim() : '',
      compare_at_price: cmpEl ? cmpEl.value.trim() : '',
      base_cost: costEl ? costEl.value.trim() : '',
      // Unlocked overrides must travel with Save, or a drag on an
      // unlocked product is silently discarded by saveAll.
      override_placement: (!p.locked && p.override_placement) ? p.override_placement : undefined
    };
  });
  const val = function(id, fallback) { const e = document.getElementById(id); return e ? e.value.trim() : fallback; };
  const mp = currentSet.master_placement || {};
  const xv = document.getElementById('x'); const yv = document.getElementById('y'); const sv = document.getElementById('s'); const av = document.getElementById('angle');
  const body = {
    placement: clampPlacement({ x: xv ? +xv.value : mp.x, y: yv ? +yv.value : mp.y, scale: sv ? +sv.value : mp.scale, angle: av ? +av.value : mp.angle }),
    details: {
      name: val('detailName', currentSet.name || ''),
      slug: val('detailSlug', currentSet.slug || ''),
      description: val('detailDesc', currentSet.description || ''),
      tags: val('detailTags', (currentSet.tags || []).join(', ')),
      grouping: currentSet.grouping || 'combine'
    },
    products: products
  };
  try {
    const j = await postSet('/save-all', body);
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
function toggleSwatch(pid, colour) {
  // Kept for old callers: colour selection now lives in the
  // Pick colors modal, so a swatch tap opens that modal instead.
  openPickColors(pid);
}
async function saveDefaultColor(pid) {
  if (!currentSet) return;
  const sid = safeId(pid);
  const colour = document.getElementById('defcol-' + sid).value;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/default-color', { colour: colour });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function saveProductPlacement(pid) {
  if (!currentSet) return;
  const sid = safeId(pid);
  const placement = clampPlacement({
    x: +document.getElementById('px-' + sid).value,
    y: +document.getElementById('py-' + sid).value,
    scale: +document.getElementById('ps-' + sid).value,
    angle: +document.getElementById('pa-' + sid).value
  });
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/lock', { locked: false, placement: placement });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function refreshProduct(pid) {
  if (!currentSet) return;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/refresh', {});
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function saveVariants(pid) {
  if (!currentSet) return alert('Create a set first.');
  const sizes = [];
  document.querySelectorAll('input[data-prod="' + pid + '"]').forEach(function(cb) {
    if (cb.checked && cb.getAttribute('data-kind') === 'size') sizes.push(cb.value);
  });
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/variants', { sizes: sizes });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function selectAllColours(pid) {
  if (!currentSet) return;
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  if (!p) return;
  const all = (p.all_colours && p.all_colours.length ? p.all_colours : p.colours || []).slice();
  try { const j = await postSet('/products/' + encodeURIComponent(pid) + '/variants', { colours: all }); refreshAfterSet(j); }
  catch (e) { alert(e.message); }
}
async function clearColours(pid) {
  if (!currentSet) return;
  try { const j = await postSet('/products/' + encodeURIComponent(pid) + '/variants', { colours: [] }); refreshAfterSet(j); }
  catch (e) { alert(e.message); }
}
async function selectAllSizes(pid) {
  if (!currentSet) return;
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  if (!p) return;
  const all = (p.all_sizes && p.all_sizes.length ? p.all_sizes : p.sizes || []).slice();
  try { const j = await postSet('/products/' + encodeURIComponent(pid) + '/variants', { sizes: all }); refreshAfterSet(j); }
  catch (e) { alert(e.message); }
}
async function clearSizes(pid) {
  if (!currentSet) return;
  try { const j = await postSet('/products/' + encodeURIComponent(pid) + '/variants', { sizes: [] }); refreshAfterSet(j); }
  catch (e) { alert(e.message); }
}
async function savePricing(pid) {
  if (!currentSet) return alert('Create a set first.');
  const sid = safeId(pid);
  const body = {
    sale_price: document.getElementById('sale-' + sid).value.trim(),
    compare_at_price: document.getElementById('cmp-' + sid).value.trim(),
    base_cost: document.getElementById('cost-' + sid).value.trim()
  };
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/pricing', body);
    refreshAfterSet(j);
    document.getElementById('priceResult-' + sid).innerHTML = '<p class="ok">Price saved.</p>';
  } catch (e) { alert(e.message); }
}
async function saveHero(pid) {
  if (!currentSet) return alert('Create a set first.');
  const sid = safeId(pid);
  const image = document.getElementById('hero-' + sid).value;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/hero', { image: image });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function reorderMockup(pid, index, dir) {
  if (!currentSet) return alert('Create a set first.');
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  if (!p || !p.mockups) return;
  const order = p.mockups.slice();
  const to = index + dir;
  if (to < 0 || to >= order.length) return;
  const tmp = order[index]; order[index] = order[to]; order[to] = tmp;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/mockups/reorder', { order: order });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function removeProduct(pid) {
  if (!currentSet) return alert('Create a set first.');
  if (!confirm('Remove this product from the set?')) return;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/remove', {});
    if (selectedPid === pid) selectedPid = null;
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function previewMockup(pid) {
  if (!currentSet) return alert('Create a set first.');
  const sid = safeId(pid);
  const box = document.getElementById('preview-' + sid);
  box.innerHTML = '<small>Making preview...</small>';
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  let photo = '';
  // Prefer the BARE photo (never a rendered mockup) as render input.
  try {
    const pr = await fetch('/api/sets/' + currentSet.id + '/products/' + encodeURIComponent(pid) + '/photo?bare=1');
    const pj = await pr.json();
    if (pj.photo) photo = pj.photo;
  } catch (e) {}
  if (!photo) photo = (p && (p.image || (p.images || [])[0] || p._photo)) || '';
  if (!photo) {
    try {
      const pr = await fetch('/api/sets/' + currentSet.id + '/products/' + encodeURIComponent(pid) + '/photo');
      const pj = await pr.json();
      if (pj.photo) { photo = pj.photo; if (p) p._photo = photo; }
    } catch (e) {}
  }
  if (!photo) { box.innerHTML = '<small>No product photo to preview on.</small>'; return; }
  try {
    const body = { photos: {} };
    body.photos[pid] = photo;
    if (currentSet.design_url) body.design = currentSet.design_url;
    const r = await fetch('/api/sets/' + currentSet.id + '/mockups', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Preview failed.');
    if (j.errors && j.errors[pid]) throw new Error(j.errors[pid]);
    const url = j.mockups[pid];
    currentSet.products.forEach(function(x) { if (x.product_id === pid) { x.mockups = [url]; if (!x.hero_image) x.hero_image = url; } });
    box.innerHTML = '<small class="ok">Preview ready. See the Design panel above.</small>';
    selectedPid = pid;
    renderProducts();
    renderCentreMockup();
  } catch (e) { box.innerHTML = '<small>' + esc(e.message) + '</small>'; }
}
async function previewAllMockups() {
  if (!currentSet) return alert('Create a set first.');
  const box = document.getElementById('previewAllResult');
  box.innerHTML = '<small>Rendering every product...</small>';
  let ok = 0, fail = 0;
  const first = selectedPid;
  for (let i = 0; i < currentSet.products.length; i++) {
    const pid = currentSet.products[i].product_id;
    const before = document.getElementById('preview-' + safeId(pid));
    await previewMockup(pid);
    const txt = before ? before.textContent : '';
    if (txt.indexOf('Preview ready') !== -1) ok++; else fail++;
  }
  selectedPid = currentSet.products[0] ? currentSet.products[0].product_id : first;
  renderProducts();
  renderCentreMockup();
  box.innerHTML = '<p><small class="ok">' + ok + ' mockup(s) ready</small>' + (fail ? ' <span class="warn">' + fail + ' failed, see each product card</span>' : '') + '</p>';
}
let lastTouchAt = 0;
function placeAt(clientX, clientY) {
  if (!currentSet) return;
  const img = document.getElementById('centreImg');
  if (!img) return;
  const rect = img.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  // Fixed print area: the DESIGN moves, clamped inside the box.
  // The box itself never moves. On an UNLOCKED product the drag
  // moves that product's override placement, never the master:
  // writing to the master while an override is displayed silently
  // moved every locked product while the centre appeared unchanged.
  // A tap/drag must never reset the size: preserve the current scale
  // and angle (previously this forced scale 0.5, undoing any shrink).
  const sel0 = selectedProduct();
  const base0 = clampPlacement(effectivePlacementOf(sel0));
  const clamped = clampPlacement({ x: (clientX - rect.left) / rect.width,
                                   y: (clientY - rect.top) / rect.height,
                                   scale: base0.scale, angle: base0.angle });
  const x = clamped.x, y = clamped.y;
  const sel = selectedProduct();
  if (currentSet && sel && !sel.locked) {
    const base = clampPlacement(effectivePlacementOf(sel));
    sel.override_placement = { x: x, y: y, scale: base.scale, angle: base.angle };
    const sid = safeId(sel.product_id);
    const pxEl = document.getElementById('px-' + sid); if (pxEl) pxEl.value = x.toFixed(2);
    const pyEl = document.getElementById('py-' + sid); if (pyEl) pyEl.value = y.toFixed(2);
  } else {
    document.getElementById('x').value = x.toFixed(2);
    document.getElementById('y').value = y.toFixed(2);
    if (currentSet) {
      currentSet.master_placement = currentSet.master_placement || { x: 0.5, y: 0.45, scale: 0.5, angle: 0 };
      currentSet.master_placement.x = x;
      currentSet.master_placement.y = y;
    }
  }
  showVals();
  markDirty();
  positionPlaceBox();
}
function tapToPlace(ev) {
  // A tap already handled as a touch must not fire twice as a click.
  if (Date.now() - lastTouchAt < 500) return;
  placeAt(ev.clientX, ev.clientY);
}
let designDrag = null;
function bindCentreDrag() {
  const img = document.getElementById('centreImg');
  const box = document.getElementById('placeBox');
  if (!img || img._dragBound) return;
  img._dragBound = true;
  // Touch tap: place at the touch point, and suppress the click
  // that browsers fire after touchend.
  img.addEventListener('touchend', function(ev) {
    if (!ev.changedTouches || !ev.changedTouches.length) return;
    ev.preventDefault();
    lastTouchAt = Date.now();
    placeAt(ev.changedTouches[0].clientX, ev.changedTouches[0].clientY);
  }, { passive: false });
  img.addEventListener('touchstart', function() {
    lastTouchAt = Date.now();
  }, { passive: true });
  // Drag the DESIGN inside the fixed print area, by touch or mouse.
  // The print area box itself never moves. Pointerdown on the box
  // (which overlays the mockup, including the design image inside
  // it) starts a design drag; a tap without moving places the
  // design at that point; a drag moves it, clamped to the box.
  // The drag writes into the same master sliders that Save persists.
  if (box) {
    box.addEventListener('pointerdown', function(ev) {
      designDrag = { moved: false, startX: ev.clientX, startY: ev.clientY, x: ev.clientX, y: ev.clientY };
      if (box.setPointerCapture) { try { box.setPointerCapture(ev.pointerId); } catch (e) {} }
      ev.preventDefault();
    });
    box.addEventListener('pointermove', function(ev) {
      if (!designDrag) return;
      if (Math.abs(ev.clientX - designDrag.startX) +
          Math.abs(ev.clientY - designDrag.startY) > 4) designDrag.moved = true;
      if (designDrag.moved) placeAt(ev.clientX, ev.clientY);
    });
    const endDesignDrag = function(ev) {
      if (designDrag && !designDrag.moved && ev && ev.clientX !== undefined) placeAt(ev.clientX, ev.clientY);
      if (designDrag && designDrag.moved) lastTouchAt = Date.now();
      designDrag = null;
    };
    box.addEventListener('pointerup', endDesignDrag);
    box.addEventListener('pointercancel', function() { designDrag = null; });
  }
}
function aidCenterH() { document.getElementById('x').value = 0.5; showVals(); }
function aidCenterV() { document.getElementById('y').value = 0.5; showVals(); }
function aidScaleToFit() { document.getElementById('x').value = 0.5; document.getElementById('y').value = 0.45; document.getElementById('s').value = 0.5; showVals(); }
function selectProduct(pid) {
  selectedPid = pid;
  renderProducts();
  renderCentreMockup();
}
function setViewSide(side) {
  viewSide = side;
  document.getElementById('tabFront').className = side === 'front' ? 'active' : 'secondary';
  document.getElementById('tabBack').className = side === 'back' ? 'active' : 'secondary';
  document.getElementById('backNote').style.display = side === 'back' ? 'block' : 'none';
  renderCentreMockup();
}
function centreImageUrl(p) {
  // Gearlaunch-style base: a flat Printify product photo when a
  // template matches this product type, otherwise the BARE store
  // photo. Never a rendered mockup: one already has a design
  // printed on it, so using it stacks a new design on the old one.
  if (!p) return '';
  if (p.kind === 'catalog' && p.images && p.images[0]) {
    p._flatTemplate = { title: p.title };
    p._printifyExact = true;
    return p.images[0];
  }
  // Exact Printify photo on file for this store product beats both a
  // template match and a model Shopify photo: it is the photo Printify
  // itself uses for this product.
  const exact = printifyImageOf(p);
  if (exact) {
    p._flatTemplate = { title: p.title, brand: 'Printify' };
    p._printifyExact = true;
    return exact;
  }
  p._printifyExact = false;
  const flat = flatTemplateForTitle(p.title);
  if (flat && flat.images && flat.images[0]) {
    p._flatTemplate = flat;
    return flat.images[0];
  }
  p._flatTemplate = null;
  const bare = (p.images && p.images[0]) || p.image || p._photoBare || '';
  if (bare && bare.indexOf('/static/mockups/') === -1) return bare;
  return '';
}
function mockupSourceLabel(p) {
  if (!p) return '';
  if (catalogTemplates === null) return 'Loading flat photo…';
  if (p._printifyExact) return 'Printify photo (exact product photo)';
  if (p._flatTemplate) return 'Printify flat product photo' + (p._flatTemplate.brand ? ' (' + esc(p._flatTemplate.brand) + ')' : '');
  return 'Not a Printify flat photo: bare store photo';
}
function renderCentreMockup() {
  const img = document.getElementById('centreImg');
  const empty = document.getElementById('centreEmpty');
  const box = document.getElementById('placeBox');
  if (!img || !empty || !box) return;
  const p = selectedProduct();
  const url = p ? centreImageUrl(p) : '';
  if (viewSide === 'back') {
    img.style.display = 'none';
    empty.style.display = 'block';
    if (p) empty.innerHTML = '<p style="padding:20px"><small>Back side preview is not available. FRONT is the working side.</small></p>';
    box.style.display = 'none';
    return;
  }
  bindCentreDrag();
  if (!catalogTemplatesTried) {
    catalogTemplatesTried = true;
    fetch('/api/catalog/templates').then(function(r) { return r.json(); }).then(function(j) {
      catalogTemplates = j;
      renderCentreMockup();
    }).catch(function() { catalogTemplatesTried = false; });
  }
  const srcEl = document.getElementById('mockupSource');
  if (srcEl && p) srcEl.innerHTML = '<small>' + mockupSourceLabel(p) + '</small>';
  if (!url) {
    img.style.display = 'none';
    box.style.display = 'none';
    empty.style.display = 'block';
    if (p && !p._photoTried) {
      p._photoTried = true;
      const pid = p.product_id;
      empty.innerHTML = '<p style="padding:20px"><small>Loading product photo...</small></p>';
      fetch('/api/sets/' + currentSet.id + '/products/' + encodeURIComponent(pid) + '/photo?bare=1')
        .then(function(r) { return r.json(); })
        .then(function(j) {
          const sel = selectedProduct();
          if (j.photo && j.photo.indexOf('/static/mockups/') === -1 && sel && sel.product_id === pid) {
            p._photoBare = j.photo;
            renderCentreMockup();
          } else if (sel && sel.product_id === pid) {
            empty.innerHTML = '<p style="padding:20px"><small>No photo on file for ' + esc(p.title || p.product_id) + '. Tap its Preview mockup button once a product photo is available.</small></p>';
          }
        })
        .catch(function() {});
    } else if (p) {
      empty.innerHTML = '<p style="padding:20px"><small>No photo on file for ' + esc(p.title || p.product_id) + '. Tap its Preview mockup button once a product photo is available.</small></p>';
    }
    return;
  }
  empty.style.display = 'none';
  img.style.display = 'block';
  if (img.getAttribute('src') !== url) img.setAttribute('src', url);
  positionPlaceBox();
}
function positionPlaceBox() {
  const img = document.getElementById('centreImg');
  const box = document.getElementById('placeBox');
  if (!img || !box) return;
  syncDesignSize();
  if (img.style.display === 'none' || viewSide === 'back') { box.style.display = 'none'; return; }
  const p = selectedProduct();
  if (!p) { box.style.display = 'none'; return; }
  // FIXED print area: the box geometry never changes with placement.
  // Only the design inside it moves. Design centre (pl.x, pl.y) is a
  // fraction of the full mockup, clamped to the box; design width is
  // pl.scale of the full mockup width, expressed against the box
  // (box width is 50% of the mockup, so scale 0.5 fills the box).
  box.style.display = 'block';
  box.style.left = (PRINT_AREA.left * 100) + '%';
  box.style.top = (PRINT_AREA.top * 100) + '%';
  box.style.width = (PRINT_AREA.width * 100) + '%';
  box.style.height = (PRINT_AREA.height * 100) + '%';
  box.style.transform = 'none';
  const pl = clampPlacement(effectivePlacementOf(p));
  const cx = pl.x, cy = pl.y, scale = pl.scale;
  // Visible text layers, each at its own position inside the box.
  // Layer x/y are full-mockup fractions (null = placement centre);
  // map them into the box, apply size, font, rotation and opacity.
  // Layers are independent of the design-hide flag, so they render
  // even when the design itself is hidden.
  const oldLayers = box.querySelectorAll('.centreLayer');
  oldLayers.forEach(function(el) { el.remove(); });
  if (currentSet) {
    const hiddenHere = (p && p.hidden_layers) || [];
    (currentSet.text_layers || []).filter(function(l) { return !l.hidden && hiddenHere.indexOf(l.id) === -1; }).forEach(function(l) {
      const lx = (l.x === undefined || l.x === null) ? cx : Math.min(PRINT_AREA.left + PRINT_AREA.width, Math.max(PRINT_AREA.left, +l.x));
      const ly = (l.y === undefined || l.y === null) ? cy : Math.min(PRINT_AREA.top + PRINT_AREA.height, Math.max(PRINT_AREA.top, +l.y));
      const span = document.createElement('div');
      span.className = 'centreLayer';
      span.textContent = l.content || '';
      span.style.position = 'absolute';
      span.style.left = (((lx - PRINT_AREA.left) / PRINT_AREA.width) * 100) + '%';
      span.style.top = (((ly - PRINT_AREA.top) / PRINT_AREA.height) * 100) + '%';
      span.style.transform = 'translate(-50%, -50%) rotate(' + (l.rotation || 0) + 'deg)';
      span.style.color = l.colour || '#111111';
      span.style.fontFamily = l.font === 'serif' ? 'serif' : (l.font === 'mono' ? 'monospace' : 'sans-serif');
      span.style.fontSize = Math.max(10, Math.round((l.size || 120) * 0.25)) + 'px';
      span.style.opacity = (l.opacity === undefined ? 1 : (l.opacity > 1 ? l.opacity / 100 : l.opacity));
      span.style.pointerEvents = 'none';
      box.appendChild(span);
    });
  }
  if (!currentSet || !currentSet.design_url || (p.hide_design)) {
    const oldDesign = document.getElementById('designImg');
    if (oldDesign) oldDesign.remove();
    return;
  }
  let designImg = document.getElementById('designImg');
  if (!designImg) {
    designImg = document.createElement('img');
    designImg.id = 'designImg';
    designImg.alt = 'Design';
    designImg.style.position = 'absolute';
    designImg.style.pointerEvents = 'none';
    box.appendChild(designImg);
  }
  if (designImg.getAttribute('src') !== currentSet.design_url) designImg.setAttribute('src', currentSet.design_url);
  const leftPct = ((cx - PRINT_AREA.left) / PRINT_AREA.width) * 100;
  const topPct = ((cy - PRINT_AREA.top) / PRINT_AREA.height) * 100;
  const widthPct = (scale / PRINT_AREA.width) * 100;
  designImg.style.left = leftPct + '%';
  designImg.style.top = topPct + '%';
  designImg.style.width = widthPct + '%';
  designImg.style.height = 'auto';
  designImg.style.transform = 'translate(-50%, -50%) rotate(' + (pl.angle || 0) + 'deg)';
}
function renderArtworkSpec() {
  const box = document.getElementById('artworkSpec');
  if (!box) return;
  if (!currentSet || !currentSet.design_url) { box.innerHTML = '<small>No design uploaded yet.</small>'; return; }
  const w = currentSet.design_width, h = currentSet.design_height, dpi = currentSet.design_dpi;
  const spec = (w && h) ? ('Artwork: ' + w + 'x' + h + (dpi ? ' @ est. ' + dpi + ' DPI' : '')) : 'Artwork uploaded.';
  const p = selectedProduct();
  const pa = p && p.print_area ? ('<br><small>Print area for ' + esc(p.title || '') + ': ' + esc(p.print_area.position) + ' ' + p.print_area.width + 'x' + p.print_area.height + '</small>') : '';
  box.innerHTML = '<b>' + esc(spec) + '</b>' + pa;
}
function renderLayers() {
  const box = document.getElementById('layersList');
  if (!box) return;
  if (!currentSet) { box.innerHTML = '<small>Open a set to see layers.</small>'; return; }
  const rows = [];
  const sel = selectedProduct();
  rows.push('<div class="layerrow"><span><b>Design</b><small> (whole set)</small>' + (currentSet.design_url ? '' : ' <small>none uploaded</small>') + '</span>'
    + (sel ? '<button class="secondary" onclick="toggleDesignHide(\'' + esc(sel.product_id) + '\')">' + (sel.hide_design ? 'Show on this product' : 'Hide on this product') + '</button>' : '')
    + '<button class="danger" onclick="removeDesign()">Remove design</button></div>');
  (currentSet.text_layers || []).forEach(function(l, idx) {
    const eye = l.hidden ? 'Show' : 'Hide';
    const pos = (l.x !== undefined && l.y !== undefined) ? ' @ ' + (+l.x).toFixed(2) + ', ' + (+l.y).toFixed(2) : ' (centred on placement)';
    rows.push('<div class="layerrow"><span><b>Text:</b> ' + esc(l.content) + ' <small>(' + esc(l.font) + ', ' + l.size + 'px, ' + esc(l.colour) + pos + (l.hidden ? ', hidden' : '') + ')</small></span>'
      + '<button class="secondary" onclick="toggleLayerEye(\'' + esc(l.id) + '\')">' + eye + '</button>'
      + '<button class="secondary" onclick="editLayer(\'' + esc(l.id) + '\')">Edit</button>'
      + '<button class="secondary" onclick="moveLayer(\'' + esc(l.id) + '\', -1)">Up</button>'
      + '<button class="secondary" onclick="moveLayer(\'' + esc(l.id) + '\', 1)">Down</button>'
      + (sel ? '<button class="secondary" onclick="hideLayerOnProduct(\'' + esc(sel.product_id) + '\', \'' + esc(l.id) + '\')">This product</button>' : '')
      + '<button class="danger" onclick="deleteLayer(\'' + esc(l.id) + '\')">All products</button></div>');
  });
  box.innerHTML = rows.join('');
}
function editLayer(lid) {
  const l = (currentSet.text_layers || []).filter(function(x) { return x.id === lid; })[0];
  if (!l) return;
  editingLayerId = lid;
  document.getElementById('layerText').value = l.content || '';
  document.getElementById('layerFont').value = l.font || 'sans';
  document.getElementById('layerSize').value = l.size || 120;
  document.getElementById('layerColour').value = l.colour || '#111111';
  document.getElementById('layerCase').value = l.lettercase || 'none';
  document.getElementById('layerRotation').value = l.rotation || 0;
  document.getElementById('layerOpacity').value = l.opacity === undefined ? 100 : Math.round(l.opacity * 100);
  document.getElementById('layerX').value = l.x === undefined ? 0.5 : l.x;
  document.getElementById('layerY').value = l.y === undefined ? 0.47 : l.y;
  document.getElementById('layerXVal').textContent = (+document.getElementById('layerX').value).toFixed(2);
  document.getElementById('layerYVal').textContent = (+document.getElementById('layerY').value).toFixed(2);
  document.getElementById('layerSubmitBtn').textContent = 'Save layer edit';
  document.getElementById('layerCancelBtn').style.display = 'inline-block';
  document.getElementById('layerFormDetails').open = true;
  document.getElementById('layerFormDetails').scrollIntoView();
}
function cancelLayerEdit() {
  editingLayerId = null;
  document.getElementById('layerSubmitBtn').textContent = 'Add text layer';
  document.getElementById('layerCancelBtn').style.display = 'none';
}
async function moveLayer(lid, dir) {
  if (!currentSet) return;
  try {
    const j = await postSet('/layers/' + encodeURIComponent(lid) + '/move', { direction: dir });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function addTextLayer() {
  if (!currentSet) return alert('Create a set first.');
  const body = {
    content: document.getElementById('layerText').value,
    font: document.getElementById('layerFont').value,
    size: document.getElementById('layerSize').value,
    colour: document.getElementById('layerColour').value,
    lettercase: document.getElementById('layerCase').value,
    rotation: document.getElementById('layerRotation').value,
    opacity: document.getElementById('layerOpacity').value,
    x: document.getElementById('layerX').value,
    y: document.getElementById('layerY').value
  };
  try {
    let j;
    if (editingLayerId) {
      j = await postSet('/layers/' + encodeURIComponent(editingLayerId) + '/edit', body);
      refreshAfterSet(j);
      cancelLayerEdit();
      document.getElementById('layerResult').innerHTML = '<p class="ok">Text layer updated. Re-run Preview mockup to see it.</p>';
    } else {
      j = await postSet('/layers', body);
      refreshAfterSet(j.set);
      document.getElementById('layerResult').innerHTML = '<p class="ok">Text layer added. Re-run Preview mockup to see it.</p>';
    }
  } catch (e) { document.getElementById('layerResult').innerHTML = '<p class="warn">' + esc(e.message) + '</p>'; }
}
async function toggleLayerEye(lid) {
  if (!currentSet) return;
  const layer = (currentSet.text_layers || []).filter(function(l) { return l.id === lid; })[0];
  if (!layer) return;
  try {
    const j = await postSet('/layers/' + encodeURIComponent(lid) + '/hide', { hidden: !layer.hidden });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function deleteLayer(lid) {
  if (!currentSet) return;
  if (!confirm('Delete this text layer on ALL products?')) return;
  try {
    const j = await postSet('/layers/' + encodeURIComponent(lid) + '/delete', {});
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function hideLayerOnProduct(pid, lid) {
  if (!currentSet) return;
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  const already = p && (p.hidden_layers || []).indexOf(lid) !== -1;
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/layers/' + encodeURIComponent(lid) + '/hide', { hidden: !already });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function toggleDesignHide(pid) {
  if (!currentSet) return;
  const p = currentSet.products.filter(function(x) { return x.product_id === pid; })[0];
  try {
    const j = await postSet('/products/' + encodeURIComponent(pid) + '/design-hide', { hidden: !p.hide_design });
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
async function removeDesign() {
  if (!currentSet || !currentSet.design_url) return;
  if (!confirm('Remove the design from the whole set? Text layers stay.')) return;
  try {
    const j = await postSet('/design/remove', {});
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
function fmtDraftTime(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) { return null; }
}
function renderDraftLine() {
  const box = document.getElementById('draftLine');
  if (!box) return;
  if (!currentSet) { box.innerHTML = '<small>Open a set to start.</small>'; return; }
  const t = fmtDraftTime(currentSet.draft_saved_at);
  const state = currentSet.publish_state || 'draft';
  const stateText = state === 'published' ? 'Published live in Shopify' : (state === 'failed' ? 'Last publish failed' : 'Not published yet');
  box.innerHTML = '<small>' + (t ? 'Saved ' + t + ' · ' : 'Not saved yet · ') + esc(stateText) + '</small>';
}
async function saveDraft() {
  if (!currentSet) return alert('Create a set first.');
  try {
    const j = await postSet('/save-draft', {});
    refreshAfterSet(j);
  } catch (e) { alert(e.message); }
}
function scrollToPickers() {
  const el = document.getElementById('pickerCard');
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}
async function loadCatalogTemplates() {
  const box = document.getElementById('catalogList');
  if (!box) return;
  let r;
  try { r = await fetch('/api/catalog/templates'); } catch (e) { box.innerHTML = '<small>Could not load catalog. Reload and try again.</small>'; return; }
  if (!r.ok) { box.innerHTML = '<small>Could not load catalog.</small>'; return; }
  const items = await r.json();
  box.innerHTML = items.map(function(t) {
    return '<div style="margin-top:12px"><b>' + esc(t.title) + '</b> <small>(' + esc(t.brand) + ')</small><br>'
      + '<small>' + t.colours.length + ' colours, ' + t.sizes.length + ' sizes</small> <span class="badge">Catalog template, not a store product yet</span>'
      + '<button onclick="addCatalogTemplate(\'' + esc(t.product_id) + '\')">Add to set</button></div>';
  }).join('') + '<button class="secondary" onclick="addAllCatalogTemplates()">Add all 3 to set</button>';
}
async function addCatalogTemplate(pid) {
  if (!currentSet) return alert('Create or open a set first.');
  try {
    const j = await postSet('/catalog-templates', { product_ids: [pid] });
    refreshAfterSet(j.set);
  } catch (e) { alert(e.message); }
}
async function addAllCatalogTemplates() {
  if (!currentSet) return alert('Create or open a set first.');
  try {
    const j = await postSet('/catalog-templates', { all: true });
    refreshAfterSet(j.set);
  } catch (e) { alert(e.message); }
}
function setGrouping(g) {
  if (!currentSet) return alert('Create a set first.');
  currentSet.grouping = g;
  const a = document.getElementById('groupCombine'); if (a) a.style.outline = g === 'combine' ? '3px solid #0f766e' : '';
  const b = document.getElementById('groupSplit'); if (b) b.style.outline = g === 'split' ? '3px solid #0f766e' : '';
}
async function saveDetails() {
  if (!currentSet) return alert('Create a set first.');
  const val = function(id, fallback) { const e = document.getElementById(id); return e ? e.value.trim() : fallback; };
  const body = {
    name: val('detailName', currentSet.name || ''),
    slug: val('detailSlug', currentSet.slug || ''),
    description: val('detailDesc', currentSet.description || ''),
    tags: val('detailTags', (currentSet.tags || []).join(', ')),
    grouping: currentSet.grouping || 'combine'
  };
  try {
    const j = await postSet('/details', body);
    refreshAfterSet(j);
    document.getElementById('detailResult').innerHTML = '<p class="ok">Set details saved (draft).</p>';
  } catch (e) { alert(e.message); }
}
function fillDetails() {
  if (!currentSet) return;
  const setVal = function(id, v) { const e = document.getElementById(id); if (e) e.value = v; };
  setVal('detailName', currentSet.name || '');
  setVal('detailSlug', currentSet.slug || '');
  setVal('detailDesc', currentSet.description || '');
  setVal('detailTags', (currentSet.tags || []).join(', '));
  setGrouping(currentSet.grouping || 'combine');
}
async function renderVariantCount() {
  const box = document.getElementById('variantCount');
  if (!box) return;
  if (!currentSet) { box.innerHTML = '<small>Open a set to see variant counts.</small>'; return; }
  try {
    const r = await fetch('/api/sets/' + currentSet.id + '/variant-count');
    const j = await r.json();
    const cls = j.guard_ok ? 'ok' : 'warn';
    box.innerHTML = '<p>Grouping: <b>' + esc(j.grouping) + '</b> | Combined variants: <b>' + j.total_combine + '</b></p><p class="' + cls + '">' + esc(j.message) + '</p>';
  } catch (e) { box.innerHTML = '<small>Could not load variant counts.</small>'; }
}
function renderPublishStatus() {
  const box = document.getElementById('publishStatus');
  if (!box) return;
  if (!currentSet) { box.innerHTML = ''; return; }
  const state = currentSet.publish_state || 'draft';
  const map = { draft: 'Not published yet', launching: 'Publishing...', published: 'Published live in Shopify', failed: 'Last publish failed', unavailable: 'Hidden' };
  box.innerHTML = '<p>Publish status: <b>' + esc(map[state] || state) + '</b>' + (currentSet.publish_error ? ' <span class="warn">' + esc(currentSet.publish_error) + '</span>' : '') + '</p>';
}
async function previewPublish() {
  if (!currentSet) return alert('Create a set first.');
  const box = document.getElementById('publishResult');
  if (!box) return;
  box.innerHTML = '<small>Checking...</small>';
  try {
    const j = await postSet('/publish', { dry_run: true });
    const rows = (j.checklist || j.products).map(function(p) {
      const variants = p.variants && p.variants.length !== undefined ? p.variants.length : p.variants;
      const ready = p.ready !== undefined ? p.ready : true;
      return '<div class="layerrow"><span>' + esc(p.title) + ' (' + variants + ' variants)</span><span>' + (ready ? '<span class="ok">Ready</span>' : '<span class="warn">Not ready</span>') + '</span></div>';
    }).join('');
    const warns = (j.warnings || []).map(function(w) { return '<p><small class="warn">' + esc(w) + '</small></p>'; }).join('');
    box.innerHTML = '<p class="ok">Preview only, nothing created.</p>' + rows + warns + '<p><small>' + esc(j.note) + '</small></p>';
  } catch (e) { box.innerHTML = '<p class="warn">' + esc(e.message) + '</p>'; }
}
async function publishLive() {
  if (!currentSet) return alert('Create a set first.');
  if (!confirm('Publish this set to Shopify as LIVE products? They will be visible in the store immediately.')) return;
  const box = document.getElementById('publishResult');
  if (!box) return;
  box.innerHTML = '<small>Publishing...</small>';
  try {
    const j = await postSet('/publish', {});
    currentSet.publish_state = 'published'; currentSet.artwork_locked = true;
    renderPublishStatus(); renderDraftLine();
    const ids = j.shopify_ids || [];
    let html = '<p class="ok">Published live. Shopify IDs: ' + esc(ids.join(', ')) + '</p>';
    if (j.partial) html += '<p class="warn">Partial publish: ' + j.created.length + ' of ' + j.total + ' created. Tap Publish again to resume from product ' + (j.next_index + 1) + '.</p>';
    if (ids.length) html += '<p><button class="secondary" onclick="createSetPage()">Create hidden set page on Shopify</button> <small>Creates a hidden page (not linked anywhere) so the set can be shared later. It will NOT appear in the store.</small></p>';
    box.innerHTML = html;
  } catch (e) { box.innerHTML = '<p class="warn">' + esc(e.message) + '</p>'; }
}
async function createSetPage() {
  if (!currentSet) return alert('Create a set first.');
  const box = document.getElementById('publishResult');
  try {
    const body = {
      title: currentSet.name,
      handle: currentSet.slug || null,
      body_html: currentSet.description || ''
    };
    const r = await fetch('/api/sets/' + currentSet.id + '/create-page', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Page creation failed.');
    box.innerHTML = '<p class="ok">Hidden set page created (Shopify page ' + esc(String(j.page_id)) + '). It is not linked anywhere in the store.</p>';
  } catch (e) { box.innerHTML = '<p class="warn">' + esc(e.message) + '</p>'; }
}
async function addProduct() {
  if (!currentSet) return alert('Create a set first.');
  const pid = document.getElementById('productId').value.trim();
  if (!pid) return alert('Type a product ID first.');
  const r = await fetch('/api/sets/' + currentSet.id + '/products', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ product_id: pid }) });
  if (!r.ok) { const j = await r.json().catch(function(){ return {}; }); return alert(j.error || 'Could not add product.'); }
  currentSet = await r.json();
  document.getElementById('productId').value = '';
  syncCache();
  updateCurrentSetLine();
  renderSetList();
  renderProducts();
  renderCentreMockup();
}
let searchTimer = null;
let searchSeq = 0;
function debouncedSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchProducts, 300);
}
function priceNum(p) {
  if (!p || p.price === undefined || p.price === null) return null;
  const n = parseFloat(String(p.price).replace(/[^0-9.]/g, ''));
  return isNaN(n) ? null : n;
}
function sortedSearchResults() {
  const mode = document.getElementById('searchSort').value;
  const list = lastSearchResults.slice();
  if (mode === 'asc' || mode === 'desc') {
    list.sort(function(a, b) {
      const pa = priceNum(a), pb = priceNum(b);
      if (pa === null && pb === null) return 0;
      if (pa === null) return 1;
      if (pb === null) return -1;
      return mode === 'asc' ? pa - pb : pb - pa;
    });
  }
  return list;
}
function rerenderSearch() {
  renderSearchResults(sortedSearchResults());
}
function renderSearchResults(products) {
  const box = document.getElementById('searchResults');
  if (!products.length) { box.innerHTML = '<small>No products found.</small>'; return; }
  const inSet = currentSet ? currentSet.products.map(function(p) { return p.product_id; }) : [];
  box.innerHTML = products.map(function(p) {
    const already = inSet.indexOf(p.id) !== -1;
    const thumb = p.image
      ? '<img src="' + esc(p.image) + '" alt="" style="width:56px;height:56px;object-fit:cover;border-radius:8px">'
      : '<span style="width:56px;height:56px;border-radius:8px;background:#eee;display:inline-block"></span>';
    const btn = already
      ? '<button class="secondary" style="margin-top:0" disabled>In set</button>'
      : '<button style="margin-top:0" onclick="addSearchedProduct(\'' + esc(p.id) + '\')">Add</button>';
    return '<div style="display:flex;gap:10px;align-items:center;margin-top:12px">' + thumb
      + '<div style="flex:1;min-width:0"><b style="overflow-wrap:anywhere">' + esc(p.title) + '</b><br><small>' + (p.price ? esc(p.price) : 'Price not shown') + '</small></div>'
      + '<div style="min-width:96px">' + btn + '</div></div>';
  }).join('');
}
async function searchProducts() {
  const box = document.getElementById('searchResults');
  const q = document.getElementById('productSearch').value.trim();
  if (q.length < 2) { box.innerHTML = ''; lastSearchResults = []; return; }
  const mySeq = ++searchSeq;
  box.innerHTML = '<small>Searching...</small>';
  let r;
  try {
  r = await fetch('/api/products/search?q=' + encodeURIComponent(q) + '&limit=50');
  } catch (e) {
    if (mySeq !== searchSeq) return;
    box.innerHTML = '<small>Search failed. Check connection and try again.</small>';
    return;
  }
  const j = await r.json().catch(function(){ return {}; });
  if (mySeq !== searchSeq) return;
  if (!r.ok) {
    if (r.status === 503) {
      box.innerHTML = '<small>Shopify is not connected. <a href="/auth/shopify">Connect Shopify</a> first, then search again.</small>';
    } else {
      box.innerHTML = '<small>' + esc(j.error || 'Search failed. Try again.') + '</small>';
    }
    return;
  }
  lastSearchResults = j.products || [];
  rerenderSearch();
}
async function addSearchedProduct(pid) {
  if (!currentSet) return alert('Create a set first.');
  const r = await fetch('/api/sets/' + currentSet.id + '/products', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ product_id: pid }) });
  if (!r.ok) { const j = await r.json().catch(function(){ return {}; }); return alert(j.error || 'Could not add product.'); }
  currentSet = await r.json();
  syncCache();
  updateCurrentSetLine();
  renderSetList();
  renderProducts();
  renderCentreMockup();
  searchProducts();
}
async function toggleLock(pid, locked) {
  if (!currentSet) return;
  const r = await fetch('/api/sets/' + currentSet.id + '/products/' + encodeURIComponent(pid) + '/lock', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ locked: !locked }) });
  if (!r.ok) { const j = await r.json().catch(function(){ return {}; }); return alert(j.error || 'Could not change lock.'); }
  currentSet = await r.json();
  syncCache();
  updateCurrentSetLine();
  renderSetList();
  renderProducts();
  renderCentreMockup();
}
async function uploadDesign() {
  if (!currentSet) return alert('Create a set first.');
  const files = document.getElementById('designFile').files;
  if (!files.length) return alert('Choose a design file first.');
  const box = document.getElementById('uploadResult');
  box.innerHTML = '<small>Uploading...</small>';
  async function uploadOne(setId, file) {
    const fd = new FormData(); fd.append('design', file);
    const r = await fetch('/api/sets/' + setId + '/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Upload failed.');
    return j;
  }
  try {
    const j = await uploadOne(currentSet.id, files[0]);
    currentSet.design_url = j.url;
    currentSet.design_width = j.validation.width;
    currentSet.design_height = j.validation.height;
    currentSet.design_dpi = j.validation.dpi_estimate;
    // Server clears rendered mockups on upload; clear the client's
    // copies too, or the centre view keeps showing the old printed
    // design underneath the new one.
    (currentSet.products || []).forEach(function(p) {
      p.mockups = []; p.mockup_versions = {}; p.mockup_version = null;
      if ((p.hero_image || '').indexOf('/static/mockups/') === 0) p.hero_image = null;
      delete p._photo; delete p._photoBare; p._photoTried = false;
    });
    renderCentreMockup();
    const v = j.validation || {};
    const warns = (v.warnings || []).map(function(w) { return '<br><small>' + esc(w) + '</small>'; }).join('');
    let html = '<p class="ok">Uploaded and checked: transparent PNG, ' + v.width + ' x ' + v.height + ' px, about ' + v.dpi_estimate + ' DPI estimated.' + warns + '</p>';
    // Extra files: duplicate this set, then upload each extra as that copy's design.
    for (let i = 1; i < files.length; i++) {
      try {
        const dr = await fetch('/api/sets/' + currentSet.id + '/duplicate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({}) });
        const dj = await dr.json();
        if (!dr.ok) throw new Error(dj.error || 'Duplicate failed.');
        await uploadOne(dj.id, files[i]);
        allSets.push(dj);
        html += '<p><small>Extra file ' + (i + 1) + ' saved as a duplicate set: ' + esc(dj.name) + '.</small></p>';
      } catch (e) {
        html += '<p><span class="warn">Extra file ' + (i + 1) + ' failed: ' + esc(e.message) + '</span></p>';
      }
    }
    box.innerHTML = html;
    renderSetList();
    renderArtworkSpec();
  } catch (e) { box.innerHTML = '<p class="warn">' + esc(e.message) + '</p>'; }
}
async function saveMaster() {
  if (!currentSet) return alert('Create a set first.');
  const placement = clampPlacement({ x: +document.getElementById('x').value, y: +document.getElementById('y').value, scale: +document.getElementById('s').value, angle: +document.getElementById('angle').value });
  const _mr = document.getElementById('masterResult');
  const r = await fetch('/api/sets/' + currentSet.id + '/master', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ placement }) });
  currentSet = await r.json();
  syncCache();
  clearDirty();
  document.getElementById('masterResult').innerHTML = '<p>Master saved. Every locked product now follows it.</p>';
  positionPlaceBox();
}
/* Per-page init scripts call checkAuth + their own loader. */
