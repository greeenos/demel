import json
import time
from backend import db, notifications


def test_vapid_key_can_sign_real_claims_and_push_uses_key_object(logged, monkeypatch):
    claims = {"sub":"mailto:admin@vital.local","aud":"https://web.push.apple.com","exp":int(time.time())+3600}
    captured=[]
    def fake_webpush(**kwargs):
        signed=kwargs["vapid_private_key"].sign(claims)
        assert signed["Authorization"].startswith("vapid ")
        captured.append(json.loads(kwargs["data"]))
    monkeypatch.setattr(notifications,"webpush",fake_webpush)
    sub={"endpoint":"https://web.push.apple.com/example","keys":{}}
    with db.db() as c:
        c.execute("INSERT INTO push VALUES(?,?)",(sub["endpoint"],json.dumps(sub)))
    assert notifications.send("Test","Body")==1
    assert captured[0]["title"]=="Test"
