// NARE & CO. — Industry Grade Frontend | Grid White / Black / Neon Green
const API = location.origin;
let state = {
  type: "url",
  isDynamic: false,
  pattern: "square",
  eyeStyle: "square",
  fg: "#0A0A0A",
  bg: "#FFFFFF",
  gradient: "solid",
  frameText: "",
  frameColor: "#00FF88",
  logoB64: null,
  lastImage: null,
  lastId: null,
  previewAbort: null
};

const TYPES = [
  {id:"url", label:"URL", icon:"🔗", cat:"popular"},
  {id:"vcard", label:"vCard", icon:"👤", cat:"business"},
  {id:"file", label:"File", icon:"📄", cat:"business"},
  {id:"linkpage", label:"Link Page", icon:"🌐", cat:"social"},
  {id:"menu", label:"Menu", icon:"🍽️", cat:"business"},
  {id:"appstore", label:"App Stores", icon:"📱", cat:"business"},
  {id:"landingpage", label:"Landing", icon:"▣", cat:"business"},
  {id:"smarturl", label:"Smart URL", icon:"🧠", cat:"utility"},
  {id:"gs1", label:"GS1", icon:"🏷️", cat:"business"},
  {id:"mp3", label:"MP3", icon:"🎵", cat:"utility"},
  {id:"video", label:"Video", icon:"▶", cat:"social"},
  {id:"wifi", label:"WiFi", icon:"📶", cat:"utility"},
  {id:"email", label:"Email", icon:"✉", cat:"utility"},
  {id:"whatsapp", label:"WhatsApp", icon:"💬", cat:"social"},
  {id:"event", label:"Event", icon:"📅", cat:"business"},
  {id:"facebook", label:"Facebook", icon:"f", cat:"social"},
  {id:"youtube", label:"YouTube", icon:"▶", cat:"social"},
  {id:"instagram", label:"Instagram", icon:"◎", cat:"social"},
  {id:"pinterest", label:"Pinterest", icon:"P", cat:"social"},
  {id:"tiktok", label:"TikTok", icon:"♪", cat:"social"},
  {id:"twitter", label:"Twitter", icon:"𝕏", cat:"social"},
  {id:"location", label:"Location", icon:"📍", cat:"utility"},
  {id:"text", label:"Text", icon:"T", cat:"utility"},
  {id:"sms", label:"SMS", icon:"💬", cat:"utility"},
  {id:"googleform", label:"G Form", icon:"📝", cat:"business"},
  {id:"googlereview", label:"G Review", icon:"⭐", cat:"business"},
];

