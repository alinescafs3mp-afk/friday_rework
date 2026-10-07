// Pure parser controls: no provider, sockets, worker or credentials.
import assert from 'node:assert/strict';
import {sources} from '../plugins/friday_rework/adapters/dsh_keyless_web.mjs';
const config={maxResults:1,maxOutputChars:2000};
const block=(title='Docs',text='Useful evidence')=>`Title: ${title}\nURL: https://docs.python.org/3/\nHighlights:\n${text}`;
assert.equal(sources(block(),config).truncated,false);
const count=sources(block()+'\n---\n'+block('More'),config);
assert.equal(count.sources.length,1);assert.equal(count.truncated,true);
const title=sources(block('x'.repeat(257)),config);
assert.equal(title.sources[0].title.length,256);assert.equal(title.truncated,true);
const snippet=sources(block('Docs','x'.repeat(200)),{...config,maxOutputChars:100});
assert.equal(snippet.truncated,true);
assert(snippet.sources[0].url.length+snippet.sources[0].title.length+snippet.sources[0].snippet.length<=100);
const noSpace=sources(block(),{...config,maxOutputChars:10});
assert.deepEqual(noSpace,{sources:[],truncated:true});
console.log(JSON.stringify({controls:5,status:'PASS',externalEffects:0}));
