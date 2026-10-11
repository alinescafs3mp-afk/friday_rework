"""Exact selected NativeControl.call AST only; inert fixture data, no runtime loader."""
class NativeControl:
    async def call(self, method, params):
        if method != 'initialize' and params.get('threadId') != self.thread:
            raise ValueError('Exact designated thread required')
        self.sequence += 1
        request_id = self.sequence
        await self.ws.send(json.dumps({'id': request_id, 'method': method, 'params': params}))
        async with asyncio.timeout(10):
            while True:
                response = json.loads(await self.ws.recv())
                if response.get('id') != request_id:
                    continue
                if 'error' in response:
                    raise RuntimeError(json.dumps(response['error']))
                return response['result']