const FORM_DEFS = {
  url: [{key:"url", label:"Website URL *", placeholder:"https://www.nareandco.com", type:"url", required:true}],
  text: [{key:"text", label:"Your Text *", placeholder:"Enter text to encode", type:"textarea", required:true}],
  email: [{key:"email", label:"Email address *", placeholder:"hello@nareandco.com", required:true}, {key:"subject", label:"Subject", placeholder:"Hello"}, {key:"body", label:"Message", placeholder:"Hi there!", type:"textarea"}],
  sms: [{key:"phone", label:"Phone Number *", placeholder:"+919876543210", required:true}, {key:"message", label:"Message", placeholder:"Hello!", type:"textarea"}],
  wifi: [{key:"ssid", label:"Network Name (SSID) *", placeholder:"NARE-WIFI", required:true}, {key:"password", label:"Password", placeholder:"••••••••"}, {key:"encryption", label:"Encryption", type:"select", opts:["WPA","WEP","nopass"]}, {key:"hidden", label:"Hidden?", type:"select", opts:["false","true"]}],
  vcard: [{key:"name", label:"Full Name *", placeholder:"Jane Doe", required:true}, {key:"organization", label:"Organization", placeholder:"NARE & CO."}, {key:"phone", label:"Phone", placeholder:"+91 98765 43210"}, {key:"email", label:"Email", placeholder:"jane@nareandco.com"}, {key:"url", label:"Website", placeholder:"https://nareandco.com"}, {key:"address", label:"Address", placeholder:"Hyderabad, India"}],
  whatsapp: [{key:"phone", label:"WhatsApp Number *", placeholder:"+919876543210", required:true}, {key:"message", label:"Prefilled Message", placeholder:"Hi!"}],
  location: [{key:"latitude", label:"Latitude *", placeholder:"17.3850", required:true}, {key:"longitude", label:"Longitude *", placeholder:"78.4867", required:true}],
  event: [{key:"title", label:"Event Title *", placeholder:"NARE & CO. Launch", required:true}, {key:"location", label:"Location", placeholder:"Hyderabad"}, {key:"start", label:"Start (YYYYMMDDTHHMMSSZ)", placeholder:"20260905T100000Z"}, {key:"end", label:"End", placeholder:"20260905T120000Z"}, {key:"description", label:"Description", type:"textarea", placeholder:"Join us..."}],
  file: [{key:"url", label:"File URL *", placeholder:"https://example.com/file.pdf", required:true}, {key:"note", label:"Tip", type:"help", text:"Paste direct file link (PDF/JPG/PNG/MP4). For dynamic hosting, use File QR — we create trackable short URL."}],
  linkpage: [{key:"title", label:"Page Title", placeholder:"NARE & CO. Links"}, {key:"bio", label:"Bio", placeholder:"Discover our world..."}, {key:"links", label:"Links (label|url per line)", type:"textarea", placeholder:"Instagram|https://instagram.com/nare\nShop|https://nareandco.com/shop"}],
  menu: [{key:"restaurant", label:"Restaurant Name", placeholder:"NARE Bistro"}, {key:"url", label:"Menu Link / PDF URL *", placeholder:"https://nareandco.com/menu.pdf", required:true}],
  appstore: [{key:"ios", label:"App Store (iOS) URL", placeholder:"https://apps.apple.com/..."}, {key:"android", label:"Google Play URL", placeholder:"https://play.google.com/..."}],
  landingpage: [{key:"title", label:"Landing Title", placeholder:"Summer Drop — NARE & CO."}, {key:"url", label:"Destination URL *", placeholder:"https://nareandco.com/drop", required:true}],
  smarturl: [{key:"primaryUrl", label:"Default URL *", placeholder:"https://nareandco.com", required:true}, {key:"rules", label:"Rules (optional)", type:"textarea", placeholder:"country:IN → https://in.nareandco.com"}],
  gs1: [{key:"content", label:"GS1 Data *", placeholder:"(01)09506000134352(17)240105(10)ABC123", required:true}],
  mp3: [{key:"url", label:"Audio URL *", placeholder:"https://soundcloud.com/...", required:true}],
  video: [{key:"url", label:"Video URL *", placeholder:"https://youtube.com/watch?v=...", required:true}],
  facebook: [{key:"url", label:"Facebook URL *", placeholder:"https://facebook.com/nareandco", required:true}],
  youtube: [{key:"url", label:"YouTube URL *", placeholder:"https://youtube.com/@nare", required:true}],
  instagram: [{key:"url", label:"Instagram URL *", placeholder:"https://instagram.com/nare", required:true}],
  pinterest: [{key:"url", label:"Pinterest URL *", placeholder:"https://pinterest.com/nare", required:true}],
  tiktok: [{key:"url", label:"TikTok URL *", placeholder:"https://tiktok.com/@nare", required:true}],
  twitter: [{key:"url", label:"Twitter/X URL *", placeholder:"https://x.com/nare", required:true}],
  googleform: [{key:"url", label:"Google Form URL *", placeholder:"https://forms.gle/...", required:true}],
  googlereview: [{key:"url", label:"Google Review Link *", placeholder:"https://g.page/r/...", required:true}],
};

function renderTypeGrid(filter="all"){
  const grid=document.getElementById('typeGrid');
  let list=TYPES;
  if(filter!=="all"){
    if(filter==="popular") list=TYPES.filter(t=>["url","vcard","file","wifi","instagram","whatsapp","youtube","text"].includes(t.id));
    else list=TYPES.filter(t=>t.cat===filter);
  }
  grid.innerHTML=list.map(t=>`
    <button class="type-btn ${state.type===t.id?'active':''}" data-type="${t.id}" aria-label="${t.label}">
      <div class="ico">${t.icon}</div>
      <div>${t.label}</div>
    </button>
  `).join('');
  grid.querySelectorAll('.type-btn').forEach(b=>{
    b.onclick=()=>{ state.type=b.dataset.type; renderTypeGrid(filter); renderForm(); updatePreviewMeta(); preview(); toast(`Selected ${b.dataset.type.toUpperCase()}`); }
  });
}

