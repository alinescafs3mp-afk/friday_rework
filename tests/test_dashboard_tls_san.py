"""Real OpenSSL memory-BIO checks of mandatory guest and public SANs."""
import datetime
import ipaddress
import ssl

import pytest

from hermes_cli import friday_dashboard_tls as tls


GUEST = '192.168.12.128'
PUBLIC_DNS = 'dashboard.example'
OWNER_IP = '192.168.1.78'


@pytest.fixture(scope='module')
def san_certificates(tmp_path_factory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SYNTHETIC SAN TEST CA')])
    ca = (x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-datetime.timedelta(minutes=1))
          .not_valid_after(now+datetime.timedelta(hours=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    homes = {}
    for label, public_san in [('public-cn-only', None), ('public-dns', x509.DNSName(PUBLIC_DNS)),
                              ('owner-ip', x509.IPAddress(ipaddress.ip_address(OWNER_IP)))]:
        sans = [x509.IPAddress(ipaddress.ip_address(GUEST))]
        if public_san is not None:
            sans.append(public_san)
        leaf = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, PUBLIC_DNS)]))
                .issuer_name(issuer).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now-datetime.timedelta(minutes=1))
                .not_valid_after(now+datetime.timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.SubjectAlternativeName(sans), critical=False)
                .sign(ca_key, hashes.SHA256()))
        home = tmp_path_factory.mktemp(label)
        home.chmod(0o700)
        folder = home/'dashboard-tls'
        folder.mkdir(mode=0o700)
        (folder/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        (folder/'server.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        (folder/'server.key').write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
        for path in folder.iterdir():
            path.chmod(0o600)
        homes[label] = home
    return homes


def test_public_dns_common_name_cannot_replace_required_san(san_certificates):
    with pytest.raises(ssl.SSLCertVerificationError):
        tls.checked(san_certificates['public-cn-only'], tls.FILES, GUEST, 9119,
                    f'https://{PUBLIC_DNS}:9119')


@pytest.mark.parametrize('label,public_host', [('public-dns', PUBLIC_DNS), ('owner-ip', OWNER_IP)])
def test_explicit_guest_and_public_sans_work(san_certificates, label, public_host):
    _, context = tls.checked(san_certificates[label], tls.FILES, GUEST, 9119,
                             f'https://{public_host}:9119')
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.hostname_checks_common_name is False


def test_returned_context_keeps_san_only_policy_for_native_clients(san_certificates):
    _, context = tls.checked(san_certificates['public-dns'], tls.FILES, GUEST, 9119,
                             f'https://{PUBLIC_DNS}:9119')
    home = san_certificates['public-cn-only']
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(home/'dashboard-tls/server.pem'), str(home/'dashboard-tls/server.key'))
    tls.handshake(server, context, GUEST)
    with pytest.raises(ssl.SSLCertVerificationError):
        tls.handshake(server, context, PUBLIC_DNS)
