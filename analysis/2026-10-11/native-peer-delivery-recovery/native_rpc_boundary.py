"""Analysis-only native RPC boundary excerpt; no routing, grant or entry point."""
import asyncio
import json
import time
import uuid

def exact_confirmation(value,event,notice):
    q=value.get('queuedSubmission',{})
    if not isinstance(q.get('id'),str):raise ValueError('missing queue id')
    uuid.UUID(q['id'])
    if q.get('clientUserMessageId')!=event:raise ValueError('foreign client id')
    rows=q.get('input')
    if not isinstance(rows,list) or len(rows)!=1:raise ValueError('different input count')
    item=rows[0]
    if not isinstance(item,dict) or set(item)-{'type','text','text_elements'}:raise ValueError('unknown input fields')
    if item.get('type')!='text' or item.get('text')!=notice:raise ValueError('different notice')
    if 'text_elements' in item and item['text_elements']!=[]:raise ValueError('different text elements')
    return q

def deadline_control(base, unix_connect):
    class Control(base):
        async def __aenter__(self):
            self.connection=unix_connect(str(self.endpoint),uri='ws://localhost/',
                compression=None,open_timeout=5,close_timeout=2,max_size=8_000_000)
            self.ws=await self.connection.__aenter__()
            try:
                result=await self.call('initialize',{'clientInfo':{'name':'friday_peer_control','version':'1'},'capabilities':{'experimentalApi':True}})
                if result.get('codexHome')!=self.home:raise RuntimeError('Backend account home mismatch')
                await self.ws.send(json.dumps({'method':'initialized'}))
                return self
            except BaseException:
                await self.__aexit__(None,None,None)
                raise
        async def __aexit__(self,*args):
            try:
                async with asyncio.timeout_at(self.deadline):
                    await self.connection.__aexit__(*args)
            except BaseException:
                # Abort only this owned client transport, never a TUI/turn/socket path.
                transport=getattr(getattr(self,'ws',None),'transport',None)
                if transport is not None:transport.abort()
                raise
    return Control

async def add_once(control,event,notice,deadline,reserve_request,confirm):
    control.deadline=deadline
    async with asyncio.timeout_at(deadline):
        async with control:
            before=await control.inspect()
            if before['status'].get('type')!='idle' or before['queued_ids'] or before['queue_has_more'] or before['goal_status'] is not None:raise RuntimeError('not idle empty goal-free')
            if time.monotonic()>=deadline-3:raise RuntimeError('no mutation after useful transport clock')
            params={'threadId':control.thread,'clientUserMessageId':event,'input':[{'type':'text','text':notice}]}
            reserve_request({'id':control.sequence+1,'method':'thread/queue/add','params':params,'deadline_monotonic':deadline,'before':before})
            # No retry and no queue/start. Existing visible TUI performs normal idle admission.
            response=await control.call('thread/queue/add',params)
            queued=exact_confirmation(response,event,notice)
            confirm(response,queued)  # durable confirmation before connection-close ambiguity
            return queued
