"""Bearer authentication shared by the local operator gateway and tests."""
import hmac

def authenticate(header,token):
    return bool(isinstance(token,str) and len(token)>=32 and isinstance(header,str)
                and hmac.compare_digest(header.encode(),('Bearer '+token).encode()))
