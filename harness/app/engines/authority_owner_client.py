"""Explicit opt-in reference client for the sole authority owner.

No local cache and NO fallback to process-local authority on transport errors.
This does not turn Python process locks into distributed locks; final synthetic
consequence enforcement remains in the owner's SQLite transaction.
"""
import json
import os
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit

class AuthorityOwnerUnavailable(RuntimeError):
    pass

def _configuration():
    base=os.environ["FLOWSIGNAL_AUTHORITY_OWNER_URL"].rstrip("/")
    parsed=urlsplit(base)
    if parsed.scheme!="http" or parsed.hostname not in ("127.0.0.1","localhost") or not parsed.port:
        raise AuthorityOwnerUnavailable("reference authority owner must be loopback")
    return base

def _send(path,*,body=None,admin=False):
    base=_configuration()
    credential=(os.environ.get("FLOWSIGNAL_AUTHORITY_OWNER_ADMIN_TOKEN")
        if admin else os.environ.get("FLOWSIGNAL_AUTHORITY_OWNER_READ_TOKEN"))
    if not credential:
        raise AuthorityOwnerUnavailable("required authority-owner credential missing")
    headers={
        "X-Authority-Admin-Token" if admin else "X-Authority-Read-Token":credential
    }
    if body is not None:
        headers["Content-Type"]="application/json"
    request=Request(base+path,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method="POST" if body is not None else "GET")
    try:
        with urlopen(request,timeout=2.0) as response:
            if response.status!=200:
                raise AuthorityOwnerUnavailable("authority owner did not authorize request")
            data=json.loads(response.read())
    except (HTTPError,URLError,OSError,ValueError,TypeError) as error:
        raise AuthorityOwnerUnavailable("authority owner unavailable or refused operation") from error
    if not isinstance(data,dict) or type(data.get("version")) is not int:
        raise AuthorityOwnerUnavailable("invalid owner response")
    return data["version"]

def authoritative_version():
    return _send("/current")

def revoke_authority():
    return _send("/revoke",body={"reason":"reference authority withdrawal"},admin=True)
