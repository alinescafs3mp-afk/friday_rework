"""Explicit native SearXNG composition; source data never grants a live route."""
import copy
import ipaddress
import re


class WebConfigError(ValueError):
    pass


def checked_web(value):
    if (not isinstance(value,dict) or set(value) != {'profile','timeout_seconds','dns','version','source_pins','image'}
            or not isinstance(value['image'],str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',value['image'])
            or value['profile'] != 'searxng-google' or type(value['timeout_seconds']) is not int
            or not 1 <= value['timeout_seconds'] <= 30 or not isinstance(value['dns'],list)
            or not 1 <= len(value['dns']) <= 2 or len(set(value['dns'])) != len(value['dns'])
            or not isinstance(value['version'],str) or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,96}',value['version'])
            or not isinstance(value['source_pins'],dict)
            or set(value['source_pins']) != {'/exe/run_searxng.sh','/usr/local/searxng/searxng-src/searx/webapp.py',
                                            '/usr/local/searxng/searxng-src/searx/settings_loader.py','/a0/helpers/searxng.py','/a0/tools/search_engine.py'}
            or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in value['source_pins'].values())):
        raise WebConfigError('a0_explicit_web_service_required')
    expected = {'/a0/helpers/searxng.py':'4020eca255497dbf95076166ebefaff14a095abafaff69cb6176a8ae31c2fcc2',
                '/a0/tools/search_engine.py':'c13c14560d0ac1947b63ed1ad795bd2fad5e026673d2cc615f34ef6da57a9efb'}
    if any(value['source_pins'].get(k)!=v for k,v in expected.items()):
        raise WebConfigError('a0_native_web_overlay_not_pinned')
    for text in value['dns']:
        try:
            ip=ipaddress.ip_address(text)
            if not ip.is_global or ip.version != 4 or str(ip) != text: raise ValueError()
        except ValueError:
            raise WebConfigError('a0_web_dns_not_public') from None
    return copy.deepcopy(value)


def route_web(value):
    v=checked_web(value)
    return {'profile':v['profile'],'dns':v['dns'],'public_https':True}


def service_files(value):
    v=checked_web(value); timeout=v['timeout_seconds']
    # Native launcher and native supervisor, dedicated to these two services.
    # UI preserves the existing accepted run_ui path; no self-update or tunnel.
    supervisor = '''[supervisord]
nodaemon=true
user=root
logfile=/dev/null
pidfile=/var/run/friday-supervisord.pid
[unix_http_server]
file=/var/run/friday-supervisor.sock
chmod=0600
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix:///var/run/friday-supervisor.sock
[program:run_searxng]
command=/exe/run_searxng.sh
user=root
directory=/usr/local/searxng/searxng-src
environment=SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml
startretries=0
autorestart=false
stopwaitsecs=1
stopasgroup=true
killasgroup=true
stdout_logfile=/dev/null
stderr_logfile=/dev/null
[program:run_ui]
command=/opt/venv-a0/bin/python /a0/run_ui.py --dockerized=true --host=127.0.0.1 --port=5000
user=root
directory=/a0
startretries=0
autorestart=false
stopwaitsecs=1
stopasgroup=true
killasgroup=true
stdout_logfile=/dev/null
stderr_logfile=/dev/null
'''
    return {
        'web/settings.yml':{'use_default_settings':{'engines':{'keep_only':['google']}},
            'search':{'formats':['json']},'server':{'bind_address':'127.0.0.1','port':55510,'limiter':False,'image_proxy':False},
            'outgoing':{'request_timeout':timeout,'max_request_timeout':timeout},
            'engines':[{'name':'google','engine':'google','shortcut':'g','disabled':False}]},
        'plugins/_document_query/config.json':{'fetch_timeout':timeout,'fetch_retries':1,'fetch_retry_backoff':0,
                                               'max_remote_bytes':1000000,'gather_timeout':timeout+1},
        'web/supervisord.conf':supervisor,
    }


START_SCRIPT = ('umask 077; . /ins/setup_venv.sh; . /ins/copy_A0.sh; '
                'mkdir -p /a0/usr/uploads; cd /a0; '
                'set -a; . /a0/usr/web/secret.env; set +a; '
                'exec /usr/bin/supervisord -c /a0/usr/web/supervisord.conf')


def service_probe(value):
    """Inside exact owned container: actual native settings and supervisor state.

    Does not search or call models. No value/hash of the secret leaves it.
    Native settings version/source pins must be observed in the built image.
    """
    v=checked_web(value)
    return '''import os,json,hashlib,pathlib,xmlrpc.client
os.environ['SEARXNG_SETTINGS_PATH']='/etc/searxng/settings.yml'
secret=pathlib.Path('/a0/usr/web/secret.env').read_text().strip().split('=',1)[1]
os.environ['SEARXNG_SECRET']=secret
assert len(secret)>=32 and secret not in ('ultrasecretkey','changeme','CHANGE_ME')
expected='''+repr(v)+'''
for name,digest in expected['source_pins'].items():
 p=pathlib.Path(name);assert p.resolve()==p and hashlib.sha256(p.read_bytes()).hexdigest()==digest
import searx, searx.settings_loader
searx.init_settings()
settings=searx.settings
assert settings['server']['secret_key']==secret
assert settings['server']['bind_address']=='127.0.0.1' and settings['server']['port']==55510
assert [x['name'] for x in settings['engines'] if not x.get('disabled',False)]==['google']
assert settings['outgoing']['request_timeout']==expected['timeout_seconds']
assert settings['outgoing']['max_request_timeout']==expected['timeout_seconds']
import supervisor.xmlrpc
server=xmlrpc.client.ServerProxy('http://127.0.0.1',transport=supervisor.xmlrpc.SupervisorTransport(None,None,'unix:///var/run/friday-supervisor.sock'))
rows=server.supervisor.getAllProcessInfo()
assert len(rows)==2 and {r['name'] for r in rows}=={'run_ui','run_searxng'}
assert all(r['statename']=='RUNNING' and type(r['pid']) is int and r['pid']>0 for r in rows)
for r in rows:
 env=pathlib.Path('/proc',str(r['pid']),'environ').read_bytes().split(b'\\0')
 assert env.count(b'SEARXNG_SECRET='+secret.encode())==1
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:55510/config',timeout=2) as response:
 assert response.status==200
 raw=response.read(65537);assert len(raw)<=65536
 config=json.loads(raw);assert config['version']==expected['version']
 assert [x['name'] for x in config['engines'] if x.get('enabled',True)]==['google']
print(json.dumps({'status':'CURRENT_NATIVE_WEB_SERVICE_CHECKED','version':expected['version'],
                 'processes':[{k:r[k] for k in ('name','pid','start','statename')} for r in rows]}))
'''
