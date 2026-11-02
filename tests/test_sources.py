"""A 200 response must contain the incident, not just a status-page shell."""
import hashlib
from datetime import datetime
from types import SimpleNamespace

import pytest
import verify_sources as verify


class Response:
    def __init__(self, body, status=200):
        self.body=body
        self.status=status
        self.url='https://example.com/report'
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self):
        return self.body


@pytest.mark.parametrize('body,status,good', [
    (b'<h1>Incident impact</h1><p>Details</p>',200,True),
    (b'<h1>Status</h1>',200,False),
    (b'<script>Incident impact</script><p>Status</p>',200,False),
    (b'<h1>Incident impact</h1>',503,False),
])
def test_source_check_requires_real_section(monkeypatch,body,status,good):
    monkeypatch.setattr(verify,'urlopen',lambda *a,**kw:Response(body,status))
    source=dict(key='example',url='https://example.com/report')
    cases=[dict(id='PUB-1',source_section='Incident impact')]
    if not good:
        with pytest.raises(ValueError):
            verify.check(source,cases)
    else:
        receipt=verify.check(source,cases)
        assert receipt['sha256']==hashlib.sha256(body).hexdigest()
        assert receipt['status']==200
        assert datetime.fromisoformat(receipt['verified_at']).tzinfo is not None
