const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../agent/index.html'),'utf8');
const code=html.split('/* VOICE_CONTROLLER */')[1].split('</script>')[0];
async function setup(supported=true){
 const elements={},timers=new Map(),events={};let next=0,created=[],spoken=[];
 const $=id=>elements[id]??={textContent:'',value:'',disabled:false,checked:false,classList:{add(){},remove(){}},click(){ctx.sent++;ctx.pauseVoice();}};
 class Recognition{static async available(){return 'available'}start(){assert.equal(this.processLocally,true)}abort(){this.aborted=true}}
 Recognition.prototype.processLocally=false;
 const ctx={$,bearer:'test',job:null,sent:0,document:{hidden:false,addEventListener(n,f){events[n]=f}},window:{speechSynthesis:{cancel(){},getVoices(){return [{lang:'zh-CN',localService:true}]},speak(u){spoken.push(u)}}},SpeechSynthesisUtterance:class{constructor(text){this.text=text}},setTimeout(f){timers.set(++next,f);return next},clearTimeout(i){timers.delete(i)}};
 if(supported){ctx.window.SpeechRecognition=class extends Recognition{constructor(){super();created.push(this)}};}
 vm.createContext(ctx);vm.runInContext(code,ctx);await Promise.resolve();await Promise.resolve();
 function result(text){const r=created.at(-1),row=[{transcript:text}];row.isFinal=true;r.onresult({resultIndex:0,results:[row]});}
 return {ctx,$,created,spoken,events,result};
}
(async()=>{
 let t=await setup(false);assert(t.$('startWake').disabled);t.ctx.beginVoice('wake');assert.equal(t.created.length,0);
 t=await setup();t.ctx.beginVoice('wake');assert.equal(t.created.length,1);t.result('普通对话');assert.equal(t.ctx.sent,0);t.result('小千，今天做什么');assert.equal(t.ctx.sent,1);assert.equal(t.$('prompt').value,'今天做什么');assert(t.created[0].aborted);
 t.ctx.stopVoice();t.ctx.beginVoice('dictate');t.result('测试草稿');assert.equal(t.$('prompt').value,'测试草稿');assert.equal(t.ctx.sent,1);
 t.ctx.beginVoice('wake');t.ctx.speakText('你好');assert(t.created.at(-1).aborted);assert.equal(t.spoken.length,1);assert(t.spoken[0].voice.localService);
 t.ctx.document.querySelectorAll=()=>[{textContent:'历史回答'}];t.$('answer').textContent='';t.$('speakAnswer').onclick();assert.equal(t.spoken.at(-1).text,'历史回答');
 t.ctx.stopVoice();t.ctx.beginVoice('wake');t.ctx.document.hidden=true;t.events.visibilitychange();assert(t.created.at(-1).aborted);assert.equal(t.$('voicePreview').textContent,'');
 t.ctx.document.hidden=false;t.ctx.bearer='';const n=t.created.length;t.ctx.beginVoice('wake');assert.equal(t.created.length,n);
 console.log('VOICE_TEST_OK: fail closed, local-only ASR/TTS, wake routing, dictation draft, feedback prevention, hide/lock guards');
})().catch(e=>{console.error(e);process.exitCode=1});
