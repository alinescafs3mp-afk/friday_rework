import io,zipfile
def docx():
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Own uploaded report</w:t></w:r></w:p><w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>')
 return b.getvalue()

def pdf():
 stream=b'BT /F1 12 Tf 72 720 Td (Own uploaded PDF report) Tj ET'
 objs=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
 out=b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n';offsets=[]
 for i,obj in enumerate(objs,1):offsets.append(len(out));out+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
 xref=len(out);out+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets)+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n';return out


def scanned_pdf():
 import zlib
 content=b'q 612 0 0 792 0 0 cm /Im0 Do Q'
 image=zlib.compress(bytes(range(256))*256)
 objs=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>',b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',b'<< /Type /XObject /Subtype /Image /Width 256 /Height 256 /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length '+str(len(image)).encode()+b' >>\nstream\n'+image+b'\nendstream']
 out=b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n';offsets=[]
 for i,obj in enumerate(objs,1):offsets.append(len(out));out+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
 xref=len(out);out+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets)+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n';return out