function renderForm(){
  const defs = FORM_DEFS[state.type] || FORM_DEFS.url;
  const area=document.getElementById('formArea');
  let html = `<div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><strong style="font-size:13px">Step 1 • Enter ${state.type.toUpperCase()} details</strong><span class="badge ${state.isDynamic?'badge-neon':'badge-white'}" style="border:1.5px solid var(--black)">${state.isDynamic?'DYNAMIC • Editable':'STATIC • Free'}</span></div>`;
  defs.forEach(f=>{
    if(f.type==="help"){
      html+=`<div class="help" role="note">${f.text}</div>`;
      return;
    }
    const req = f.required ? ' <span style="color:#DC2626">*</span>' : '';
    if(f.type==="textarea"){
      html+=`<div class="field"><label for="f_${f.key}">${f.label}${req}</label><textarea id="f_${f.key}" rows="3" placeholder="${f.placeholder||''}" ${f.required?'required':''}></textarea><div class="field-error" id="err_${f.key}"></div></div>`;
    } else if(f.type==="select"){
      html+=`<div class="field"><label for="f_${f.key}">${f.label}${req}</label><select id="f_${f.key}">${f.opts.map(o=>`<option value="${o}">${o}</option>`).join('')}</select></div>`;
    } else {
      html+=`<div class="field"><label for="f_${f.key}">${f.label}${req}</label><input id="f_${f.key}" type="${f.type||'text'}" placeholder="${f.placeholder||''}" ${f.required?'required':''}></div>`;
    }
  });
  html+=`<div class="two-col">
    <div class="field"><label for="f_name">QR Name (dashboard)</label><input id="f_name" placeholder="My ${state.type.toUpperCase()} QR — NARE" maxlength="60"></div>
    <div class="field"><label for="f_folder">Campaign Folder</label><select id="f_folder"><option>My QR Codes</option><option>Marketing</option><option>Events</option><option>Retail</option></select></div>
  </div>`;
  if(state.isDynamic){
    html+=`<details style="background:var(--grid-white);border:1px solid var(--black);border-radius:12px;padding:10px" open><summary style="font-weight:800;cursor:pointer;font-size:12px">🔒 Security & Expiry (Dynamic only)</summary>
      <div class="two-col" style="margin-top:10px">
        <div class="field"><label for="f_password">Password (optional)</label><input id="f_password" type="password" placeholder="Leave blank for public"></div>
        <div class="field"><label for="f_scan_limit">Scan Limit</label><input id="f_scan_limit" type="number" min="1" placeholder="e.g. 1000"></div>
      </div>
      <div class="field"><label for="f_expiry">Expiry Date (optional)</label><input id="f_expiry" type="datetime-local"></div>
    </details>`;
  } else {
    html+=`<div class="help">💡 <b>Static</b> is free forever. Switch to <b>Dynamic</b> to edit URL after print and track scans.</div>`;
  }
  area.innerHTML=html;
  area.querySelectorAll('input,textarea,select').forEach(el=>{
    el.addEventListener('input', debounce(preview, 350));
    el.addEventListener('change', preview);
  });
}

function collectData(){
  const defs = FORM_DEFS[state.type] || [];
  const data={};
  defs.forEach(f=>{
    if(f.type==="help") return;
    const el=document.getElementById(`f_${f.key}`);
    if(el) data[f.key]=el.value.trim();
  });
  return data;
}

function validateForm(){
  let ok=true;
  const defs=FORM_DEFS[state.type]||[];
  defs.forEach(f=>{
    if(f.required){
      const el=document.getElementById(`f_${f.key}`);
      const err=document.getElementById(`err_${f.key}`);
      if(el && !el.value.trim()){
        ok=false;
        el.classList.add('error');
        if(err){ err.textContent=`${f.label.replace(' *','')} is required`; err.classList.add('show'); }
      } else {
        if(el) el.classList.remove('error');
        if(err){ err.classList.remove('show'); }
      }
    }
  });
  return ok;
}

function buildContentForPreview(){
  const data=collectData();
  const t=state.type;
  if(t==="url"||t==="facebook"||t==="instagram"||t==="youtube"||t==="tiktok"||t==="twitter"||t==="pinterest"||t==="video"||t==="mp3"||t==="file"||t==="googleform"||t==="googlereview"||t==="landingpage"||t==="menu"){
    let u=data.url||data.content||"";
    if(!u) return "";
    if(!/^https?:\/\//.test(u)) u="https://"+u;
    return u;
  }
  if(t==="text") return data.text||"";
  if(t==="email"){
    if(!data.email) return "";
    return `mailto:${data.email}?subject=${data.subject||''}&body=${data.body||''}`;
  }
  if(t==="sms") return data.phone ? `SMSTO:${data.phone}:${data.message||''}` : "";
  if(t==="wifi") return data.ssid ? `WIFI:T:${data.encryption||'WPA'};S:${data.ssid};P:${data.password||''};;` : "";
  if(t==="vcard") return data.name ? `BEGIN:VCARD\nFN:${data.name}\nTEL:${data.phone||''}\nEMAIL:${data.email||''}\nEND:VCARD` : "";
  if(t==="whatsapp") return data.phone ? `https://wa.me/${data.phone}?text=${encodeURIComponent(data.message||'')}` : "";
  if(t==="location") return data.latitude && data.longitude ? `geo:${data.latitude},${data.longitude}` : "";
  if(t==="event") return data.title ? `BEGIN:VEVENT\nSUMMARY:${data.title}\nEND:VEVENT` : "";
  if(t==="appstore") return data.ios||data.android||"";
  if(t==="smarturl") return data.primaryUrl||"";
  if(t==="gs1") return data.content||"";
  return data.url||data.text||"";
}

let previewTimer=null;
function debounce(fn,ms){ return (...a)=>{ clearTimeout(previewTimer); previewTimer=setTimeout(()=>fn(...a), ms)} }

async function preview(){
  const content = buildContentForPreview();
  const img=document.getElementById('qrImage');
  const frame=document.getElementById('qrFrame');
  const loading=document.getElementById('qrLoading');
  const noPrev=document.getElementById('qrNoPreview');
  if(!content){
    if(noPrev){ noPrev.style.display="grid"; }
    return;
  } else if(noPrev){ noPrev.style.display="none"; }

  // show loading
  if(loading) loading.style.display="grid";
  if(frame) frame.classList.add('loading');

  // abort previous
  if(state.previewAbort) try{ state.previewAbort.abort(); }catch{}
  const controller=new AbortController();
  state.previewAbort=controller;

  try{
    const res = await fetch(`${API}/api/preview`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      signal: controller.signal,
      body: JSON.stringify({
        content,
        type: state.type,
        fg_color: state.fg,
        bg_color: state.bg,
        pattern: state.pattern,
        eye_style: state.eyeStyle,
        gradient: state.gradient,
        frame_text: state.frameText,
        frame_color: state.frameColor,
        logo_base64: state.logoB64
      })
    });
    const j=await res.json();
    if(j.image_base64){
      img.src=j.image_base64;
      state.lastImage=j.image_base64;
      img.onload=()=>{
        if(loading) loading.style.display="none";
        if(frame) frame.classList.remove('loading');
      };
      return;
    }
  }catch(e){
    if(e.name==='AbortError') return;
    // fallback
  } finally {
    if(loading) loading.style.display="none";
    if(frame) frame.classList.remove('loading');
  }
  // fallback to external quick qr
  if(content){
    const col=state.fg.replace('#','');
    const bg=state.bg.replace('#','');
    img.src=`https://api.qrserver.com/v1/create-qr-code/?size=360x360&data=${encodeURIComponent(content)}&color=${col}&bgcolor=${bg}&margin=4`;
  }
}

