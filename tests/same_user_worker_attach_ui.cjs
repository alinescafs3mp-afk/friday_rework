"use strict";
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const requests=[],states=[];let cursor=0,effects=[],Component,tree,uncertain=process.argv[3]==='uncertain';
const row={platform:'telegram',transport_profile:'default',account_id:'bot-A',user_id:'1',runtime_profile:'user-1',
  principal_id:'same-owner',template:'ordinary',enabled:true,generation:3,config_sha256:'a'.repeat(64),
  recoverable:true,required_names:['LOCAL_KEY'],required_workers:[],worker_attachment:true,can_attach_workers:true,state:'ADMITTED_WORKER_SETUP_AVAILABLE'};
const React={createElement:(tag,props,...children)=>({tag,props:props||{},children}),
 useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=v];},
 useEffect:(f,deps)=>{const i=cursor++,old=states[i];if(!old||deps.some((v,j)=>v!==old[j])){states[i]=deps;effects.push(f);}}};
const context={URLSearchParams,Promise,window:{__HERMES_PLUGIN_SDK__:{React,
 fetchJSON:async(url,init={})=>{requests.push({url,...init});
  if(url.includes('/profiles'))return ['default'];
  if(url.includes('/onboarding?'))return {templates:['ordinary','friday-local'],worker_templates:['friday-local'],pending:[row],config_sha256:'a'.repeat(64)};
  if(url.includes('/workers/prepare')){if(uncertain)throw Error('offline transport uncertainty');return {enabled:true,generation:3,
   required_workers:['dsh','a0'],worker_attachment:true,can_attach_workers:false,can_prepare_workers:false,can_qualify_workers:true,
   capture_names:[],workers:{dsh:{state:'PREPARED_RUNTIME_UNOBSERVED'},a0:{state:'PREPARED_RUNTIME_UNOBSERVED'}}};}
  if(url.includes('/workers/qualify'))return {enabled:true,state:'ADMITTED_BOTH_WORKERS_ATTACHED',can_qualify_workers:false};
  if(url.includes('/workers/state'))return {enabled:true,can_attach_workers:false,required_workers:['dsh','a0'],can_qualify_workers:false};
  throw Error('unexpected request '+url);
 },authedFetch:()=>{throw Error('unexpected download');}},__HERMES_PLUGINS__:{register:(name,component)=>{Component=component;}}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context,{timeout:1000});
const render=()=>{cursor=0;tree=Component();const pending=effects;effects=[];pending.forEach(f=>f());};
const text=n=>typeof n==='string'?n:n&&n.children?n.children.map(text).join(''):'';
const find=(n,p)=>{if(!n||typeof n!=='object')return null;if(p(n))return n;for(const c of n.children||[]){const v=find(c,p);if(v)return v;}return null;};
const button=label=>find(tree,n=>n.tag==='button'&&text(n)===label);
const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const click=async label=>{render();const b=button(label);assert(b,'missing '+label);assert(!b.props.disabled,'disabled '+label);await b.props.onClick();await tick();render();};
(async()=>{render();await tick();render();render();await click('onboarding');await click('Load current native state');
 await click('Manage workers for admitted profile');assert(button('Activate complete profile').props.disabled);
 assert(button('Attach both workers to this profile').props.disabled);
 const select=find(tree,n=>n.tag==='select'&&n.children.some(c=>c&&c.props&&c.props.value==='friday-local'));
 assert(select);select.props.onChange({target:{value:'friday-local'}});render();await click('Attach both workers to this profile');
 const prepared=requests.find(r=>r.url.includes('/workers/prepare'));assert(prepared);
 assert.deepEqual(JSON.parse(prepared.body),{platform:'telegram',transport_profile:'default',account_id:'bot-A',user_id:'1',
  expected_config_sha256:'a'.repeat(64),generation:3,template:'friday-local'});
 assert(button('Activate complete profile').props.disabled);
 if(uncertain){assert(button('Attach both workers to this profile').props.disabled);await click('Inspect worker setup');}
 else {await click('Prepare and check required workers');assert(button('Prepare and check required workers').props.disabled);await click('Inspect worker setup');}
 process.stdout.write(JSON.stringify({requests,browser_live:'NOT_RUN',mode:uncertain?'UNCERTAINTY_NO_REPLAY':'EXPLICIT_SAME_USER_BOTH_ATTACH'}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
