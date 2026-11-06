// Web Audio player for source panels. Expects a global L of UI labels.
// Clock: displayed time = clip_start + (saved offset + AudioContext.currentTime - playback start).
// Buffer source nodes are one-shot: pause stops the node, resume/seek creates a new one.
let activePanel=null, audioContext=null, sourceNode=null;
let playing=false, offset=0, startedAt=0, playRequest=0;
const panels=[...document.querySelectorAll('.source-panel')];
function formatTime(seconds){const n=Math.max(0,Math.floor(seconds));return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(v=>String(v).padStart(2,'0')).join(':');}
function position(){return offset+(playing?audioContext.currentTime-startedAt:0);}
function update(){if(!activePanel)return;const absolute=Math.min(Number(activePanel.dataset.clipEnd),Number(activePanel.dataset.clipStart)+position());activePanel.querySelector('.global-time').textContent=formatTime(absolute);activePanel.querySelector('.timeline').value=absolute;activePanel.querySelector('.toggle-play').textContent=playing?L.pause:L.play;}
function status(text){if(activePanel)activePanel.querySelector('.playback-status').textContent=text;}
function bytes(panel){if(!panel._bytes)panel._bytes=Uint8Array.from(atob(panel.querySelector('.clip-bytes').textContent.trim()),c=>c.charCodeAt(0));return panel._bytes;}
function pause(){playRequest++;offset=position();playing=false;if(sourceNode){sourceNode.onended=null;sourceNode.stop();sourceNode.disconnect();sourceNode=null;}update();status(L.paused);}
async function play(){
 if(!activePanel||playing)return;
 const panel=activePanel, request=++playRequest;
 try{
  const Context=window.AudioContext||window.webkitAudioContext;
  if(!Context)throw new Error(L.noaudio);
  if(!audioContext)audioContext=new Context();
  await audioContext.resume();
  if(audioContext.state!=='running')throw new Error(L.blocked);
  status(L.loading);
  if(!panel._audioBuffer)panel._audioBuffer=await audioContext.decodeAudioData(bytes(panel).slice().buffer);
  if(request!==playRequest||panel!==activePanel)return;
  if(offset>=panel._audioBuffer.duration-.02)offset=Number(panel.dataset.start)-Number(panel.dataset.clipStart);
  const node=audioContext.createBufferSource();node.buffer=panel._audioBuffer;node.connect(audioContext.destination);
  sourceNode=node;startedAt=audioContext.currentTime;playing=true;
  node.onended=()=>{if(sourceNode!==node)return;offset=node.buffer.duration;playing=false;sourceNode=null;node.disconnect();update();status(L.ended);};
  node.start(0,Math.max(0,offset));update();status(L.playing);
 }catch(error){
  if(request!==playRequest||panel!==activePanel)return;
  playing=false;update();status(L.failed+error.name+' — '+error.message+L.fallback);
 }
}
function seek(absolute){const resume=playing;pause();offset=Math.max(0,Math.min(Number(activePanel.dataset.clipEnd)-Number(activePanel.dataset.clipStart),absolute-Number(activePanel.dataset.clipStart)));update();if(resume)play();}
function activate(panel,autoplay){pause();activePanel=panel;offset=Number(panel.dataset.start)-Number(panel.dataset.clipStart);panel.querySelector('.custom-controls').hidden=false;update();status(L.located+formatTime(Number(panel.dataset.start)));if(autoplay)play();}
for(const panel of panels){
 panel.querySelector('.toggle-play').addEventListener('click',()=>{if(playing)pause();else play();});
 panel.querySelector('.timeline').addEventListener('input',event=>seek(Number(event.target.value)));
 panel.querySelector('.download-clip')?.addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([bytes(panel)],{type:'audio/mpeg'}));const link=document.createElement('a');link.href=url;link.download='meeting-'+formatTime(Number(panel.dataset.start)).replaceAll(':','-')+'.mp3';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
}
// Internal links update location.hash in place: default fragment navigation can leave a srcdoc preview.
for(const link of document.querySelectorAll('a[data-source]')){link.addEventListener('click',event=>{event.preventDefault();const panel=document.getElementById(link.dataset.source);const from=link.closest('section');panel.querySelector('.close-source').href=from?'#'+from.id:'#overview';activate(panel,true);location.hash=link.getAttribute('href');});}
for(const link of document.querySelectorAll('a[href^="#"]:not([data-source])')){link.addEventListener('click',event=>{event.preventDefault();if(activePanel)pause();location.hash=link.getAttribute('href');});}
function followHash(){const panel=document.getElementById(location.hash.slice(1));if(panel&&panel.classList.contains('source-panel')){if(panel!==activePanel)activate(panel,false);}else{pause();activePanel=null;}}
setInterval(()=>{if(playing)update();},100);
addEventListener('hashchange',followHash);
addEventListener('keydown',event=>{if(event.key==='Escape'&&activePanel){pause();location.hash=activePanel.querySelector('.close-source').getAttribute('href');}});
addEventListener('pagehide',()=>pause());followHash();
