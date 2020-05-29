import shutil

import pytest


@pytest.mark.parametrize("val,expected", [
    ("t", True),  # truthy
    ("T", True),
    ("true", True),
    ("True", True),
    ("TRUE", True),
    ("1", True),
    (1, True),
    (True, True),
    ("f", False),  # falsy
    ("F", False),
    ("false", False),
    ("False", False),
    ("FALSE", False),
    ("0", False),
    (0, False),
    (False, False),
    ("random", False),  # misc
    (None, False),
])
def test_as_boolean(val, expected):
    from pygluu.containerlib.utils import as_boolean
    assert as_boolean(val) == expected


@pytest.mark.parametrize("value, expected", [
    ("a", "a"),
    (1, "1"),
    (b"b", "b"),
    (True, "true"),
    (False, "false"),
    (None, "null"),
    ([], "[]"),
])
def test_safe_value(value, expected):
    from pygluu.containerlib.utils import safe_value
    assert safe_value(value) == expected


@pytest.mark.parametrize("size", [12, 10])
def test_get_random_chars(size):
    from pygluu.containerlib.utils import get_random_chars
    assert len(get_random_chars(size)) == size


@pytest.mark.parametrize("size", [12, 10])
def test_get_sys_random_chars(size):
    from pygluu.containerlib.utils import get_sys_random_chars
    assert len(get_sys_random_chars(size)) == size


# def test_get_quad():
#     from pygluu.containerlib.utils import get_quad
#     assert len(get_quad()) == 4


# def test_join_quad_str():
#     from pygluu.containerlib.utils import join_quad_str

#     # should have dot char
#     assert join_quad_str(2).find(".") != 0
#     assert len(join_quad_str(2)) == 9


# @pytest.mark.parametrize("val, expected", [
#     ("@1234", "1234"),
#     ("!1234", "1234"),
#     (".1234", "1234")
# ])
# def test_safe_inum_str(val, expected):
#     from pygluu.containerlib.utils import safe_inum_str
#     assert safe_inum_str(val) == expected


@pytest.mark.parametrize("cmd", ["echo foobar"])
def test_exec_cmd(cmd):
    from pygluu.containerlib.utils import exec_cmd

    out, err, code = exec_cmd(cmd)
    assert out == b"foobar"
    assert err == b""
    assert code == 0


@pytest.mark.parametrize("txt, ctx, expected", [
    ("%id", {}, "%id"),
    ("%(id)s", {"id": 1}, "1"),
])
def test_safe_render(txt, ctx, expected):
    from pygluu.containerlib.utils import safe_render
    assert safe_render(txt, ctx) == expected


@pytest.mark.parametrize("text, num_spaces, expected", [
    ("ab\n\tcd", 0, "ab\ncd"),
    ("ab\n\tcd", 1, " ab\n cd"),
])
def test_reindent(text, num_spaces, expected):
    from pygluu.containerlib.utils import reindent
    assert reindent(text, num_spaces) == expected


@pytest.mark.parametrize("text, num_spaces, expected", [
    ("abcd", 0, "YWJjZA=="),
    ("abcd", 1, " YWJjZA=="),
    (b"abcd", 0, "YWJjZA=="),
    (b"abcd", 1, " YWJjZA=="),
])
def test_generate_base64_contents(text, num_spaces, expected):
    from pygluu.containerlib.utils import generate_base64_contents
    assert generate_base64_contents(text, num_spaces) == expected


@pytest.mark.parametrize("text, key, expected", [
    ("abcd", "a" * 24, b"YgH8NDxhxmA="),
    ("abcd", b"a" * 24, b"YgH8NDxhxmA="),
    (b"abcd", "a" * 24, b"YgH8NDxhxmA="),
    (b"abcd", b"a" * 24, b"YgH8NDxhxmA="),
])
def test_encode_text(text, key, expected):
    from pygluu.containerlib.utils import encode_text
    assert encode_text(text, key) == expected


@pytest.mark.parametrize("encoded_text, key, expected", [
    ("YgH8NDxhxmA=", "a" * 24, b"abcd"),
    ("YgH8NDxhxmA=", b"a" * 24, b"abcd"),
    (b"YgH8NDxhxmA=", "a" * 24, b"abcd"),
    (b"YgH8NDxhxmA=", b"a" * 24, b"abcd"),
])
def test_decode_text(encoded_text, key, expected):
    from pygluu.containerlib.utils import decode_text
    assert decode_text(encoded_text, key) == expected


