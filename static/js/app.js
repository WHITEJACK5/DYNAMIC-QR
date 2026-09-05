// NARE & CO. - Frontend Logic - Grid White / Black / Neon Green
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
  lastId: null
};

const TYPES = [
  {id:"url", label:"URL", icon:"🔗", cat:"popular", desc:"Website link"},
  {id:"vcard", label:"vCard", icon:"👤", cat:"business", desc:"Contact card"},
  {id:"file", label:"File", icon:"📄", cat:"business", desc:"PDF/Img/Doc"},
  {id:"linkpage", label:"Link Page", icon:"🌐", cat:"social", desc:"Bio link"},
  {id:"menu", label:"Menu", icon:"🍽️", cat:"business", desc:"Restaurant"},
  {id:"appstore", label:"App Stores", icon:"📱", cat:"business", desc:"Store links"},
  {id:"landingpage", label:"Landing", icon:"▣", cat:"business", desc:"Custom page"},
  {id:"smarturl", label:"Smart URL", icon:"🧠", cat:"utility", desc:"Multi-URL"},
  {id:"gs1", label:"GS1", icon:"🏷️", cat:"business", desc:"Digital Link"},
  {id:"mp3", label:"MP3", icon:"🎵", cat:"utility", desc:"Audio"},
  {id:"video", label:"Video", icon:"▶", cat:"social", desc:"YouTube etc"},
  {id:"wifi", label:"WiFi", icon:"📶", cat:"utility", desc:"Connect"},
  {id:"email", label:"Email", icon:"✉", cat:"utility", desc:"Mailto"},
  {id:"whatsapp", label:"WhatsApp", icon:"💬", cat:"social", desc:"Chat"},
  {id:"event", label:"Event", icon:"📅", cat:"business", desc:"Calendar"},
  {id:"facebook", label:"Facebook", icon:"f", cat:"social", desc:"Social"},
  {id:"youtube", label:"YouTube", icon:"▶", cat:"social", desc:"Channel"},
  {id:"instagram", label:"Instagram", icon:"◎", cat:"social", desc:"Profile"},
  {id:"pinterest", label:"Pinterest", icon:"P", cat:"social", desc:"Board"},
  {id:"tiktok", label:"TikTok", icon:"♪", cat:"social", desc:"Profile"},
  {id:"twitter", label:"Twitter", icon:"𝕏", cat:"social", desc:"X / Twitter"},
  {id:"location", label:"Location", icon:"📍", cat:"utility", desc:"Map geo"},
  {id:"text", label:"Text", icon:"T", cat:"utility", desc:"Plain text"},
  {id:"sms", label:"SMS", icon:"💬", cat:"utility", desc:"Text msg"},
  {id:"googleform", label:"G Form", icon:"📝", cat:"business", desc:"Google Form"},
  {id:"googlereview", label:"G Review", icon:"⭐", cat:"business", desc:"Review"},
];

