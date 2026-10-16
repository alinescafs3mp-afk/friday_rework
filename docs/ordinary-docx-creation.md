Plain DOCX source support

The existing admitted write_file tool accepts explicit format="docx" and creates an absent .docx name in the caller workspace. A revision creates another name from extracted text; rich formatting is not retained. Runtime uses only Python standard-library XML, ZIP and strict bounded base64; python-docx and lxml are not runtime dependencies.

The static OPC template was built with python-docx 1.2.0 using tools/build_plain_docx_template.py. Run that build-only tool with the output path friday_plain_docx_template.b64. Decoded SHA256 must be 884478f7f60cfe75d88872eda9c7001084423f92f7c448bfe5446403da198ef4. Fixed ZIP/core properties preserve reproducibility. The actual Steve Canny 2013 MIT notice ships as hermes_cli/friday_plain_docx_template.LICENSE in the native patch; no substitute license is used.

Native tests run with fully composed native sources on PYTHONPATH and existing project test fixtures. Source tests do not prove installed CLI bootstrap, authenticated Telegram execution, runtime or release acceptance. Independent source review is separate from Root integration and runtime qualification.
