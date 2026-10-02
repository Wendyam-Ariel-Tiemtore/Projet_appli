import io
import zipfile

import pytest
from cryptography.exceptions import InvalidTag

from analyste.report.docx_builder import _safe_cell
from analyste.security import crypto
from analyste.security.auth import password_problems
from analyste.security.web import UploadError, safe_filename, validate_upload


def test_chiffrement_aller_retour_et_integrite():
    k = crypto.new_key()
    blob = crypto.encrypt(k, b"donnees sensibles", b"projet1")
    assert b"sensibles" not in blob
    assert crypto.decrypt(k, blob, b"projet1") == b"donnees sensibles"
    with pytest.raises(InvalidTag):
        crypto.decrypt(k, blob, b"projet2")  # contexte différent : refus
    alt = bytearray(blob)
    alt[-1] ^= 1
    with pytest.raises(InvalidTag):
        crypto.decrypt(k, bytes(alt), b"projet1")  # altération détectée


def test_enveloppe_de_cle():
    master = crypto.new_key()
    k = crypto.new_key()
    w = crypto.wrap_key(master, k, "abc")
    assert crypto.unwrap_key(master, w, "abc") == k
    with pytest.raises(InvalidTag):
        crypto.unwrap_key(master, w, "autre")


@pytest.mark.parametrize("pwd,ok", [("court", False), ("toutenminuscules", False), ("Motdepasse-2026!", True),
                                     ("ariel-Solide-2026", False)])
def test_politique_mot_de_passe(pwd, ok):
    assert (not password_problems(pwd, "ariel")) is ok


def test_fichier_renomme_refuse():
    with pytest.raises(UploadError):
        validate_upload("donnees.xlsx", b"a;b\n1;2\n", 10_000)
    with pytest.raises(UploadError):
        validate_upload("donnees.sav", b"not spss", 10_000)
    with pytest.raises(UploadError):
        validate_upload("donnees.csv", b"MZ\x90\x00binaire", 10_000)
    with pytest.raises(UploadError):
        validate_upload("donnees.exe", b"a,b", 10_000)


def test_taille_maximale():
    with pytest.raises(UploadError):
        validate_upload("d.csv", b"a,b\n" * 1000, 100)


def test_bombe_de_decompression_refusee():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "0" * (50 * 1024 * 1024))
    with pytest.raises(UploadError, match="anormalement"):
        validate_upload("bombe.xlsx", buf.getvalue(), 60 * 1024 * 1024)


def test_macros_refusees():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<w/>")
        z.writestr("xl/vbaProject.bin", "x")
    with pytest.raises(UploadError, match="macros"):
        validate_upload("m.xlsx", buf.getvalue(), 10_000_000)


def test_nom_de_fichier_nettoye():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert "/" not in safe_filename("a/b\\c<script>.csv")


def test_injection_de_formule_neutralisee():
    assert _safe_cell("=HYPERLINK(\"http://x\")").startswith("'")
    assert _safe_cell("-3,5") == "-3,5"
    assert _safe_cell("@SUM(A1)").startswith("'")