const FORM_DEFS = {
  url: [{key:"url", label:"Enter the URL of your website", placeholder:"https://www.nareandco.com", type:"url"}],
  text: [{key:"text", label:"Your Text", placeholder:"Enter text to encode", type:"textarea"}],
  email: [{key:"email", label:"Email address", placeholder:"hello@nareandco.com"}, {key:"subject", label:"Subject", placeholder:"Hello"}, {key:"body", label:"Message", placeholder:"Hi there!", type:"textarea"}],
  sms: [{key:"phone", label:"Phone Number", placeholder:"+919876543210"}, {key:"message", label:"Message", placeholder:"Hello!", type:"textarea"}],
  wifi: [{key:"ssid", label:"Network Name (SSID)", placeholder:"NARE-WIFI"}, {key:"password", label:"Password", placeholder:"••••••••"}, {key:"encryption", label:"Encryption", placeholder:"WPA", type:"select", opts:["WPA","WEP","nopass"]}, {key:"hidden", label:"Hidden?", type:"select", opts:["false","true"]}],
  vcard: [{key:"name", label:"Full Name", placeholder:"Jane Doe"}, {key:"organization", label:"Organization", placeholder:"NARE & CO."}, {key:"phone", label:"Phone", placeholder:"+91 98765 43210"}, {key:"email", label:"Email", placeholder:"jane@nareandco.com"}, {key:"url", label:"Website", placeholder:"https://nareandco.com"}, {key:"address", label:"Address", placeholder:"Hyderabad, India"}],
  whatsapp: [{key:"phone", label:"WhatsApp Number", placeholder:"+919876543210"}, {key:"message", label:"Prefilled Message", placeholder:"Hi!"}],
  location: [{key:"latitude", label:"Latitude", placeholder:"17.3850"}, {key:"longitude", label:"Longitude", placeholder:"78.4867"}],
  event: [{key:"title", label:"Event Title", placeholder:"NARE & CO. Launch"}, {key:"location", label:"Location", placeholder:"Hyderabad"}, {key:"start", label:"Start (YYYYMMDDTHHMMSSZ)", placeholder:"20260905T100000Z"}, {key:"end", label:"End", placeholder:"20260905T120000Z"}, {key:"description", label:"Description", type:"textarea", placeholder:"Join us..."}],
  file: [{key:"url", label:"File URL (upload to get URL)", placeholder:"https://example.com/file.pdf"}, {key:"note", label:"Tip", type:"help", text:"Upload PDF/JPG/PNG/MP4/Excel/Word elsewhere and paste link. Or use our File QR — we’ll host via dynamic short URL."}],
  linkpage: [{key:"title", label:"Page Title", placeholder:"NARE & CO. Links"}, {key:"bio", label:"Bio", placeholder:"Discover our world..."}, {key:"links", label:"Links (one per line: label|url)", type:"textarea", placeholder:"Instagram|https://instagram.com/nare\nShop|https://nareandco.com/shop"}],
  menu: [{key:"restaurant", label:"Restaurant Name", placeholder:"NARE Bistro"}, {key:"url", label:"Menu Link / PDF URL", placeholder:"https://nareandco.com/menu.pdf"}],
  appstore: [{key:"ios", label:"App Store (iOS) URL", placeholder:"https://apps.apple.com/..."}, {key:"android", label:"Google Play URL", placeholder:"https://play.google.com/..."}],
  landingpage: [{key:"title", label:"Landing Title", placeholder:"Summer Drop — NARE & CO."}, {key:"url", label:"Destination / Content URL", placeholder:"https://nareandco.com/drop"}],
  smarturl: [{key:"primaryUrl", label:"Default URL", placeholder:"https://nareandco.com"}, {key:"rules", label:"Rules (JSON or lines: condition→url)", type:"textarea", placeholder:"country:IN → https://in.nareandco.com\nlanguage:es → https://es.nareandco.com"}],
  gs1: [{key:"content", label:"GS1 Digital Link / GTIN Data", placeholder:"(01)09506000134352(17)240105(10)ABC123"}],
  mp3: [{key:"url", label:"MP3 / Audio URL (SoundCloud etc)", placeholder:"https://soundcloud.com/..."}],
  video: [{key:"url", label:"Video URL", placeholder:"https://youtube.com/watch?v=..."}],
  facebook: [{key:"url", label:"Facebook URL", placeholder:"https://facebook.com/nareandco"}],
  youtube: [{key:"url", label:"YouTube URL", placeholder:"https://youtube.com/@nare"}],
  instagram: [{key:"url", label:"Instagram URL", placeholder:"https://instagram.com/nare"}],
  pinterest: [{key:"url", label:"Pinterest URL", placeholder:"https://pinterest.com/nare"}],
  tiktok: [{key:"url", label:"TikTok URL", placeholder:"https://tiktok.com/@nare"}],
  twitter: [{key:"url", label:"Twitter/X URL", placeholder:"https://x.com/nare"}],
  googleform: [{key:"url", label:"Google Form URL", placeholder:"https://forms.gle/..."}],
  googlereview: [{key:"url", label:"Google Review Link", placeholder:"https://g.page/r/..."}],
};

