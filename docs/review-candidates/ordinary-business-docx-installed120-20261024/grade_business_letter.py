"""Read-only bounded S223 ordinary business-letter semantic retarget of R136.

CLI requires Root-bound references. Importing this module has no effects.
No network, runtime, database, credential, extraction or product writes.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import signal
import stat
import struct
import time
import unicodedata
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile
import zlib

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
OFFICE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'
LIMITS = dict(archive_bytes_max=1048576, members_max=128,
              total_uncompressed_bytes_max=8388608,
              member_uncompressed_bytes_max=2097152, style_basedOn_max_depth=20)
IDS = ['source_regular_file', 'compressed_archive_size_limit', 'source_unchanged_during_read', 'received_sha256_matches', 'received_bytes_match', 'zip_member_count_limit', 'zip_member_names_unique', 'zip_member_paths_safe', 'zip_members_not_encrypted', 'zip_member_uncompressed_size_limit', 'zip_total_uncompressed_size_limit', 'zip_regular_members', 'zip_size_preflight_before_decompression', 'zip_all_members_valid_crc_and_sizes', 'ooxml_required_parts_present', 'required_xml_no_dtd_or_entities', 'required_xml_well_formed', 'word_main_content_type', 'root_office_document_relationship_internal_target', 'word_document_root', 'word_styles_root', 'word_document_body_present', 'style_ids_unique', 'outline_style_resolution_valid_bounded_acyclic', 'letter_text_supported_visible', 'letter_direct_paragraph_structure', 'letter_no_template_table_markdown', 'letter_header_date', 'letter_sender_company', 'letter_recipient_company', 'letter_recipient_full_name', 'letter_subject', 'letter_greeting', 'letter_purpose_order', 'letter_quantity_item', 'letter_total_including_vat', 'letter_vat_rate', 'letter_included_vat_amount', 'letter_delivery_date_address', 'letter_confirmation_deadline_email', 'letter_sender_role_full_name', 'letter_sections_order', 'letter_all_dates_exact', 'letter_all_order_model_values_exact', 'letter_all_quantity_values_exact', 'letter_all_money_roles_values_exact', 'letter_all_vat_rates_exact', 'letter_all_emails_exact', 'letter_all_companies_exact', 'letter_all_person_names_exact', 'letter_numeric_inventory_exact', 'letter_no_negation_contradiction', 'letter_all_date_roles_exact', 'letter_all_address_tokens_exact', 'letter_all_job_roles_exact', 'grading_completed_without_exception']
REQUIRED = ['[Content_Types].xml', '_rels/.rels', 'word/document.xml', 'word/styles.xml']
FACTS = {'document_date': '26.10.2026', 'sender_company': 'ООО «Северный Контур»', 'recipient_company': 'АО «Вектор-Сервис»', 'recipient_person': 'Марина Сергеевна Орлова', 'sender_person': 'Алексей Ильич Лебедев', 'sender_role': 'руководитель проектов', 'subject': 'Согласование поставки датчиков ДТ-48', 'order_number': 'СК-2847/26', 'quantity': 24, 'item': 'комплекта датчиков ДТ-48', 'total_rub': '186720', 'vat_percent': 20, 'vat_included_rub': '31120', 'delivery_date': '06.11.2026', 'delivery_address': 'г. Казань, ул. Аделя Кутуя, д. 86', 'confirmation_deadline': '30.10.2026', 'contact_email': 'office@sever-kontur.example'}
SPEC_SHA256 = 'a9baee5c3c250f0772e51a44e331def7054b7e921d5c720d344f54ecdab945a3'
SPEC_BYTES = 2853
CREATE_QUESTION = 'Подготовь деловое письмо на русском языке от ООО «Северный Контур» в АО «Вектор-Сервис». Дата письма 26.10.2026. Адресат: Марина Сергеевна Орлова. Тема: «Согласование поставки датчиков ДТ-48». Просим согласовать поставку по заказу СК-2847/26: 24 комплекта датчиков ДТ-48, общая стоимость с НДС 186 720 руб., НДС 20%, включённая сумма НДС 31 120 руб. Дата поставки 06.11.2026; адрес: г. Казань, ул. Аделя Кутуя, д. 86. Попроси подтвердить согласование до 30.10.2026; контактный адрес office@sever-kontur.example. Подписант: Алексей Ильич Лебедев, руководитель проектов. ФИО адресата в шапке и подписанта в подписи напечатай полностью в именительном падеже. Сделай настоящее письмо Word: отдельные абзацы для шапки/даты/адресата, обращения, цели и заказа, количества/стоимости/НДС, поставки и адреса, просьбы о подтверждении со сроком и email, заключения и подписи; не менее шести непустых абзацев Word. Формулировки свободные; суммы, даты и реквизиты должны иметь однозначные подписи. Даты пиши ДД.ММ.ГГГГ. Таблицы, Markdown и посторонний шаблонный заголовок не добавляй.'
FOLLOWUP_QUESTION = 'По только что подготовленному письму назови номер заказа, количество комплектов, общую стоимость с НДС, ставку и включённую сумму НДС, дату и адрес поставки, а также срок подтверждения и контактный адрес. Не создавай и не отправляй файл: ответь текстом.'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
CURRENT_TUPLE = {'source': 120, 'installed': 120, 'layers': 120, 'project': 316, 'native': 0, 'service_owner': 'Root'}
CUSTODY_IDS = {'one_document_one_send_full_window', 'received_regular_complete_exact_bytes_sha',
               'receipt_exact_capture_observation', 'genuine_docx_name_mime',
               'advertised_getfile_same_file_identity_size', 'exact_nonce_request_run_binding',
               'unchanged_unit', 'unchanged_dashboard_owner', 'unchanged_dashboard_lock_sha256',
               'unchanged_install_marker_sha256', 'unchanged_source_sha256', 'unchanged_all_session_ids',
               'stable_routing_authority', 'stable_session_identity', 'no_remaining_native_turn_leases',
               'one_native_user_exact_request', 'native_create_only_verified_docx_write',
               'native_workspace_received_identical', 'native_delivered_exact_document_receipt',
               'native_receipt_same_user_origin', 'immutable_exact_native_candidate_journal',
               'persisted_hidden_terminal_delivered_anchor', 'old_private_memory_fact_not_emitted'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Rejected(Exception):
    pass


def read_regular(path, maximum):
    """No FIFO/symlink following; exact bounded snapshot including path identity."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise Rejected('source_not_regular')
        if before.st_size > maximum:
            raise Rejected('source_size_limit')
        raw = b''
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(fd)
        current = os.lstat(path)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        unchanged = all(getattr(before, k) == getattr(after, k) == getattr(current, k) for k in fields)
        return raw, unchanged
    finally:
        os.close(fd)


