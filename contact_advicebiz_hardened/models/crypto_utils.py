import os

from cryptography.fernet import Fernet, InvalidToken

from odoo import _
from odoo.exceptions import UserError


KEY_ENV = "ADVICEBIZ_ACCESS_DATA_FERNET_KEY"
TOKEN_PREFIX = "abzfernet:v1:"


def _get_fernet():
    """Return the Fernet instance using a key kept outside the Odoo database."""
    raw_key = (os.environ.get(KEY_ENV) or "").strip()
    if not raw_key:
        raise UserError(_(
            "A chave de encriptação dos Dados de Acesso não está configurada. "
            "Defina a variável de ambiente %s no serviço Odoo e reinicie o servidor."
        ) % KEY_ENV)

    try:
        return Fernet(raw_key.encode("ascii"))
    except (ValueError, TypeError):
        raise UserError(_(
            "A variável %s não contém uma chave Fernet válida. "
            "A chave deve ser uma chave Fernet URL-safe base64 de 32 bytes."
        ) % KEY_ENV)


def is_encrypted(value):
    return bool(value) and value.startswith(TOKEN_PREFIX)


def encrypt_secret(value):
    if not value:
        return False
    if is_encrypted(value):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return TOKEN_PREFIX + token


def decrypt_secret(value):
    if not value:
        return False
    if not is_encrypted(value):
        raise UserError(_(
            "Foi encontrado um valor de password legado ainda não cifrado. "
            "Atualize o módulo para concluir a migração antes de visualizar a password."
        ))

    token = value[len(TOKEN_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise UserError(_(
            "Não foi possível desencriptar a password. A chave configurada não corresponde "
            "à chave usada para cifrar os dados, ou o valor armazenado está corrompido."
        ))