@pytest.mark.skipif(
    shutil.which("keytool") is None,
    reason="requires keytool executable"
)
def test_cert_to_truststore(tmpdir):
    from pygluu.containerlib.utils import cert_to_truststore

    tmp = tmpdir.mkdir("pygluu")
    keystore_file = tmp.join("gluu.jks")
    cert_file = tmp.join("gluu.crt")

    # dummy cert
    cert_file.write("""-----BEGIN CERTIFICATE-----
MIIEGDCCAgCgAwIBAgIRANslKJCe/whYi01rkUOAxh0wDQYJKoZIhvcNAQELBQAw
DTELMAkGA1UEAxMCQ0EwHhcNMTkxMTI1MDQwOTQ4WhcNMjEwNTI1MDQwOTE4WjAP
MQ0wCwYDVQQDEwRnbHV1MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA
05TqppxdpSP9vzQP42YFPM79K3TdOFmsCJLMnKRkeR994MGra6JQ75/+vYmKXJaU
Bo3/VieU2pGaAsXI7MqNfXQcKSwAoGU03xqoBUS8INIYX+Cr7q8jFp1q2VLqpNlt
zWZQsee2TUIsa7MzJ5UK7QnaqK4uadl9XHlkRdXC5APecJoRJK4K1UZ59TyiMisz
Dqf+DrmCaJpIPph4Ro9TZMdoE9CX2mFz6Q+ItaSXvyNqUabip7iIwFf3Mu1pal98
AogsfKcfvu+ki93slrJ6jiDIi5B+D0gbA4E03ncgdfQ8Vs55BZbI0N5uEypfI0ky
LQ6201p4bRRXX4LKooObCwIDAQABo3EwbzAOBgNVHQ8BAf8EBAMCA7gwHQYDVR0l
BBYwFAYIKwYBBQUHAwEGCCsGAQUFBwMCMB0GA1UdDgQWBBROCOakMthTjAwM7MTP
RnkvLRHMOjAfBgNVHSMEGDAWgBTeSnpdqVZhjCRnCKJFfwiGwnVCvTANBgkqhkiG
9w0BAQsFAAOCAgEAjBOt4xgsiW3BN/ZZ6DehrdmRZRrezwhBWwUrnY9ajmwv0Trs
4sd8EP7RuJsGS5gdUy/qzogSEhUyMz4+iRy/OW9bdzOFe+WDU6Xh9Be/C2Dv9osa
5dsG+Q9/EM9Z2LqKB5/uJJi5xgXdYwRXATDsBdNI8LxQQz0RdCZIJlpqsDEd1qbH
8YX/4cnknuL/7NsqLvn5iZvQcYFA/mfsN8zN52StuRONf1RKdQ3rwT7KehGi7aUa
IWwLEnzLmeZFLUWBl6h2uUMOUe1J8Di176K3SP5pCeb8+gQd5b2ra/IutN7lpISD
7YSStLNCCT33sjbximvX0ur/VipQQO1B/dz9Ua1kPPKV/blTXCiKNf+PpepaFBIp
jIb/dBIq9pLPBWtGz4tCNQIORDBpQjfPpSNH3lEjTyWUOttJYkss6LHAnnQ8COyk
IsbroXkmDKy86qHKlUc7L4REBykLDL7Olm4yQC8Zg46PaG5ymfYVuHd+tC7IZj8H
FRnpMhUJ4+bn+h0kxS4agwb2uCSO4Ge7edViq6ZFZnnfOG6zsz3VJRV71Zw2CQAL
0MxrbeozSHyNrbT2uAGyV85pNJmwZVlBfyKywMWsG3HcoKAhxg//IqNv0pi48Ey9
2xLnWTK3GxoBMh3mpjub+jf6OYDwmh0eBxm+PRMVAe3QB1eG/GGKgEwaTrc=
-----END CERTIFICATE-----""")

    _, _, code = cert_to_truststore(
        "gluu_https", str(cert_file), str(keystore_file), "secret",
    )
    assert code == 0


def test_get_server_certificate(tmpdir, httpsserver):
    from pygluu.containerlib.utils import get_server_certificate

    host, port = httpsserver.server_address
    filepath = tmpdir.mkdir("pygluu").join("gluu.crt")

    cert = get_server_certificate(host, port, str(filepath))
    assert cert == filepath.read()


def test_ldap_encode():
    from pygluu.containerlib.utils import ldap_encode

    assert ldap_encode("secret").startswith("{ssha}")