function updatePreviewMeta(){
  const el=document.getElementById('previewType');
  if(!el) return;
  el.textContent=`${state.type.toUpperCase()} • ${state.isDynamic?'Dynamic':'Static'}`;
  el.style.background=state.isDynamic?'var(--neon)':'white';
  el.style.color='var(--black)';
}

function validateEmail(email){
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

async function generate(){
  if(!validateForm()){
    toast("Please fill required fields", true);
    // scroll to first error
    const err=document.querySelector('.field input.error, .field textarea.error');
    if(err) err.scrollIntoView({behavior:'smooth', block:'center'});
    return;
  }
  const contentCheck=buildContentForPreview();
  if(!contentCheck){
    toast("Please enter valid content", true);
    return;
  }
  // For dynamic, require login to enable tracking/edit
  const token=localStorage.getItem('nare_token');
  if(state.isDynamic && !token){
    toast("Login required for Dynamic (trackable) QR — showing login", true);
    openAuth('register');
    document.getElementById('authError').textContent="Dynamic QR needs account — Register free to track & edit later. Or switch to Static.";
    document.getElementById('authError').classList.add('show');
    return;
  }

  const data=collectData();
  const nameEl=document.getElementById('f_name');
  const name=nameEl? nameEl.value.trim()||`My ${state.type.toUpperCase()} QR` : `My ${state.type.toUpperCase()} QR`;
  const btn=document.getElementById('generateBtn');
  btn.disabled=true; const orig=btn.textContent; btn.textContent="⟳ Generating…"; btn.classList.add('btn-loading');
  
  try{
    const payload={
      type: state.type,
      data,
      is_dynamic: state.isDynamic,
      fg_color: state.fg,
      bg_color: state.bg,
      pattern: state.pattern,
      eye_style: state.eyeStyle,
      gradient: state.gradient,
      frame_text: state.frameText,
      frame_color: state.frameColor,
      name,
      logo_base64: state.logoB64,
      password: document.getElementById('f_password')?.value || null,
      scan_limit: document.getElementById('f_scan_limit')?.value ? parseInt(document.getElementById('f_scan_limit').value) : null,
      expiry_date: document.getElementById('f_expiry')?.value ? new Date(document.getElementById('f_expiry').value).toISOString() : null
    };
    const res=await fetch(`${API}/api/generate`,{
      method:"POST",
      headers:{"Content-Type":"application/json", ...(token?{"Authorization":`Bearer ${token}`}:{})},
      body: JSON.stringify(payload)
    });
    const j=await res.json();
    if(!res.ok) throw new Error(j.error||"Failed to generate");
    document.getElementById('qrImage').src=j.image_base64;
    state.lastImage=j.image_base64;
    state.lastId=j.qr_id;
    
    // Success without confirm — toast + inline banner
    toast(j.is_dynamic ? `QR saved! ${j.short_code} • Trackable` : `QR ready — Static free`);
    
    // Show success bar under generator
    let bar=document.getElementById('genSuccess');
    if(!bar){
      bar=document.createElement('div');
      bar.id='genSuccess';
      bar.style.cssText='margin:0 18px 14px;background:var(--black);color:var(--neon);padding:12px 14px;border-radius:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;border:1px solid var(--black)';
      document.getElementById('generateBtn').parentElement.insertAdjacentElement('afterend', bar);
    }
    const dlName=`NARE-CO-${state.type}-${Date.now()}.png`;
    bar.innerHTML=`
      <span style="font-size:12px;font-weight:800">✔ ${j.is_dynamic?'Dynamic saved to Dashboard':'Static ready'} • <span style="color:white">${j.is_dynamic?`/r/${j.short_code}`: 'Static'}</span></span>
      <span style="display:flex;gap:6px">
        <button class="btn btn-primary btn-sm" onclick="download(state.lastImage, '${dlName}')">⬇ PNG</button>
        <button class="btn btn-ghost btn-sm" style="background:white" onclick="location.href='/dashboard'">Dashboard →</button>
      </span>
    `;
    bar.style.display='flex';

  }catch(e){
    toast("Error: "+e.message, true);
  }finally{
    btn.disabled=false; btn.textContent=orig; btn.classList.remove('btn-loading');
  }
}

function download(dataUrl, filename){
  if(!dataUrl){ toast("Nothing to download", true); return; }
  const a=document.createElement('a');
  a.href=dataUrl;
  a.download=filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(`Downloaded ${filename}`);
}

// Auth — PROFESSIONAL
let authMode="login";
function openAuth(mode){
  authMode=mode;
  const m=document.getElementById('authModal');
  m.classList.add('open');
  document.getElementById('authTitle').textContent= mode==="login" ? "Welcome back" : "Create your free account";
  document.getElementById('authSubtitle').textContent= mode==="login" ? "Log in to manage your QRs" : "Free • Unlimited static • 3 dynamic";
  document.getElementById('nameField').style.display= mode==="register" ? "block" : "none";
  document.getElementById('authSubmit').textContent= mode==="login" ? "Log In →" : "Create Account →";
  document.getElementById('switchAuth').textContent= mode==="login" ? "Need an account? Register free" : "Have an account? Log In";
  document.getElementById('passHint').style.display= mode==="register" ? "block" : "none";
  document.getElementById('forgotLink').style.display= mode==="login" ? "block" : "none";
  hideAuthErrors();
  // focus email
  setTimeout(()=>document.getElementById('authEmail').focus(), 100);
}
function closeModal(id){ document.getElementById(id).classList.remove('open'); }
function openModal(which){
  if(which==="demo") document.getElementById('demoModal').classList.add('open');
  if(which==="register") openAuth("register");
  if(which==="login") openAuth("login");
}
function hideAuthErrors(){
  document.getElementById('authError').classList.remove('show');
  document.getElementById('authSuccess').classList.remove('show');
  document.getElementById('authMsg').style.display="none";
  ['emailError','passError','nameError'].forEach(id=>{
    const el=document.getElementById(id);
    if(el){ el.textContent=""; el.classList.remove('show'); }
  });
  ['authEmail','authPass','authName'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.classList.remove('error');
  });
  document.getElementById('authLoading').style.display="none";
}
function showFieldError(inputId, errId, msg){
  const inp=document.getElementById(inputId);
  const err=document.getElementById(errId);
  if(inp) inp.classList.add('error');
  if(err){ err.textContent=msg; err.classList.add('show'); }
}
async function submitAuth(){
  hideAuthErrors();
  const email=document.getElementById('authEmail').value.trim();
  const pass=document.getElementById('authPass').value;
  const name=document.getElementById('authName').value.trim();
  let hasErr=false;
  if(!email){ showFieldError('authEmail','emailError','Email is required'); hasErr=true; }
  else if(!validateEmail(email)){ showFieldError('authEmail','emailError','Enter valid email'); hasErr=true; }
  if(!pass){ showFieldError('authPass','passError','Password is required'); hasErr=true; }
  else if(pass.length<6){ showFieldError('authPass','passError','Password must be ≥6 characters'); hasErr=true; }
  if(authMode==='register' && !name){ showFieldError('authName','nameError','Name is required for new account'); hasErr=true; }
  if(hasErr) return;

  const btn=document.getElementById('authSubmit');
  btn.disabled=true; const orig=btn.textContent; btn.textContent= authMode==='login' ? '⟳ Logging in…' : '⟳ Creating…'; btn.classList.add('btn-loading');
  document.getElementById('authLoading').style.display='block';
  document.getElementById('authLoading').textContent= authMode==='login' ? 'Verifying securely…' : 'Creating your workspace…';

  try{
    const url = authMode==="login" ? `${API}/api/login` : `${API}/api/register`;
    const body = authMode==="login" ? {email,password:pass} : {email,password:pass,name};
    const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error|| (authMode==='login'?'Invalid email or password':'Registration failed'));
    // success
    localStorage.setItem('nare_token', j.token);
    localStorage.setItem('nare_user', JSON.stringify(j.user));
    if(document.getElementById('rememberMe').checked){
      localStorage.setItem('nare_remember','1');
    }
    document.getElementById('authSuccess').textContent= authMode==='login' ? `Welcome back, ${j.user.email}` : `Account created! Welcome, ${j.user.name||j.user.email}`;
    document.getElementById('authSuccess').classList.add('show');
    toast(authMode==='login' ? `Logged in as ${j.user.email}` : `Account created — logged in`);
    setTimeout(()=>{
      closeModal('authModal');
      updateAuthUI();
      if(authMode==='register'){
        // after register, encourage first QR
        document.getElementById('generateBtn')?.scrollIntoView({behavior:'smooth', block:'center'});
      }
    }, 700);
  }catch(e){
    const errEl=document.getElementById('authError');
    errEl.textContent=e.message;
    errEl.classList.add('show');
    // map common errors to fields
    if(e.message.toLowerCase().includes('email already')) showFieldError('authEmail','emailError',e.message);
    if(e.message.toLowerCase().includes('invalid credentials')) showFieldError('authPass','passError',e.message);
  } finally {
    btn.disabled=false; btn.textContent=orig; btn.classList.remove('btn-loading');
    document.getElementById('authLoading').style.display='none';
  }
}
function updateAuthUI(){
  const token=localStorage.getItem('nare_token');
  const userStr=localStorage.getItem('nare_user');
  const loginBtn=document.getElementById('loginBtn');
  const regBtn=document.getElementById('registerBtn');
  const navDash=document.getElementById('navDash');
  if(token && userStr){
    try{
      const u=JSON.parse(userStr);
      loginBtn.textContent="Log Out";
      loginBtn.onclick=()=>{ localStorage.removeItem('nare_token'); localStorage.removeItem('nare_user'); toast("Logged out"); setTimeout(()=>location.reload(), 500); };
      regBtn.textContent="Dashboard →";
      regBtn.onclick=()=>location.href="/dashboard";
      if(navDash) navDash.style.display="inline-flex";
    }catch{}
  } else {
    loginBtn.textContent="Log In";
    loginBtn.onclick=()=>openAuth('login');
    regBtn.textContent="Register — Free";
    regBtn.onclick=()=>openAuth('register');
    if(navDash) navDash.style.display="none";
  }
}
function toast(msg, isErr=false){
  const t=document.getElementById('toast');
  t.textContent= (isErr?"⚠ ":"✔ ")+msg;
  t.classList.add('show');
  t.style.background=isErr?"#DC2626":"var(--black)";
  t.style.borderColor=isErr?"#FCA5A5":"#333";
  clearTimeout(t._hide);
  t._hide=setTimeout(()=>t.classList.remove('show'), 3200);
}