function renderTypeGrid(filter="all"){
  const grid=document.getElementById('typeGrid');
  let list=TYPES;
  if(filter!=="all"){
    if(filter==="popular") list=TYPES.filter(t=>["url","vcard","file","wifi","instagram","whatsapp","youtube","text"].includes(t.id));
    else list=TYPES.filter(t=>t.cat===filter);
  }
  grid.innerHTML=list.map(t=>`
    <button class="type-btn ${state.type===t.id?'active':''}" data-type="${t.id}">
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
  let html = `<div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:13px">Step 1 • Enter ${state.type.toUpperCase()} details</strong><span class="badge badge-neon">${state.isDynamic?'DYNAMIC':'STATIC'}</span></div>`;
  defs.forEach(f=>{
    if(f.type==="help"){
      html+=`<div class="help">${f.text}</div>`;
      return;
    }
    if(f.type==="textarea"){
      html+=`<div class="field"><label>${f.label}</label><textarea id="f_${f.key}" rows="3" placeholder="${f.placeholder||''}"></textarea></div>`;
    } else if(f.type==="select"){
      html+=`<div class="field"><label>${f.label}</label><select id="f_${f.key}">${f.opts.map(o=>`<option value="${o}">${o}</option>`).join('')}</select></div>`;
    } else {
      html+=`<div class="field"><label>${f.label}</label><input id="f_${f.key}" type="${f.type||'text'}" placeholder="${f.placeholder||''}"></div>`;
    }
  });
  // extras
  html+=`<div class="two-col">
    <div class="field"><label>QR Name (for dashboard)</label><input id="f_name" placeholder="My ${state.type} QR — NARE"></div>
    <div class="field"><label>Campaign Folder</label><select id="f_folder"><option>My QR Codes</option><option>Marketing</option><option>Events</option></select></div>
  </div>`;
  if(state.isDynamic){
    html+=`<details style="background:var(--grid-white);border:1px solid var(--black);border-radius:12px;padding:10px"><summary style="font-weight:800;cursor:pointer">🔒 Security & Expiry (Dynamic only)</summary>
      <div class="two-col" style="margin-top:10px">
        <div class="field"><label>Password (optional)</label><input id="f_password" type="password" placeholder="Leave blank for public"></div>
        <div class="field"><label>Scan Limit</label><input id="f_scan_limit" type="number" placeholder="e.g. 1000"></div>
      </div>
      <div class="field"><label>Expiry Date (optional)</label><input id="f_expiry" type="datetime-local"></div>
    </details>`;
  }
  area.innerHTML=html;
  // bind input -> preview
  area.querySelectorAll('input,textarea,select').forEach(el=>{
    el.addEventListener('input', debounce(preview, 400));
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

function buildContentForPreview(){
  const data=collectData();
  // simple mapping for JS preview (mirror backend)
  const t=state.type;
  if(t==="url"||t==="facebook"||t==="instagram"||t==="youtube"||t==="tiktok"||t==="twitter"||t==="pinterest"||t==="video"||t==="mp3"||t==="file"||t==="googleform"||t==="googlereview"||t==="landingpage"||t==="menu"){
    let u=data.url||data.content||"https://nareandco.com";
    if(!/^https?:\/\//.test(u)) u="https://"+u;
    return u;
  }
  if(t==="text") return data.text||"Hello NARE & CO";
  if(t==="email") return `mailto:${data.email||''}?subject=${data.subject||''}&body=${data.body||''}`;
  if(t==="sms") return `SMSTO:${data.phone||''}:${data.message||''}`;
  if(t==="wifi") return `WIFI:T:${data.encryption||'WPA'};S:${data.ssid||''};P:${data.password||''};;`;
  if(t==="vcard") return `BEGIN:VCARD\nFN:${data.name||'John'}\nTEL:${data.phone||''}\nEMAIL:${data.email||''}\nEND:VCARD`;
  if(t==="whatsapp") return `https://wa.me/${data.phone||''}?text=${encodeURIComponent(data.message||'')}`;
  if(t==="location") return `geo:${data.latitude||'0'},${data.longitude||'0'}`;
  if(t==="event") return `BEGIN:VEVENT\nSUMMARY:${data.title||'Event'}\nLOCATION:${data.location||''}\nEND:VEVENT`;
  if(t==="appstore") return data.ios||data.android||"https://nareandco.com";
  return data.url||data.text||"https://nareandco.com";
}

let previewTimer=null;
function debounce(fn,ms){ return (...a)=>{ clearTimeout(previewTimer); previewTimer=setTimeout(()=>fn(...a), ms)} }

async function preview(){
  const content = buildContentForPreview();
  // Use local QR generation for instant preview (qrcodejs fallback) + backend styled when possible
  // Try backend styled preview for accurate colors/frame
  try{
    const res = await fetch(`${API}/api/preview`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
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
      document.getElementById('qrImage').src=j.image_base64;
      state.lastImage=j.image_base64;
      return;
    }
  }catch(e){}
  // fallback to quick js qr (bw)
  const holder=document.getElementById('qrImage');
  // use qrserver fallback
  holder.src=`https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(content)}&color=${state.fg.replace('#','')}&bgcolor=${state.bg.replace('#','')}`;
}

function updatePreviewMeta(){
  const el=document.getElementById('previewType');
  el.textContent=`${state.type.toUpperCase()} • ${state.isDynamic?'Dynamic':'Static'}`;
  el.style.background=state.isDynamic?'var(--neon)':'white';
}

async function generate(){
  const data=collectData();
  const nameEl=document.getElementById('f_name');
  const name=nameEl? nameEl.value.trim()||`My ${state.type} QR` : `My ${state.type} QR`;
  const btn=document.getElementById('generateBtn');
  btn.disabled=true; btn.textContent="Generating…";
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
    const token=localStorage.getItem('nare_token');
    const res=await fetch(`${API}/api/generate`,{
      method:"POST",
      headers:{"Content-Type":"application/json", ...(token?{"Authorization":`Bearer ${token}`}:{})},
      body: JSON.stringify(payload)
    });
    const j=await res.json();
    if(!res.ok) throw new Error(j.error||"Failed");
    document.getElementById('qrImage').src=j.image_base64;
    state.lastImage=j.image_base64;
    state.lastId=j.qr_id;
    toast(j.is_dynamic ? `Dynamic QR created → ${j.short_code}` : `Static QR created`);
    // Show success with download + dashboard link
    if(j.qr_id){
      // add to local list preview
    }
    // offer download
    if(confirm(`QR generated! ${j.is_dynamic?'Dynamic • Editable • Trackable':'Static'} — Download now?`)){
      download(j.image_base64, `nare-co-${state.type}-${Date.now()}.png`);
    }
  }catch(e){
    toast("Error: "+e.message, true);
  }finally{
    btn.disabled=false; btn.textContent="⚡ Generate QR Code";
  }
}

function download(dataUrl, filename){
  const a=document.createElement('a');
  a.href=dataUrl;
  a.download=filename;
  a.click();
}

// Auth
let authMode="login";
function openAuth(mode){
  authMode=mode;
  document.getElementById('authModal').classList.add('open');
  document.getElementById('authTitle').textContent= mode==="login" ? "Log In to NARE & CO." : "Create your NARE & CO. account";
  document.getElementById('nameField').style.display= mode==="register" ? "block" : "none";
  document.getElementById('authSubmit').textContent= mode==="login" ? "Log In →" : "Register — Free →";
  document.getElementById('switchAuth').textContent= mode==="login" ? "Need an account? Register" : "Have an account? Log In";
  document.getElementById('authMsg').style.display="none";
}
function closeModal(id){ document.getElementById(id).classList.remove('open'); }
function openModal(which){
  if(which==="demo") document.getElementById('demoModal').classList.add('open');
  if(which==="register") openAuth("register");
  if(which==="login") openAuth("login");
}
async function submitAuth(){
  const email=document.getElementById('authEmail').value.trim();
  const pass=document.getElementById('authPass').value.trim();
  const name=document.getElementById('authName').value.trim();
  const msg=document.getElementById('authMsg');
  if(!email||!pass){ msg.textContent="Email & password required"; msg.style.display="block"; return; }
  const url = authMode==="login" ? `${API}/api/login` : `${API}/api/register`;
  const body = authMode==="login" ? {email,password:pass} : {email,password:pass,name};
  try{
    const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error||"Auth failed");
    localStorage.setItem('nare_token', j.token);
    localStorage.setItem('nare_user', JSON.stringify(j.user));
    msg.style.display="none";
    closeModal('authModal');
    toast(`Welcome, ${j.user.email} — NARE & CO.`);
    updateAuthUI();
  }catch(e){ msg.textContent=e.message; msg.style.display="block"; }
}
function updateAuthUI(){
  const token=localStorage.getItem('nare_token');
  const user=localStorage.getItem('nare_user');
  if(token && user){
    const u=JSON.parse(user);
    document.getElementById('loginBtn').textContent="Log Out";
    document.getElementById('loginBtn').onclick=()=>{ localStorage.removeItem('nare_token'); localStorage.removeItem('nare_user'); location.reload(); };
    document.getElementById('registerBtn').textContent="Dashboard →";
    document.getElementById('registerBtn').onclick=()=>location.href="/dashboard";
    document.getElementById('navDash').style.display="inline-flex";
    // hide switch?
  } else {
    document.getElementById('loginBtn').onclick=()=>openAuth('login');
    document.getElementById('registerBtn').onclick=()=>openAuth('register');
  }
}
function toast(msg, isErr=false){
  const t=document.getElementById('toast');
  t.textContent= (isErr?"⚠ ":"✔ ")+msg;
  t.classList.add('show');
  t.style.background=isErr?"#c00":"var(--black)";
  setTimeout(()=>t.classList.remove('show'), 2600);
}

// Init
document.addEventListener('DOMContentLoaded', ()=>{
  renderTypeGrid("all");
  renderForm();
  preview();
  updateAuthUI();

  // top filter pills
  document.querySelectorAll('[data-filter]').forEach(p=>{
    p.onclick=()=>{ document.querySelectorAll('[data-filter]').forEach(x=>x.classList.remove('active')); p.classList.add('active'); renderTypeGrid(p.dataset.filter); }
  });

  // toggle dynamic
  const tog=document.getElementById('dynamicToggle');
  tog.addEventListener('change', ()=>{
    state.isDynamic=tog.checked;
    document.getElementById('toggleBg').style.background= tog.checked ? "var(--neon)" : "#333";
    document.getElementById('toggleKnob').style.transform= tog.checked ? "translateX(22px)" : "translateX(0)";
    document.getElementById('toggleKnob').style.background= tog.checked ? "var(--black)" : "white";
    renderForm();
    updatePreviewMeta();
    preview();
  });

  document.getElementById('generateBtn').onclick=generate;
  document.getElementById('resetBtn').onclick=()=>{ state.logoB64=null; document.getElementById('logoPreview').style.display="none"; renderForm(); preview(); toast("Reset"); };

  // custom tabs
  document.querySelectorAll('#customTabs button').forEach(b=>{
    b.onclick=()=>{
      document.querySelectorAll('#customTabs button').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      document.querySelectorAll('.custom-pane').forEach(p=>p.style.display="none");
      document.getElementById('pane-'+b.dataset.tab).style.display="block";
    }
  });

  // pattern
  document.querySelectorAll('[data-pattern]').forEach(b=>{
    b.onclick=()=>{ document.querySelectorAll('[data-pattern]').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.pattern=b.dataset.pattern; preview(); };
  });
  document.querySelectorAll('[data-eye]').forEach(b=>{
    b.onclick=()=>{ document.querySelectorAll('[data-eye]').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.eyeStyle=b.dataset.eye; preview(); };
  });
  document.querySelectorAll('[data-gradient]').forEach(b=>{
    b.onclick=()=>{ document.querySelectorAll('[data-gradient]').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.gradient=b.dataset.gradient; preview(); };
  });

  // colors
  const fg=document.getElementById('fgColor'), bg=document.getElementById('bgColor');
  const fgt=document.getElementById('fgText'), bgt=document.getElementById('bgText');
  fg.oninput=()=>{ fgt.value=fg.value; state.fg=fg.value; preview(); };
  bg.oninput=()=>{ bgt.value=bg.value; state.bg=bg.value; preview(); };
  fgt.onchange=()=>{ state.fg=fgt.value; fg.value=fgt.value; preview(); };
  bgt.onchange=()=>{ state.bg=bgt.value; bg.value=bgt.value; preview(); };
  document.querySelectorAll('[data-preset]').forEach(b=>{
    b.onclick=()=>{ const [f,back]=b.dataset.preset.split(','); state.fg=f; state.bg=back; fg.value=f; bg.value=back; fgt.value=f; bgt.value=back; preview(); toast("Preset applied"); };
  });

  // logo
  document.getElementById('logoInput').onchange=e=>{
    const file=e.target.files[0];
    if(!file) return;
    const reader=new FileReader();
    reader.onload=ev=>{
      state.logoB64=ev.target.result;
      document.getElementById('logoThumb').src=state.logoB64;
      document.getElementById('logoPreview').style.display="grid";
      preview();
    };
    reader.readAsDataURL(file);
  };
  document.getElementById('removeLogo').onclick=()=>{ state.logoB64=null; document.getElementById('logoInput').value=""; document.getElementById('logoPreview').style.display="none"; preview(); };

  // frame
  document.getElementById('frameText').oninput=e=>{ state.frameText=e.target.value; preview(); };
  document.getElementById('frameColor').oninput=e=>{ state.frameColor=e.target.value; preview(); };
  document.querySelectorAll('[data-frame]').forEach(b=>{
    b.onclick=()=>{ document.getElementById('frameText').value=b.dataset.frame; state.frameText=b.dataset.frame; preview(); };
  });

  // templates
  document.querySelectorAll('[data-template]').forEach(b=>{
    b.onclick=()=>{
      const t=b.dataset.template;
      if(t==="neon"){ state.fg="#0A0A0A"; state.bg="#FFFFFF"; state.pattern="dots"; state.eyeStyle="circle"; state.frameText="SCAN ME • NARE & CO."; state.frameColor="#00FF88"; }
      if(t==="mono"){ state.fg="#0A0A0A"; state.bg="#FFFFFF"; state.pattern="square"; state.eyeStyle="square"; state.frameText=""; }
      if(t==="grid"){ state.fg="#1A1A1A"; state.bg="#F8F9FA"; state.pattern="gapped"; state.eyeStyle="rounded"; }
      if(t==="neonBlack"){ state.fg="#00FF88"; state.bg="#0A0A0A"; state.pattern="rounded"; state.eyeStyle="circle"; state.frameText="NARE & CO. — SCAN"; state.frameColor="#00FF88"; }
      fg.value=state.fg; bg.value=state.bg; fgt.value=state.fg; bgt.value=state.bg;
      document.getElementById('frameText').value=state.frameText;
      document.getElementById('frameColor').value=state.frameColor;
      preview(); toast(`Template: ${t}`);
    };
  });
  document.getElementById('saveTemplateBtn').onclick=async()=>{
    const token=localStorage.getItem('nare_token');
    if(!token) return toast("Log in to save templates", true);
    const r=await fetch(`${API}/api/templates`,{method:"POST",headers:{"Content-Type":"application/json","Authorization":`Bearer ${token}`},body:JSON.stringify({name:`Template ${Date.now()}`,config:state})});
    if(r.ok) toast("Template saved");
    else toast("Failed to save", true);
  };

  // download buttons
  document.querySelectorAll('[data-dl]').forEach(b=>{
    b.onclick=async()=>{
      const fmt=b.dataset.dl;
      if(state.lastId){
        const token=localStorage.getItem('nare_token');
        if(token){
          // use backend download which respects id
          window.location=`${API}/api/download/${state.lastId}?format=${fmt}&token=${token}`;
          return;
        }
      }
      // fallback: download preview
      if(state.lastImage) download(state.lastImage, `nare-co-${fmt}.${fmt==='pdf'?'pdf':'png'}`);
      else toast("Generate first", true);
    };
  });
  document.getElementById('downloadBtn').onclick=()=>{
    if(state.lastImage) download(state.lastImage, `NARE-CO-QR-${Date.now()}.png`);
    else toast("Generate first!", true);
  };

  // auth
  document.getElementById('loginBtn').onclick=()=>openAuth('login');
  document.getElementById('registerBtn').onclick=()=>openAuth('register');
  document.getElementById('authSubmit').onclick=submitAuth;
  document.getElementById('switchAuth').onclick=e=>{ e.preventDefault(); openAuth(authMode==="login"?"register":"login"); };
  document.getElementById('authModal').onclick=e=>{ if(e.target.id==="authModal") closeModal('authModal'); };
  document.getElementById('demoModal').onclick=e=>{ if(e.target.id==="demoModal") closeModal('demoModal'); };
  document.getElementById('ham').onclick=()=>{
    const nav=document.getElementById('nav');
    nav.style.display= nav.style.display==="flex" ? "none" : "flex";
    nav.style.position="absolute"; nav.style.top="64px"; nav.style.right="16px"; nav.style.background="white"; nav.style.border="1.5px solid var(--black)"; nav.style.borderRadius="16px"; nav.style.padding="12px"; nav.style.flexDirection="column"; nav.style.boxShadow="6px 6px 0 var(--black)";
  };
});
