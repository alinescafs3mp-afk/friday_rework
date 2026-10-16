import io,zipfile,json
from file_native_fixture import env,entered,home
from tools import file_tools

def test_invalid_xml_encoding_is_typed_malformed(env):
    xml=b'<?xml version="1.0" encoding="not-a-real-encoding"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>test</w:t></w:r></w:p></w:body></w:document>'
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('word/document.xml',xml)
    data=output.getvalue()
    with entered(env):
        path=home(env)/'workspace/invalid.docx';path.write_bytes(data);path.chmod(0o600)
        result=json.loads(file_tools.read_file_tool('invalid.docx'))
        assert result=={'success':False,'error':'document_extraction_failed','format':'docx','reason':'malformed_or_required_part_limit'}
        assert path.read_bytes()==data