// Init
document.addEventListener('DOMContentLoaded', ()=>{
  renderTypeGrid("all");
  renderForm();
  preview();
  updateAuthUI();

  // check needAuth param
  const params=new URLSearchParams(location.search);
  if(params.get('needAuth')){
    openAuth('login');
    document.getElementById('authError').textContent="Please log in to view Dashboard";
    document.getElementById('authError').classList.add('show');
  }

  document.querySelectorAll('[data-filter]').forEach(p=>{
    p.onclick=()=>{ document.querySelectorAll('[data-filter]').forEach(x=>x.classList.remove('active')); p.classList.add('active'); renderTypeGrid(p.dataset.filter); }
  });

  const tog=document.getElementById('dynamicToggle');
  if(tog){
    tog.addEventListener('change', ()=>{
      state.isDynamic=tog.checked;
      document.getElementById('toggleBg').style.background= tog.checked ? "var(--neon)" : "#333";
      document.getElementById('toggleKnob').style.transform= tog.checked ? "translateX(22px)" : "translateX(0)";
      document.getElementById('toggleKnob').style.background= tog.checked ? "var(--black)" : "white";
      renderForm();
      updatePreviewMeta();
      preview();
    });
  }

  document.getElementById('generateBtn').onclick=generate;
  document.getElementById('resetBtn').onclick=()=>{
    state.logoB64=null;
    const prev=document.getElementById('logoPreview');
    if(prev) prev.style.display="none";
    const inp=document.getElementById('logoInput');
    if(inp) inp.value="";
    renderForm();
    preview();
    const bar=document.getElementById('genSuccess');
    if(bar) bar.style.display="none";
    toast("Reset");
  };

  document.querySelectorAll('#customTabs button').forEach(b=>{
    b.onclick=()=>{
      document.querySelectorAll('#customTabs button').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      document.querySelectorAll('.custom-pane').forEach(p=>p.style.display="none");
      const pane=document.getElementById('pane-'+b.dataset.tab);
      if(pane) pane.style.display="block";
    }
  });

  document.querySelectorAll('[data-pattern]').forEach(b=>{
    b.onclick=()=>{ document.querySelectorAll('[data-pattern]').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.pattern=b.dataset.pattern; preview(); };
  });
  document.querySelectorAll('[data-eye]').forEach(b=>{
    b.onclick=()=>{ document.querySelectorAll('[data-eye]').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.eyeStyle=b.dataset.eye; preview(); };
  });
  document.querySelectorAll('[data-gradient]').forEach(b=>{
    b.onclick=()=>{ document.querySelectorAll('[data-gradient]').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.gradient=b.dataset.gradient; preview(); };
  });

  const fg=document.getElementById('fgColor'), bg=document.getElementById('bgColor');
  const fgt=document.getElementById('fgText'), bgt=document.getElementById('bgText');
  if(fg){
    fg.oninput=()=>{ if(fgt) fgt.value=fg.value; state.fg=fg.value; preview(); };
    bg.oninput=()=>{ if(bgt) bgt.value=bg.value; state.bg=bg.value; preview(); };
    if(fgt) fgt.onchange=()=>{ state.fg=fgt.value; fg.value=fgt.value; preview(); };
    if(bgt) bgt.onchange=()=>{ state.bg=bgt.value; bg.value=bgt.value; preview(); };
  }
  document.querySelectorAll('[data-preset]').forEach(b=>{
    b.onclick=()=>{ const [f,back]=b.dataset.preset.split(','); state.fg=f; state.bg=back; if(fg) fg.value=f; if(bg) bg.value=back; if(fgt) fgt.value=f; if(bgt) bgt.value=back; preview(); toast("Preset applied"); };
  });

  // Logo - enhanced with drag & validation
  const logoInput=document.getElementById('logoInput');
  const dropZone=document.getElementById('logoDropZone');
  function handleLogoFile(file){
    if(!file) return;
    const validTypes=['image/png','image/jpeg','image/jpg','image/webp','image/svg+xml'];
    if(!validTypes.includes(file.type) && !file.name.match(/\.(png|jpg|jpeg|webp|svg)$/i)){
      toast("Invalid file type — use PNG/JPG/WebP/SVG", true);
      return;
    }
    if(file.size > 5*1024*1024){
      toast("File too large — max 5MB", true);
      return;
    }
    const reader=new FileReader();
    reader.onload=ev=>{
      state.logoB64=ev.target.result;
      const thumb=document.getElementById('logoThumb');
      const prev=document.getElementById('logoPreview');
      if(thumb) thumb.src=state.logoB64;
      if(prev) prev.style.display="grid";
      preview();
      toast("Logo added — centered at 22%");
    };
    reader.readAsDataURL(file);
  }
  if(logoInput){
    logoInput.onchange=e=>{
      const file=e.target.files[0];
      handleLogoFile(file);
    };
  }
  if(dropZone){
    dropZone.ondragover=e=>{ e.preventDefault(); dropZone.style.borderColor='var(--neon)'; dropZone.style.background='rgba(0,255,136,0.08)'; };
    dropZone.ondragleave=()=>{ dropZone.style.borderColor='var(--black)'; dropZone.style.background='var(--grid-white)'; };
    dropZone.ondrop=e=>{
      e.preventDefault();
      dropZone.style.borderColor='var(--black)'; dropZone.style.background='var(--grid-white)';
      const file=e.dataTransfer.files[0];
      handleLogoFile(file);
    };
  }
  const removeBtn=document.getElementById('removeLogo');
  if(removeBtn){
    removeBtn.onclick=()=>{ state.logoB64=null; if(logoInput) logoInput.value=""; const prev=document.getElementById('logoPreview'); if(prev) prev.style.display="none"; preview(); toast("Logo removed"); };
  }

  const frameTextEl=document.getElementById('frameText');
  if(frameTextEl) frameTextEl.oninput=e=>{ state.frameText=e.target.value; preview(); };
  const frameColorEl=document.getElementById('frameColor');
  if(frameColorEl) frameColorEl.oninput=e=>{ state.frameColor=e.target.value; preview(); };
  document.querySelectorAll('[data-frame]').forEach(b=>{
    b.onclick=()=>{
      const val=b.dataset.frame;
      const inp=document.getElementById('frameText');
      if(inp) inp.value=val;
      state.frameText=val;
      preview();
      // switch to frame tab visually
      document.querySelectorAll('#customTabs button').forEach(x=>x.classList.remove('active'));
      const ft=document.querySelector('[data-tab="frame"]');
      if(ft) ft.classList.add('active');
      document.querySelectorAll('.custom-pane').forEach(p=>p.style.display="none");
      const pane=document.getElementById('pane-frame');
      if(pane) pane.style.display="block";
    };
  });

  document.querySelectorAll('[data-template]').forEach(b=>{
    b.onclick=()=>{
      const t=b.dataset.template;
      if(t==="neon"){ state.fg="#0A0A0A"; state.bg="#FFFFFF"; state.pattern="dots"; state.eyeStyle="circle"; state.frameText="SCAN ME • NARE & CO."; state.frameColor="#00FF88"; }
      if(t==="mono"){ state.fg="#0A0A0A"; state.bg="#FFFFFF"; state.pattern="square"; state.eyeStyle="square"; state.frameText=""; }
      if(t==="grid"){ state.fg="#1A1A1A"; state.bg="#F8F9FA"; state.pattern="gapped"; state.eyeStyle="rounded"; }
      if(t==="neonBlack"){ state.fg="#00FF88"; state.bg="#0A0A0A"; state.pattern="rounded"; state.eyeStyle="circle"; state.frameText="NARE & CO. — SCAN"; state.frameColor="#00FF88"; }
      if(fg) fg.value=state.fg; if(bg) bg.value=state.bg; if(fgt) fgt.value=state.fg; if(bgt) bgt.value=state.bg;
      const ft=document.getElementById('frameText');
      const fc=document.getElementById('frameColor');
      if(ft) ft.value=state.frameText;
      if(fc) fc.value=state.frameColor;
      preview(); toast(`Template: ${t}`);
    };
  });
  const saveTpl=document.getElementById('saveTemplateBtn');
  if(saveTpl){
    saveTpl.onclick=async()=>{
      const token=localStorage.getItem('nare_token');
      if(!token){ toast("Log in to save templates", true); openAuth('login'); return; }
      saveTpl.disabled=true; saveTpl.textContent="Saving…";
      try{
        const r=await fetch(`${API}/api/templates`,{method:"POST",headers:{"Content-Type":"application/json","Authorization":`Bearer ${token}`},body:JSON.stringify({name:`Template ${Date.now()}`,config:state})});
        if(r.ok) toast("Template saved to your account");
        else { const j=await r.json(); throw new Error(j.error); }
      }catch(e){ toast(e.message, true); }
      finally{ saveTpl.disabled=false; saveTpl.textContent="Save as Template"; }
    };
  }

  document.querySelectorAll('[data-dl]').forEach(b=>{
    b.onclick=()=>{
      const fmt=b.dataset.dl;
      if(state.lastId){
        const token=localStorage.getItem('nare_token');
        if(token){
          window.location=`${API}/api/download/${state.lastId}?format=${fmt}&token=${token}`;
          return;
        }
      }
      if(state.lastImage) download(state.lastImage, `NARE-CO-${fmt}-${Date.now()}.${fmt==='pdf'?'pdf':'png'}`);
      else toast("Generate a QR first", true);
    };
  });
  const dlBtn=document.getElementById('downloadBtn');
  if(dlBtn){
    dlBtn.onclick=()=>{
      if(state.lastImage) download(state.lastImage, `NARE-CO-QR-${Date.now()}.png`);
      else toast("Generate a QR first!", true);
    };
  }

  // Auth wiring
  document.getElementById('loginBtn').onclick=()=>openAuth('login');
  document.getElementById('registerBtn').onclick=()=>openAuth('register');
  document.getElementById('authSubmit').onclick=submitAuth;
  document.getElementById('switchAuth').onclick=e=>{ e.preventDefault(); openAuth(authMode==="login"?"register":"login"); };
  document.getElementById('togglePass').onclick=()=>{
    const inp=document.getElementById('authPass');
    const btn=document.getElementById('togglePass');
    if(inp.type==='password'){ inp.type='text'; btn.textContent='🙈'; } else { inp.type='password'; btn.textContent='👁'; }
  };
  // Enter to submit
  ['authEmail','authPass','authName'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.addEventListener('keydown', e=>{ if(e.key==='Enter') submitAuth(); });
  });
  document.getElementById('authModal').onclick=e=>{ if(e.target.id==="authModal") closeModal('authModal'); };
  document.getElementById('demoModal').onclick=e=>{ if(e.target.id==="demoModal") closeModal('demoModal'); };
  const ham=document.getElementById('ham');
  if(ham){
    ham.onclick=()=>{
      const nav=document.getElementById('nav');
      const isFlex=nav.style.display==="flex";
      if(isFlex){
        nav.style.display="none";
      } else {
        nav.style.display="flex";
        nav.style.position="absolute"; nav.style.top="64px"; nav.style.right="16px"; nav.style.background="white"; nav.style.border="1.5px solid var(--black)"; nav.style.borderRadius="16px"; nav.style.padding="12px"; nav.style.flexDirection="column"; nav.style.boxShadow="6px 6px 0 var(--black)"; nav.style.zIndex="60";
      }
    };
  }
  // Forgot link
  const forgot=document.getElementById('forgotLink');
  if(forgot) forgot.onclick=e=>{ e.preventDefault(); toast("Password reset — contact support@nareandco.com", true); };
});