def pinned(ref, maximum=16777216):
    if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
        raise Rejected('reference_missing')
    raw, unchanged = read_regular(ref['path'], maximum)
    if not unchanged or sha(raw) != ref.get('sha256') or len(raw) != ref.get('bytes'):
        raise Rejected('reference_identity_mismatch')
    return raw


def text(element):
    return ''.join(e.text or '' for e in element.iter('{' + W + '}t')).strip()


def grade(path, expected_sha256, expected_bytes):
    start = time.monotonic()
    checks = {k: {'id': k, 'passed': None, 'status': 'NOT_EVALUATED',
                  'reason': 'prerequisite_unavailable'} for k in IDS}
    observations = {'raw_document_text_logged': False}
    source = {'expected_sha256': expected_sha256, 'expected_bytes': expected_bytes}

    def check(k, value, **details):
        checks[k] = dict(id=k, passed=bool(value), **details)
        return bool(value)

    def require(k, value, **details):
        if not check(k, value, **details):
            raise Rejected(k)

    try:
        try:
            raw, unchanged = read_regular(path, LIMITS['archive_bytes_max'])
        except Rejected as exc:
            if str(exc) == 'source_size_limit':
                check('source_regular_file', True)
                check('compressed_archive_size_limit', False)
            else:
                check('source_regular_file', False)
            raise
        except OSError:
            check('source_regular_file', False)
            raise Rejected('source_open_failed')
        check('source_regular_file', True)
        require('compressed_archive_size_limit', len(raw) <= LIMITS['archive_bytes_max'], actual_bytes=len(raw))
        require('source_unchanged_during_read', unchanged)
        source.update(sha256=sha(raw), bytes=len(raw))
        require('received_sha256_matches', sha(raw) == expected_sha256)
        require('received_bytes_match', len(raw) == expected_bytes)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = z.infolist()
            observations['zip_member_count'] = len(members)
            require('zip_member_count_limit', len(members) <= LIMITS['members_max'], actual=len(members))
            require('zip_member_names_unique', len({i.orig_filename for i in members}) == len(members))
            def safe(i):
                n = i.orig_filename
                return (n == i.filename and n and '\x00' not in n and '\\' not in n
                        and not n.startswith('/') and not re.match(r'^[A-Za-z]:', n)
                        and '..' not in n.split('/'))
            require('zip_member_paths_safe', all(safe(i) for i in members))
            require('zip_members_not_encrypted', all(not i.flag_bits & 1 for i in members))
            require('zip_member_uncompressed_size_limit', all(0 <= i.file_size <= LIMITS['member_uncompressed_bytes_max'] for i in members))
            require('zip_total_uncompressed_size_limit', sum(i.file_size for i in members) <= LIMITS['total_uncompressed_bytes_max'])
            require('zip_regular_members', all(not i.is_dir() and stat.S_IFMT(i.external_attr >> 16) in (0, stat.S_IFREG) for i in members))
            check('zip_size_preflight_before_decompression', True)
            parts = {}
            try:
                for i in members:
                    # ZipExtFile truncates output to declared file_size. Verify the
                    # actual stream too, bounded at declared+1, to catch forged sizes.
                    offset = i.header_offset
                    if raw[offset:offset+4] != b'PK\x03\x04':
                        raise Rejected('local_header_invalid')
                    name_size, extra_size = struct.unpack_from('<HH', raw, offset+26)
                    begin = offset + 30 + name_size + extra_size
                    compressed = raw[begin:begin+i.compress_size]
                    if len(compressed) != i.compress_size:
                        raise Rejected('compressed_member_truncated')
                    if i.compress_type == zipfile.ZIP_STORED:
                        actual = compressed
                    elif i.compress_type == zipfile.ZIP_DEFLATED:
                        decoder = zlib.decompressobj(-15)
                        actual = decoder.decompress(compressed, i.file_size+1)
                        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                            raise Rejected('deflate_stream_not_exact')
                    else:
                        raise Rejected('unsupported_ooxml_compression')
                    if len(actual) != i.file_size or zlib.crc32(actual) != i.CRC:
                        raise Rejected('actual_crc_or_size_mismatch')
                    with z.open(i) as member:
                        data = member.read(LIMITS['member_uncompressed_bytes_max'] + 1)
                        if len(data) != i.file_size or member.read(1):
                            raise Rejected('member_size_mismatch')
                    if i.filename in REQUIRED:
                        parts[i.filename] = data
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, Rejected, zlib.error, struct.error):
                check('zip_all_members_valid_crc_and_sizes', False)
                raise Rejected('crc_or_size_failure')
            check('zip_all_members_valid_crc_and_sizes', True, checked_members=len(members))
        require('ooxml_required_parts_present', all(k in parts for k in REQUIRED))
        require('required_xml_no_dtd_or_entities', all(not re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', v.replace(b'\x00', b''), re.I) for v in parts.values()))
        try:
            xml = {k: ET.fromstring(v) for k, v in parts.items()}
        except ET.ParseError:
            check('required_xml_well_formed', False)
            raise Rejected('malformed_xml')
        check('required_xml_well_formed', True, parsed_parts=len(xml))
        ct = xml[REQUIRED[0]]
        matches = [e for e in ct.findall('{' + CT + '}Override') if e.get('PartName') == '/word/document.xml']
        check('word_main_content_type', ct.tag == '{' + CT + '}Types' and len(matches) == 1 and matches[0].get('ContentType') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml')
        root_rels = xml[REQUIRED[1]]
        rels = [e for e in root_rels.findall('{' + REL + '}Relationship') if e.get('Type') == OFFICE]
        valid_rel = False
        if len(rels) == 1:
            r = rels[0]
            t = r.get('Target', '')
            u = urlsplit(t)
            valid_rel = (r.get('TargetMode', 'Internal') == 'Internal' and not (u.scheme or u.netloc or u.query or u.fragment)
                         and '\\' not in t and '%' not in t and posixpath.normpath(t.lstrip('/')) == 'word/document.xml')
        check('root_office_document_relationship_internal_target', root_rels.tag == '{' + REL + '}Relationships' and valid_rel)
        doc, styles_xml = xml[REQUIRED[2]], xml[REQUIRED[3]]
        require('word_document_root', doc.tag == '{' + W + '}document')
        require('word_styles_root', styles_xml.tag == '{' + W + '}styles')
        body = doc.find('{' + W + '}body')
        require('word_document_body_present', body is not None)
        style_elements = styles_xml.findall('{' + W + '}style')
        style_ids = [s.get('{' + W + '}styleId') for s in style_elements]
        require('style_ids_unique', all(style_ids) and len(style_ids) == len(set(style_ids)))
        styles = dict(zip(style_ids, style_elements))
        errors = set()

        def outline(properties):
            e = properties.find('{' + W + '}outlineLvl') if properties is not None else None
            if e is None:
                return None
            try:
                n = int(e.get('{' + W + '}val', ''))
                if n not in range(10):
                    raise ValueError()
                return n
            except ValueError:
                errors.add('invalid_outline_level')
                return None

        def from_style(sid, chain=()):
            if sid in chain:
                errors.add('style_cycle')
                return None
            if len(chain) >= LIMITS['style_basedOn_max_depth']:
                errors.add('style_depth')
                return None
            s = styles.get(sid)
            if s is None:
                errors.add('missing_style')
                return None
            level = outline(s.find('{' + W + '}pPr'))
            based = s.find('{' + W + '}basedOn')
            inherited = from_style(based.get('{' + W + '}val'), chain + (sid,)) if based is not None else None
            return level if level is not None else inherited

        for sid in styles:
            from_style(sid)
        children = list(body)
        paragraphs = []
        for index, p in enumerate(children):
            if p.tag != '{' + W + '}p':
                continue
            props = p.find('{' + W + '}pPr')
            direct = outline(props)
            s = props.find('{' + W + '}pStyle') if props is not None else None
            inherited = from_style(s.get('{' + W + '}val')) if s is not None else None
            level = direct if direct is not None else inherited
            paragraphs.append((index, text(p), level))
        check('outline_style_resolution_valid_bounded_acyclic', not errors, error_count=len(errors), max_depth=20)
        observations.update(body_paragraph_count=len(paragraphs), style_count=len(styles),
                            heading_resolution_method='direct outline, otherwise bounded acyclic pStyle/basedOn; 0..8 qualifies; w:t only')
        semantic = letter_checks(body, paragraphs, styles_xml)
        for key, value in semantic.items():
            check(key, value)
        observations.update(nonempty_direct_body_paragraphs=sum(bool(t) for _, t, _ in paragraphs),
                            semantic_method='NFC text, exact typed facts with local roles; flexible prose; no raw text retained')
        check('grading_completed_without_exception', True)
    except Rejected as exc:
        observations['controlled_rejection'] = str(exc)
        check('grading_completed_without_exception', True)
    except Exception as exc:
        observations['exception_type'] = type(exc).__name__
        check('grading_completed_without_exception', False)
    results = [checks[k] for k in IDS]
    counts = dict(total=len(results), passed=sum(c['passed'] is True for c in results),
                  failed=sum(c['passed'] is False for c in results),
                  not_evaluated=sum(c['passed'] is None for c in results))
    return dict(source=source, limits=LIMITS, checks=results, check_counts=counts,
                observations=observations, verdict='PASS' if counts['passed'] == len(IDS) else 'FAIL',
                elapsed_seconds=round(time.monotonic()-start, 6),
                limitations=['Independent single-artifact semantic grade only; no live effects or release acceptance.',
                             'Native custody authentication is a separately pinned Root result; semantic PASS does not replace it.',
                             'Decoder/security checks reused from pinned R136; ordinary business-letter facts retargeted for S223.'])



def normalized(value):
    """NFC and presentation spacing; never transliterate Latin/Cyrillic lookalikes."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value)).strip().casefold()


def contains(value, wanted):
    return normalized(wanted) in normalized(value)


DATE_RE = re.compile(r'(?<!\d)\d{1,2}[./-]\d{1,2}[./-]\d{4}(?!\d)')
MONEY_RE = re.compile(r'(?<![\d.,])(?P<amount>(?:\d{1,3}(?: \d{3})+|\d+)(?:[,.]\d{2})?)\s*(?:руб(?:лей|ля|ль|\.)?|₽)(?![а-я])', re.I)
QUANTITY_RE = re.compile(r'(?<!\d)(\d+)\s+комплект[а-я]*', re.I)
RATE_RE = re.compile(r'(?<![\d.,])(\d+(?:[,.]\d+)?)\s*%')
EMAIL_RE = re.compile(r'[a-z0-9.!#$&*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+', re.I)
ORDER_RE = re.compile(r'(?<![а-яa-z0-9])[а-яa-z]{1,6}-\d+/\d+(?![а-яa-z0-9])', re.I)
MODEL_RE = re.compile(r'(?<![а-яa-z0-9])[а-яa-z]{1,6}[-‑–]\d+(?![а-яa-z0-9/])', re.I)
COMPANY_RE = re.compile(r'(?<![а-я])(?:ооо|пао|зао|оао|ао)\s*[«"“„][^»"”“]+[»"”“]', re.I)
PERSON_RE = re.compile(r'(?<![А-Яа-яЁё])([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*(?:вич|вна|ична|ич)\s+[А-ЯЁ][а-яё]+)(?![А-Яа-яЁё])')



def company_key(value):
    """Company quote presentation only; exact legal prefix and name survive."""
    match = re.fullmatch(r'(ооо|пао|зао|оао|ао)\s*([«"“„])([^»"”“]+)([»"”“])', normalized(value))
    if match is None or {'«':'»', '"':'"', '“':'”', '„':'“'}.get(match.group(2)) != match.group(4):
        return None
    return match.group(1), normalized(match.group(3))


def company_contains(value, wanted):
    expected = company_key(wanted)
    return expected is not None and any(company_key(token) == expected
                                        for token in COMPANY_RE.findall(normalized(value)))

def amount_integer(token):
    value = token.replace(' ', '').replace(',', '.')
    return value[:-3] if value.endswith('.00') else value


def fact_analysis(paragraphs, followup=False):
    """Deterministic local-role checks, never whole-paragraph prose equality."""
    ps = [normalized(p) for p in paragraphs if normalized(p)]
    joined = ' '.join(ps)
    f = FACTS
    amounts = []
    money_ok = True
    total_seen = vat_seen = False
    for p in ps:
        previous_end = 0
        for m in MONEY_RE.finditer(p):
            value = amount_integer(m.group('amount'))
            prefix = p[previous_end:m.start()]
            # A preceding cost/total label identifies total; remaining money needs
            # an explicit VAT/included label. Each occurrence is checked, so the
            # presence of correct numbers cannot rescue swapped/wrong values.
            if re.search(r'стоимост|общ(?:ая|ую|ей)\s+сумм|сумм[ауы]\s+заказ|итого|итогов', prefix):
                role = 'total'
                valid = value == f['total_rub']
                total_seen |= valid
            elif re.search(r'ндс|в\s+том\s+числе|включ[её]н', prefix):
                role = 'vat'
                valid = value == f['vat_included_rub']
                vat_seen |= valid
            else:
                role, valid = 'unlabeled', False
            amounts.append((value, role))
            money_ok &= valid
            previous_end = m.end()
    quantities = QUANTITY_RE.findall(joined)
    rates = RATE_RE.findall(joined)
    all_dates = DATE_RE.findall(joined)
    allowed_dates = {f['delivery_date'], f['confirmation_deadline']}
    if not followup:
        allowed_dates.add(f['document_date'])
    date_roles_ok = True
    for p in ps:
        previous_end = 0
        for m in DATE_RE.finditer(p):
            prefix = p[previous_end:m.start()]
            roles = []
            for role, pattern in [('delivery', r'постав|достав'),
                                  ('confirmation', r'подтвер|срок|не\s+позднее'),
                                  ('document', r'дат[ауы]\s+письма')]:
                roles.extend((hit.start(), role) for hit in re.finditer(pattern, prefix))
            # In a confirmation clause the delivery noun may be the object:
            # "Просим подтвердить поставку до <deadline>". A trailing deadline
            # preposition + confirmation anchor selects confirmation, while
            # "подтвердить дату поставки на <deliverydate>" remains delivery.
            clause = re.split(r'[;!?]|\.(?:\s+|$)', prefix)[-1]
            confirmation_deadline = (re.search(r'подтвер', clause)
                                     and re.search(r'\b(?:до|к)\s*$|\bне\s+позднее\s*$', clause))
            role = ('confirmation' if confirmation_deadline else
                    max(roles)[1] if roles else ('unknown' if followup else 'document'))
            expected_date = {'delivery':f['delivery_date'], 'confirmation':f['confirmation_deadline'],
                             'document':f['document_date']}.get(role)
            date_roles_ok &= m.group(0) == expected_date
            previous_end = m.end()
    # Explicit typed alternative addresses and job titles cannot be hidden by
    # the simultaneous presence of the correct full values elsewhere.
    city_values = re.findall(r'(?<![а-я])(?:г\.|город)\s*([а-яё-]+)', joined)
    street_values = re.findall(r'(?<![а-я])(?:ул\.|улица)\s*([^,;.]+)', joined)
    address_tokens_ok = (all(c=='казань' for c in city_values)
                         and all(s.strip()=='аделя кутуя' for s in street_values))
    role_tokens_ok = not re.search(r'\b(?:директор|начальник|менеджер|бухгалтер)[а-я]*\b|руководител[а-я]*\s+отдел', joined)
    emails = EMAIL_RE.findall(joined)
    orders = ORDER_RE.findall(joined)
    models = MODEL_RE.findall(joined)
    companies = COMPANY_RE.findall(joined)
    raw_joined = ' '.join(paragraphs)
    people = PERSON_RE.findall(unicodedata.normalize('NFC', raw_joined))
    expected_people = {normalized(f['recipient_person']), normalized(f['sender_person'])}
    expected_companies = {company_key(f['sender_company']), company_key(f['recipient_company'])}
    # Remove only typed, exact expected numeric facts. Any remaining digit is
    # an unsupported/conflicting numeric statement, including currency-free
    # wrong amounts or mixed-script malformed dates/identifiers.
    residue = joined
    for date in allowed_dates:
        residue = re.sub(r'(?<!\d)' + re.escape(date) + r'(?!\d)', ' ', residue)
    residue = residue.replace(normalized(f['order_number']), ' ').replace('дт-48', ' ')
    residue = residue.replace(normalized(f['delivery_address']), ' ')
    residue = MONEY_RE.sub(lambda m: ' ' if amount_integer(m.group('amount')) in {f['total_rub'], f['vat_included_rub']} else m.group(0), residue)
    residue = QUANTITY_RE.sub(lambda m: ' ' if m.group(1) == str(f['quantity']) else m.group(0), residue)
    residue = RATE_RE.sub(lambda m: ' ' if m.group(1) == str(f['vat_percent']) else m.group(0), residue)
    safe_negation = re.sub(r'\bне\s+позднее\b', '', joined)
    no_negation = not re.search(r'\bне\b|\bбез\s+ндс\b|\bвместо\b|за\s+исключением|отмен[а-я]*|ошибочн[а-я]*|неверн[а-я]*', safe_negation)
    quantity_ps = [i for i,p in enumerate(ps) if str(f['quantity']) in QUANTITY_RE.findall(p) and contains(p, f['item'])]
    price_ps = [i for i,p in enumerate(ps) if MONEY_RE.search(p) and contains(p, 'НДС')]
    delivery_ps = [i for i,p in enumerate(ps) if contains(p, f['delivery_date']) and contains(p, f['delivery_address']) and re.search(r'постав|достав', p)]
    confirm_ps = [i for i,p in enumerate(ps) if contains(p, f['confirmation_deadline']) and contains(p, f['contact_email']) and re.search(r'подтвер', p)]
    return dict(paragraphs=ps, joined=joined, quantity_ps=quantity_ps, price_ps=price_ps,
                delivery_ps=delivery_ps, confirm_ps=confirm_ps,
                total_seen=total_seen, vat_seen=vat_seen,
                all_dates=bool(all_dates) and set(all_dates) <= allowed_dates,
                all_date_roles=date_roles_ok, all_address_tokens=address_tokens_ok, all_job_roles=role_tokens_ok,
                all_order_models=bool(orders) and all(o == normalized(f['order_number']) for o in orders) and all(m == 'дт-48' for m in models),
                all_quantities=bool(quantities) and all(q == str(f['quantity']) for q in quantities),
                all_money=money_ok and total_seen and vat_seen,
                all_rates=bool(rates) and all(r == str(f['vat_percent']) for r in rates),
                all_emails=bool(emails) and all(e == f['contact_email'] for e in emails),
                all_companies=all(company_key(c) in expected_companies for c in companies),
                all_people=all(normalized(p) in expected_people for p in people),
                numeric_inventory=not re.search(r'\d', residue), no_negation=no_negation)


def letter_checks(body, paragraphs, styles_xml):
    raw_ps = [t for _,t,_ in paragraphs if t.strip()]
    a = fact_analysis(raw_ps)
    ps, joined, f = a['paragraphs'], a['joined'], FACTS
    purpose = [i for i,p in enumerate(ps) if contains(p, f['order_number']) and re.search(r'заказ', p) and re.search(r'соглас|постав', p)]
    greeting_pattern = (r'\b(?:уважаем[а-я]*|здравствуйте|добрый\s+(?:день|вечер)|'
                        r'доброе\s+утро|приветствую(?:\s+вас)?)\b')
    greeting = [i for i,p in enumerate(ps) if re.search(greeting_pattern, p)
                and 'марина сергеевна' in p]
    signatures = [i for i,p in enumerate(ps) if contains(p, f['sender_person']) and contains(p, f['sender_role'])]
    closing_pattern = (r'\b(?:с\s+(?:(?:глубоким|искренним)\s+)?уважением|'
                       r'с\s+(?:самыми\s+)?(?:наилучшими|лучшими|добрыми)\s+пожеланиями|'
                       r'с\s+благодарностью|благодарим\s+за|'
                       r'с\s+надеждой\s+на\s+сотрудничество|искренне\s+ваш[аи]?)\b')
    closing = [i for i,p in enumerate(ps) if re.search(closing_pattern, p)]
    header_end = min(purpose) if purpose else 0
    header = ps[:header_end]
    sender = any(company_contains(p, f['sender_company']) for p in header)
    recipient_company = any(company_contains(p, f['recipient_company']) for p in header)
    recipient_person = any(contains(p, f['recipient_person']) for p in header)
    subject = any(contains(p, f['subject']) for p in ps)
    # Require distinct actual body paragraphs for each body role, plus header,
    # greeting and signature; breaks inside a paragraph cannot supply a role.
    quantity = set(a['quantity_ps'])
    # A labelled bare quantity refers to the single named item in the immediately
    # preceding single-item order clause. Do not borrow an item from a remote
    # paragraph or accept a competing noun after the quantity unit.
    money_words = {'общая', 'общую', 'общей', 'стоимость', 'сумма', 'сумму', 'суммы',
                   'заказа', 'итого', 'итоговая', 'с', 'в', 'том', 'числе', 'ндс',
                   'включенная', 'включённая', 'включен', 'включён', 'руб', 'рублей',
                   'рубля', 'рубль', 'ставка', 'составляет', 'размере'}
    for i, p in enumerate(ps):
        quantity_label = re.match(r'количество\s*(?::|[—–-]|составляет)?\s*'
                                  + str(f['quantity']) + r'\s+комплекта\s*(?:[.;!?]|$)', p)
        # The supplementary cross-paragraph inference is intentionally bounded:
        # after its bare quantity clause only monetary/VAT prose may follow.
        monetary_tail = (quantity_label is not None and
                         all(word in money_words for word in
                             re.findall(r'[^\W\d_]+', p[quantity_label.end():])))
        if (i > 0 and i - 1 in purpose and monetary_tail
                and re.fullmatch(r'(?:просим(?:\s+вас)?\s+)?(?:согласовать|согласование)\s+'
                                 r'поставк[а-я]*\s+по\s+заказ[а-я]*\s+'
                                 + re.escape(normalized(f['order_number']))
                                 + r'\s*:\s*датчик(?:и|ов|а)?\s+дт-48[.!]?', ps[i - 1])):
            quantity.add(i)
    quantity_price = sorted(quantity & set(a['price_ps']))
    # Earliest feasible ordered roles suffice; linear bounded scans avoid
    # Cartesian products of repeated malicious paragraph-role candidates.
    previous = 0
    order_ok = header_end > 0
    for choices in [greeting, purpose, quantity_price, a['delivery_ps'], a['confirm_ps'], closing]:
        next_choices = [i for i in choices if i > previous]
        if not next_choices:
            order_ok = False
            break
        previous = min(next_choices)
    order_ok = order_ok and any(i >= previous for i in signatures)
    bad_tags = {'del','moveFrom','vanish','webHidden','instrText','fldSimple','fldChar','altChunk','object','drawing','tab'}
    # A w:tab under w:pPr/w:tabs declares a tab-stop position; it does not
    # insert a text tab. Keep rejecting actual w:r/w:tab and every hidden or
    # unsupported content tag, including declarations in styles.
    tab_stops = {id(tab) for root in (body, styles_xml)
                 for props in root.iter('{' + W + '}pPr')
                 for tabs in props.findall('{' + W + '}tabs')
                 for tab in tabs.findall('{' + W + '}tab')}
    supported = not any(e.tag == '{'+W+'}'+name and not (name == 'tab' and id(e) in tab_stops)
                        for root in (body,styles_xml) for e in root.iter() for name in bad_tags)
    supported &= len(joined) <= 16000 and not any(unicodedata.category(ch) == 'Cf' for ch in joined)
    no_template = not list(body.iter('{'+W+'}tbl')) and not re.search(r'```|(^|\n)\s*#{1,6}\s|\|', '\n'.join(raw_ps))
    no_template &= not any(p in {'проверка документа','цель','данные','решение'} for p in ps)
    header_date = any(contains(p, f['document_date']) for p in header)
    result = dict(zip(['letter_text_supported_visible','letter_direct_paragraph_structure','letter_no_template_table_markdown',
                     'letter_header_date','letter_sender_company','letter_recipient_company','letter_recipient_full_name',
                     'letter_subject','letter_greeting','letter_purpose_order','letter_quantity_item',
                     'letter_total_including_vat','letter_vat_rate','letter_included_vat_amount',
                     'letter_delivery_date_address','letter_confirmation_deadline_email','letter_sender_role_full_name',
                     'letter_sections_order','letter_all_dates_exact','letter_all_order_model_values_exact',
                     'letter_all_quantity_values_exact','letter_all_money_roles_values_exact','letter_all_vat_rates_exact',
                     'letter_all_emails_exact','letter_all_companies_exact','letter_all_person_names_exact',
                     'letter_numeric_inventory_exact','letter_no_negation_contradiction'],
                    [supported, len(ps)>=6 and order_ok, no_template, header_date, sender, recipient_company,
                     recipient_person, subject, bool(greeting), bool(purpose), bool(quantity),
                     a['total_seen'], a['all_rates'], a['vat_seen'], bool(a['delivery_ps']), bool(a['confirm_ps']),
                     bool(signatures) and bool(closing), order_ok, a['all_dates'], a['all_order_models'],
                     a['all_quantities'], a['all_money'], a['all_rates'], a['all_emails'], a['all_companies'],
                     a['all_people'], a['numeric_inventory'], a['no_negation']]))
    result.update(letter_all_date_roles_exact=a['all_date_roles'],
                  letter_all_address_tokens_exact=a['all_address_tokens'],
                  letter_all_job_roles_exact=a['all_job_roles'])
    return result


def grade_followup(value):
    """Text CONTENT ONLY. No delivery, nonce, conversation or context authority."""
    if not isinstance(value, str) or len(value) > 16000:
        return dict(verdict='FAIL', checks={'bounded_text': False}, context_acceptance=None,
                    actual_delivery_acceptance=None, raw_text_logged=False)
    a = fact_analysis([value], followup=True)
    f, joined = FACTS, normalized(value)
    checks = dict(order_number=contains(value,f['order_number']), quantity=a['all_quantities'],
                  total_rub=a['total_seen'], vat_percent=a['all_rates'], vat_included_rub=a['vat_seen'],
                  delivery_date_address=bool(a['delivery_ps']), confirmation_deadline_email=bool(a['confirm_ps']),
                  all_dates_exact=a['all_dates'], all_date_roles_exact=a['all_date_roles'],
                  all_address_tokens_exact=a['all_address_tokens'],
                  optional_company_values_consistent=a['all_companies'],
                  optional_person_values_consistent=a['all_people'],
                  all_order_model_values_exact=a['all_order_models'],
                  all_money_roles_values_exact=a['all_money'], all_emails_exact=a['all_emails'],
                  numeric_inventory_exact=a['numeric_inventory'], no_negation_contradiction=a['no_negation'],
                  unicode_supported=not any(unicodedata.category(c)=='Cf' for c in joined),
                  no_file_or_markdown=not re.search(r'```|прикреп[а-я]*\s+файл|отправ[а-я]*\s+файл', joined))
    return dict(verdict='PASS' if all(checks.values()) else 'FAIL', checks=checks,
                raw_text_logged=False, context_acceptance=None, actual_delivery_acceptance=None,
                limitation='Content only; Root must separately pin actual no-document text receipt, nonce, predecessor and native context continuity. Never proof that model remembered rather than read the named artifact.')


def tester_encoded(value):
    # Exact accepted existing tester source lines130-136, including newline.
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + '\n').encode()


def expected_create_request(nonce, name):
    return ('Новая независимая задача DOCX ' + nonce + '. Запрос Root: '
            + CREATE_QUESTION + ' Верни ровно один файл ' + name
            + ' в эту же беседу Telegram. В подписи к файлу укажи ровно: ' + nonce
            + '. Если отвечаешь также текстом, начни его с ' + nonce
            + '. Старые файлы и задания не повторять.')


def bind(binding):
    """Existing Root pin/custody mechanism; no new authority/signature scheme."""
    if binding.get('state') != 'BOUND_BY_ROOT':
        raise Rejected('binding_not_root_bound')
    if binding.get('expected_current_tuple') != CURRENT_TUPLE:
        raise Rejected('binding_current_tuple_mismatch')
    spec = pinned(binding['source_spec_ref'], 65536)
    if sha(spec) != SPEC_SHA256 or len(spec) != SPEC_BYTES:
        raise Rejected('source_spec_pin_mismatch')
    plan = json.loads(pinned(binding['actual_plan_ref']))
    if plan.get('current_tuple') != CURRENT_TUPLE or plan.get('operator') != 'Root':
        raise Rejected('actual_plan_source_tuple_mismatch')
    run_id = binding.get('expected_run_id')
    if not isinstance(run_id,str) or not run_id or len(run_id)>160 or plan.get('new_run_id') != run_id:
        raise Rejected('actual_plan_run_id_mismatch')
    task = plan['new_task']
    nonce, name = task['nonce'], task['output_filename']
    if (set(task) != {'kind','nonce','question','output_filename'} or task['kind'] != 'distinct-docx-create'
            or not isinstance(nonce,str) or re.fullmatch('[0-9a-f]{32}',nonce) is None
            or name != 'friday_report_check_117_' + nonce + '.docx'
            or task['question'] != CREATE_QUESTION):
        raise Rejected('actual_plan_filename_nonce_question_mismatch')
    if binding.get('output_filename') != name or binding.get('nonce') != nonce:
        raise Rejected('binding_filename_nonce_mismatch')
    scenario = plan['new_scenario']
    steps = scenario.get('steps')
    request = expected_create_request(nonce,name)
    if (not isinstance(steps,list) or len(steps)!=1 or set(steps[0])!={'request','observe'}
            or steps[0]['request'] != request or scenario.get('deadline_seconds') != 300
            or steps[0]['observe'].get('window_seconds') != 180
            or steps[0]['observe'].get('max_documents') != 1):
        raise Rejected('actual_plan_scenario_request_mismatch')
    artifact = binding['actual_received_artifact_ref']
    if (not isinstance(artifact.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',artifact['sha256'])
            or type(artifact.get('bytes')) is not int or not 0<artifact['bytes']<=LIMITS['archive_bytes_max']):
        raise Rejected('artifact_identity_invalid')
    pinned(artifact, LIMITS['archive_bytes_max'])
    artifact_stat = os.stat(artifact['path'], follow_symlinks=False)
    source_refs = binding.get('source_only_artifact_refs')
    if not isinstance(source_refs,list):
        raise Rejected('source_only_reference_list_missing')
    for ref in source_refs + [binding['source_spec_ref'],binding['actual_plan_ref']]:
        pinned(ref)
        source_stat = os.stat(ref['path'], follow_symlinks=False)
        if (os.path.abspath(ref['path'])==os.path.abspath(artifact['path'])
                or (source_stat.st_dev,source_stat.st_ino)==(artifact_stat.st_dev,artifact_stat.st_ino)):
            raise Rejected('source_only_artifact_not_returned_result')
    custody = json.loads(pinned(binding['native_custody_grade_ref']))
    schema = binding.get('expected_custody_schema')
    if not isinstance(schema,str) or not schema or custody.get('schema') != schema:
        raise Rejected('custody_schema_mismatch')
    if custody.get('refs',{}).get('received') != artifact:
        raise Rejected('custody_artifact_reference_mismatch')
    for key,custody_key in [('native_immutable_receipt_journal_ref','native_candidate_journal'),
                            ('receiver_receipt_ref','receipt'),('actual_run_ref','run')]:
        if custody.get('refs',{}).get(custody_key) != binding[key]:
            raise Rejected('custody_reference_mismatch_'+custody_key)
        pinned(binding[key])
    run = json.loads(pinned(binding['actual_run_ref']))
    scenario_hash = sha(tester_encoded(scenario))
    if (run.get('id')!=run_id or run.get('scenario')!=scenario or run.get('scenario_sha256')!=scenario_hash
            or run.get('step')!=0 or run.get('status')!='EVIDENCE_READY' or run.get('send_state')!='sent'):
        raise Rejected('plan_run_scenario_mismatch')
    sent = run.get('sent_message_id')
    if type(sent) is not int or sent<=0 or run.get('sent_ids') != [sent]:
        raise Rejected('run_sent_identity_mismatch')
    params = {'chat_id':'@jerichodevbot','text':request}
    request_hash = sha(tester_encoded(params))
    metadata = run.get('request_metadata',{})
    if (metadata.get('method')!='sendMessage' or metadata.get('params')!=params
            or metadata.get('body_sha256')!=request_hash or metadata.get('body_bytes')!=len(tester_encoded(params))):
        raise Rejected('run_request_bytes_mismatch')
    receipt = json.loads(pinned(binding['receiver_receipt_ref']))
    advertised, info = receipt.get('advertised_document',{}), receipt.get('get_file',{})
    if (receipt.get('kind')!='document' or receipt.get('path')!=artifact['path']
            or receipt.get('sha256')!=artifact['sha256'] or receipt.get('bytes')!=artifact['bytes']
            or receipt.get('complete_artifact') is not True or advertised.get('file_name')!=name
            or advertised.get('mime_type')!=DOCX_MIME or receipt.get('caption')!=nonce
            or advertised.get('file_size')!=artifact['bytes'] or info.get('file_size')!=artifact['bytes']
            or not advertised.get('file_id') or advertised.get('file_id')!=info.get('file_id')
            or not advertised.get('file_unique_id') or advertised.get('file_unique_id')!=info.get('file_unique_id')):
        raise Rejected('receiver_filename_mime_nonce_artifact_mismatch')
    for key,expected in [('run_id',run_id),('scenario_sha256',scenario_hash),('step',0),
                         ('sent_message_id',sent),('sent_ids',[sent]),('request_body_sha256',request_hash)]:
        if receipt.get(key)!=expected:
            raise Rejected('receiver_run_request_mismatch_'+key)
    custody_checks = custody.get('checks',{})
    custody_pass = (custody.get('state')=='PASS' and set(custody_checks)==CUSTODY_IDS
                    and all(v is True for v in custody_checks.values()))
    return artifact,dict(output_filename=name,nonce=nonce,native_custody_pass=custody_pass,
                         native_custody_check_count=len(custody_checks),
                         root_authentication='Root-bound exact refs; no independent signature scheme invented',
                         current_tuple=CURRENT_TUPLE,source_only_separated=True,
                         semantics_delivery_context_separate=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binding', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    start = time.monotonic()
    def deadline(signum, frame):
        raise TimeoutError('new_readonly_grade_execution_budget_exhausted')
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 160)
    raw, unchanged = read_regular(args.binding, 1048576)
    if not unchanged:
        raise Rejected('binding_changed')
    binding = json.loads(raw)
    artifact, custody = bind(binding)
    result = grade(artifact['path'], artifact['sha256'], artifact['bytes'])
    result.update(schema='frw.S223.independent-business-letter-semantic-grade.v1',
                  binding_ref={'path': args.binding, 'sha256': sha(raw), 'bytes': len(raw)},
                  custody_binding=custody, old_R116_R136_semantic_verdict_preserved='FAIL', contextual_acceptance=None,
                  acceptance='ACTUAL_DOCX_SEMANTICS_AND_SEPARATE_ROOT_CUSTODY_PASS' if result['verdict'] == 'PASS' and custody['native_custody_pass'] else 'NOT_ACCEPTED')
    result['timing'] = dict(scope='separate new read-only grade; old live windows/effects not reopened',
                            origin_monotonic=start, limit_seconds=180, reserve_seconds=20,
                            elapsed_seconds=round(time.monotonic()-start, 6))
    if result['timing']['elapsed_seconds'] > 160:
        result['acceptance'] = 'NOT_ACCEPTED_DEADLINE_EXCEEDED'
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    signal.setitimer(signal.ITIMER_REAL, 0)
    print(json.dumps({'verdict': result['verdict'], 'acceptance': result['acceptance'],
                      'check_counts': result['check_counts'], 'output': args.output}))


if __name__ == '__main__':
    main()
