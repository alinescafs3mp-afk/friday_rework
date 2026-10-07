/** Friday glue into intact Harness ctx.web. No discovery, remote instructions,
 * dynamic tools, SDK SSE reconnection, paid key, model or alternate route. */
export const name = 'friday-web-keyless';
export const inject = ['web'];
export const ENDPOINT = 'https://mcp.exa.ai/mcp?tools=web_search_exa';
const fail = code => { throw Error(code); };
const integer = (v, max) => Number.isInteger(v) && v > 0 && v <= max;
export function checked(config) {
  if (!config || Object.keys(config).sort().join() !== 'endpoint,maxOutputChars,maxResponseBytes,maxResults,timeoutMs'
      || config.endpoint !== ENDPOINT || !integer(config.maxResults,20)
      || !integer(config.timeoutMs,30000) || !integer(config.maxResponseBytes,1000000)
      || !integer(config.maxOutputChars,15000)) fail('KEYLESS_CONFIG_REFUSED');
  return Object.freeze({...config});
}
function envelope(body) {
  // Exactly one matching RPC response. SSE events are data only, never retried.
  const texts=body.trim().startsWith('{') ? [body] : body.split(/\r\n|\r|\n/).filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trim());
  if (texts.length !== 1) fail('KEYLESS_ENVELOPE_REFUSED');
  let v; try {v=JSON.parse(texts[0]);} catch {fail('KEYLESS_MALFORMED');}
  if (v.jsonrpc !== '2.0' || v.id !== 1 || v.error || Object.keys(v).some(k=>!['jsonrpc','id','result'].includes(k))) fail('KEYLESS_RPC_REFUSED');
  const r=v.result;
  if (!r || r.isError || Object.keys(r).some(k=>!['content','isError'].includes(k))
      || !Array.isArray(r.content) || r.content.length !== 1 || r.content[0].type !== 'text'
      || typeof r.content[0].text !== 'string'
      || Object.keys(r.content[0]).some(k=>!['type','text','_meta'].includes(k))) fail('KEYLESS_TOOL_RESULT_REFUSED');
  return r.content[0].text;
}
export function sources(text,config) {
  // Reuse Hermes native Exa formatted-text mapping. No instruction/system
  // fields are projected. URL is attribution; native fetch validates DNS/SSRF.
  const out=[];let left=config.maxOutputChars,truncated=text.length>config.maxOutputChars;
  for (const block of text.split('\n---\n')) {
    let title='',url='',lines=[],highlight=false;
    for (const raw of block.split(/\r?\n/)) {
      const line=raw.trim();
      if (line.startsWith('Title:')) title=line.slice(6).trim();
      if (line.startsWith('URL:')) url=line.slice(4).trim();
      if (/^(Title|URL|Highlights|Published|Author):/.test(line)) highlight=line.startsWith('Highlights:');
      else if (highlight && line) lines.push(line);
    }
    let u;try {u=new URL(url);}catch {continue;}
    if (u.protocol !== 'https:' || u.username || u.password || u.port || url.length>1024) continue;
    if (out.length>=config.maxResults || left<url.length) {truncated=true;break;}
    left-=url.length;
    if(title.length>Math.min(256,left)) truncated=true;
    title=title.slice(0,Math.min(256,left));left-=title.length;
    const prefix='Untrusted web search evidence: ';
    if((prefix+lines.join(' ')).length>left) truncated=true;
    const snippet=(prefix+lines.join(' ')).slice(0,Math.max(0,left));left-=snippet.length;
    out.push({url,title,snippet});
  }
  return {sources:out,truncated};
}
export class KeylessSearchProvider {
  id='exa';
  constructor(config) {this.config=checked(config);}
  available() {return true;}
  async search(request, signal) {
    const c=this.config;
    if (typeof request.query !== 'string' || !request.query.trim() || request.query.length>4096
        || (request.maxResults !== undefined && !integer(request.maxResults,20))) fail('KEYLESS_QUERY_REFUSED');
    const limit=Math.min(request.maxResults ?? c.maxResults,c.maxResults);
    const controller=new AbortController();
    const abort=()=>controller.abort();
    if (signal?.aborted) fail('KEYLESS_ABORTED');
    signal?.addEventListener('abort',abort,{once:true});
    const timer=setTimeout(abort,c.timeoutMs);let reader;
    try {
      const response=await fetch(c.endpoint,{method:'POST',redirect:'error',signal:controller.signal,
        headers:{'content-type':'application/json','accept':'application/json, text/event-stream'},
        body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'web_search_exa',arguments:{query:request.query,objective:request.query,numResults:limit}}})});
      if (!response.ok) fail(response.status===429?'KEYLESS_RATE_LIMITED':'KEYLESS_UNAVAILABLE');
      if (!/^application\/json|^text\/event-stream/.test(response.headers.get('content-type')||'')) fail('KEYLESS_CONTENT_TYPE');
      if (Number(response.headers.get('content-length')||0)>c.maxResponseBytes) fail('KEYLESS_BODY_BOUND');
      if (!response.body) fail('KEYLESS_BODY_MISSING');
      reader=response.body.getReader();let length=0;const chunks=[];
      while (true) {
        const {done,value}=await reader.read();if(done)break;
        length+=value.byteLength;if(length>c.maxResponseBytes)fail('KEYLESS_BODY_BOUND');chunks.push(value);
      }
      if(controller.signal.aborted)fail('KEYLESS_ABORTED');
      const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
      const text=envelope(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      return sources(text,{...c,maxResults:limit});
    } catch {fail(controller.signal.aborted?'KEYLESS_ABORTED':'KEYLESS_REQUEST_REFUSED');}
    finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);controller.abort();if(reader)await reader.cancel().catch(()=>{});}
  }
}
export function apply(ctx,config) {ctx.web.registerSearchProvider(new KeylessSearchProvider(config));}

