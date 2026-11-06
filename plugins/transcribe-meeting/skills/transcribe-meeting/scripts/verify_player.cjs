// Playback test of meeting-summary.html inside a restricted preview:
// srcdoc iframe, sandbox="allow-scripts" (opaque origin), CSP media-src/connect-src 'none'.
// Usage: node verify_player.cjs OUT_DIR [--chrome /path/to/chrome-or-headless-shell]
// Needs Node 18+, the `ws` package (or Node 22+ global WebSocket), and a headless
// Chromium (CHROME_BIN, --chrome, Playwright's cache, or chromium/google-chrome on PATH).
// Asserts: every summary row links to a resolvable source panel; no <audio> elements;
// for the first, middle and last panels the clip decodes to a nonzero signal, the audio
// context runs and the ORIGINAL-clock position advances; pause freezes; seek lands;
// resume advances; close stops playback. Also shows that a media-URL <audio> is blocked.
const fs=require('fs'),path=require('path'),os=require('os'),{spawn,execSync}=require('child_process');
let WebSocket;try{WebSocket=require('ws');}catch{WebSocket=globalThis.WebSocket;}
if(!WebSocket)throw new Error('Need the ws package (npm i ws) or Node 22+');
// Accepts the output folder (tests meeting-summary.html) or a page path (e.g. the library variant).
const target=path.resolve(process.argv[2]||'.');
const page=target.endsWith('.html')?target:path.join(target,'meeting-summary.html');
const out=target.endsWith('.html')?path.dirname(target):target;
const flag=process.argv.indexOf('--chrome');
function findChrome(){
 if(flag>0)return process.argv[flag+1];
 if(process.env.CHROME_BIN)return process.env.CHROME_BIN;
 const cache=path.join(os.homedir(),'.cache/ms-playwright');
 if(fs.existsSync(cache))for(const d of fs.readdirSync(cache).sort().reverse()){
  for(const rel of ['chrome-headless-shell-linux64/chrome-headless-shell','chrome-linux/chrome','chrome-linux64/chrome']){const p=path.join(cache,d,rel);if(fs.existsSync(p))return p;}}
 for(const name of ['chromium','chromium-browser','google-chrome','chrome-headless-shell']){try{return execSync('command -v '+name,{shell:'/bin/bash'}).toString().trim();}catch{}}
 throw new Error('No headless Chromium found; pass --chrome PATH');
}
const bin=findChrome(),dir=path.dirname(bin),env={...process.env};delete env.DISPLAY;
if(fs.existsSync(dir+'/vk_swiftshader_icd.json')){env.LD_LIBRARY_PATH='';env.VK_ICD_FILENAMES=env.VK_DRIVER_FILES=dir+'/vk_swiftshader_icd.json';}
// No autoplay override: playback must start from the (CDP-simulated) user click, as in a real preview.
const flags=['--no-sandbox','--disable-gpu','--ozone-platform=headless','--use-angle=swiftshader','--disable-background-networking','--remote-debugging-port=0','about:blank'];
if(!/headless-shell/.test(bin))flags.unshift('--headless=new');
const browser=spawn(bin,flags,{env});
let ws;const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const address=await new Promise((resolve,reject)=>{let err='';const t=setTimeout(()=>reject(new Error('Browser startup timeout: '+err.slice(-500))),20000);browser.stderr.on('data',b=>{err+=b;const m=err.match(/DevTools listening on (ws:\/\/\S+)/);if(m){clearTimeout(t);resolve(m[1]);}});});
 const targets=await(await fetch('http://127.0.0.1:'+new URL(address).port+'/json/list')).json();
 ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>ws.addEventListener?ws.addEventListener('open',r,{once:true}):ws.once('open',r));
 let id=0;const pending=new Map(),contexts=new Map();
 const onMessage=raw=>{const m=JSON.parse(raw.data??raw);
  if(m.method==='Runtime.executionContextsCleared')contexts.clear();
  if(m.method==='Runtime.executionContextCreated'&&m.params.context.auxData?.isDefault)contexts.set(m.params.context.auxData.frameId,m.params.context.id);
  if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}};
 ws.addEventListener?ws.addEventListener('message',onMessage):ws.on('message',onMessage);
 const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 const evaluate=async(expression,contextId)=>{const r=await call('Runtime.evaluate',{expression,contextId,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails).slice(0,800));return r.result.value;};
 await call('Page.enable');await call('Runtime.enable');
 await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
 const main=(await call('Page.getFrameTree')).frameTree.frame.id;
 await call('Page.setDocumentContent',{frameId:main,html:'<html><body style="margin:0"><iframe id="preview" sandbox="allow-scripts" style="width:100vw;height:100vh;border:0"></iframe></body></html>'});
 const policy="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'none'; connect-src 'none'";
 const html=fs.readFileSync(page,'utf8').replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="'+policy+'">');
 await evaluate('document.getElementById("preview").srcdoc='+JSON.stringify(html)+';true;');
 let ctx;
 for(let n=0;n<100&&!ctx;n++){const child=(await call('Page.getFrameTree')).frameTree.childFrames?.find(f=>f.frame.url==='about:srcdoc');
  if(child&&contexts.has(child.frame.id)){try{if(await evaluate("typeof play==='function'&&document.querySelectorAll('.source-panel').length>0",contexts.get(child.frame.id)))ctx=contexts.get(child.frame.id);}catch{}}
  await sleep(100);}
 if(!ctx)throw new Error('Sandboxed preview did not load');
 const run=e=>evaluate(e,ctx);
 const structure=await run(`({opaqueOrigin:origin==='null',audioElements:document.querySelectorAll('audio').length,panels:document.querySelectorAll('.source-panel').length,rows:document.querySelectorAll('[data-summary-row]').length,allRowsLinked:[...document.querySelectorAll('[data-summary-row]')].every(r=>r.querySelector('a[data-source]')),allLinksResolve:[...document.querySelectorAll('a[data-source]')].every(a=>document.getElementById(a.getAttribute('href').slice(1)))})`);
 if(structure.audioElements||!structure.allRowsLinked||!structure.allLinksResolve||!structure.rows)throw new Error('Structure failed '+JSON.stringify(structure));
 const mediaUrl=await run(`(async()=>{const p=document.querySelector('.source-panel');const a=new Audio('data:audio/mpeg;base64,'+p.querySelector('.clip-bytes').textContent.trim().slice(0,4000));const r=await Promise.race([a.play().then(()=>'played',e=>e.name),new Promise(r=>a.onerror=()=>r('error '+(a.error&&a.error.code))),new Promise(r=>setTimeout(()=>r('timeout'),3000))]);a.pause();return r;})()`);
 const ids=await run(`[...document.querySelectorAll('.source-panel')].map(p=>p.id)`);
 const pick=[...new Set([ids[0],ids[Math.floor(ids.length/2)],ids[ids.length-1]])];
 const cases=[];
 for(const i of pick){
  const c=await run(`(async()=>{document.querySelector('a[data-source="${i}"]').click();await new Promise(r=>setTimeout(r,1200));const p=document.getElementById('${i}');const b=p._audioBuffer;let rms=0;if(b){const a=b.getChannelData(0);for(let j=0;j<a.length;j+=32)rms+=a[j]*a[j];rms=Math.sqrt(rms/Math.ceil(a.length/32));}return {id:'${i}',panel:getComputedStyle(p).display,context:audioContext&&audioContext.state,playing,expectedStart:Number(p.dataset.start),originalTime:Number(p.dataset.clipStart)+position(),displayed:p.querySelector('.global-time').textContent,decodedSeconds:b&&b.duration,rms,status:p.querySelector('.playback-status').textContent}})()`);
  if(c.context!=='running'||!c.playing||c.panel!=='flex'||!(c.rms>1e-6)||c.originalTime<c.expectedStart+.2||c.originalTime>c.expectedStart+4)throw new Error('Playback failed '+JSON.stringify(c));
  cases.push(c);
 }
 const last=pick[pick.length-1];
 const paused=await run(`(async()=>{document.querySelector('#${last} .toggle-play').click();const a=position();await new Promise(r=>setTimeout(r,400));return {playing,before:a,after:position()}})()`);
 if(paused.playing||Math.abs(paused.after-paused.before)>.01)throw new Error('Pause failed '+JSON.stringify(paused));
 const seeking=await run(`(()=>{const p=document.getElementById('${last}'),r=p.querySelector('.timeline');r.value=Math.min(Number(p.dataset.clipEnd)-1,Number(p.dataset.start)+3);r.dispatchEvent(new Event('input',{bubbles:true}));return {playing,target:Number(r.value),actual:Number(p.dataset.clipStart)+position(),displayed:p.querySelector('.global-time').textContent}})()`);
 if(seeking.playing||Math.abs(seeking.target-seeking.actual)>.01)throw new Error('Seek failed '+JSON.stringify(seeking));
 const resumed=await run(`(async()=>{document.querySelector('#${last} .toggle-play').click();await new Promise(r=>setTimeout(r,600));return {playing,actual:Number(activePanel.dataset.clipStart)+position()}})()`);
 if(!resumed.playing||resumed.actual<seeking.target+.3)throw new Error('Resume failed '+JSON.stringify(resumed));
 const shot=await call('Page.captureScreenshot',{format:'png'});const logs=target.endsWith('.html')?out:path.join(out,'logs');fs.mkdirSync(logs,{recursive:true});
 fs.writeFileSync(path.join(logs,'player-preview.png'),Buffer.from(shot.data,'base64'));
 await run(`document.querySelector('#${last} .close-source').click()`);await sleep(150);
 const closed=await run("({playing,source:!!sourceNode,visible:[...document.querySelectorAll('.source-panel')].filter(p=>getComputedStyle(p).display!=='none').length})");
 if(closed.playing||closed.source||closed.visible)throw new Error('Close failed '+JSON.stringify(closed));
 const result={browser:bin,preview:'srcdoc iframe, sandbox=allow-scripts, CSP '+policy,structure,mediaUrlAudioUnderPolicy:mediaUrl,cases,paused,seeking,resumed,closed,passed:true,
  limit:'Passing here does not prove every host preview permits Web Audio or downloads.'};
 fs.writeFileSync(path.join(logs,'player-verification.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error('PLAYER_TEST_FAILED',e.message||e);process.exitCode=1;}).finally(()=>{try{ws&&ws.close();}catch{}browser.kill();});
