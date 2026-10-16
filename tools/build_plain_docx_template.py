"""Build-only python-docx 1.2.0 plain template, following native MIT docx skill.
Runtime has no third party document dependency. ZIP timestamps and product
metadata are fixed; all relationships are inspected to reject external targets.
"""
from docx import Document
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
import hashlib,base64,argparse
parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args();out=BytesIO()
doc=Document()
p=doc.core_properties
p.author='Friday'; p.last_modified_by='Friday'; p.title=''; p.subject='';p.keywords='';p.comments='';p.category='';p.identifier='';p.language=''
p.created=p.modified=datetime(2000,1,1,tzinfo=timezone.utc)
b=BytesIO();doc.save(b)
with ZipFile(b) as source, ZipFile(out,'w',compression=ZIP_DEFLATED) as dest:
    for name in sorted(source.namelist()):
        data=source.read(name)
        if name.endswith('.rels'):
            root=ET.fromstring(data)
            assert not any(e.get('TargetMode')=='External' for e in root)
        if name=='docProps/app.xml':
            root=ET.fromstring(data)
            for item in root:
                if item.tag.endswith('Application'): item.text='Friday'
                if item.tag.endswith('AppVersion'): item.text='1.0'
            data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        info=ZipInfo(name,(2000,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o600<<16
        dest.writestr(info,data)
data=out.getvalue();args.output.write_bytes(base64.b64encode(data)+b'\n');print(hashlib.sha256(data).hexdigest())