/** Exact ordinary renderer composition at the existing native probe. */
export function validateWebOverlay(overlay) {
  const ids=new Set(['web','web-search-exa','web-search-exa-keyless','mcp-exa','web-fetch-http','tool-web']);
  const selected=overlay.filter(r=>r && (ids.has(r.id) && !(r.id==='tool-web'&&r.disabled===true) || 'insert' in r));
  if(!selected.length)return false;
  const tool=selected.find(r=>r.id==='tool-web')?.config;
  const http=selected.find(r=>r.id==='web-fetch-http')?.config;
  const provider=selected.find(r=>'insert' in r)?.insert?.[0];
  if(!tool||!http||!provider||!integer(tool.searchMaxResults,20)||!integer(tool.searchMaxQueries,4)
      || !integer(tool.searchTimeoutMs,120000)||!integer(tool.fetchMaxOutputChars,200000)
      || tool.fetchMaxOutputChars<2000||!integer(http.maxResponseBytes,5000000))fail('WEB_PATCH_REFUSED');
  const r=tool.searchMaxResults,t=tool.searchTimeoutMs,c=tool.fetchMaxOutputChars,b=http.maxResponseBytes;
  const p=provider.id==='web-search-exa-keyless' ? {id:'web-search-exa-keyless',name:'/payload/friday-web-keyless.mjs',config:{endpoint:ENDPOINT,maxResults:r,timeoutMs:Math.min(t,30000),maxResponseBytes:Math.min(b,1000000),maxOutputChars:Math.min(c,15000)}} : {id:'web-search-exa',name:'@deepseek-ai/dsh-web-search-exa',config:{baseURL:'https://api.exa.ai',searchType:'auto',numResults:r,highlightsPerResult:1}};
  const expected=[{id:'web',config:{searchProvider:'exa',fetchProvider:'http'}},{insert:[p]},
    {id:'web-fetch-http',disabled:false,config:{maxResponseBytes:b,maxBodyChars:c,timeoutMs:t,maxRedirects:3}},
    {id:'tool-web',disabled:false,config:{search:true,fetch:true,searchMaxResults:r,searchMaxQueries:tool.searchMaxQueries,searchTimeoutMs:t,fetchTimeoutMs:t,fetchMaxOutputChars:c}}];
  if(JSON.stringify(selected)!==JSON.stringify(expected))fail('WEB_PATCH_REFUSED');return true;
}
