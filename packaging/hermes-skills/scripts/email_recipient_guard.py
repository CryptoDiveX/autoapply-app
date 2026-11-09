"""Fail-closed VB Jobs recipient suppression guard, no network or sending."""
from pathlib import Path
import json,sys
from email.utils import getaddresses
REGISTRY=Path.home() / ('Hermes/job-applications/outreach-database/email-suppression.json')
HOLD=Path.home() / ('Hermes/job-applications/daily-100-applications/EMAIL_AUDIT_HOLD.json')

def check(values,registry=REGISTRY,hold=HOLD):
    if hold.exists():
        state=json.loads(hold.read_text())
        if state.get('outbound_email_hold'):raise RuntimeError('Outbound email held for bounce-suppression audit. Native applications unaffected.')
    data=json.loads(registry.read_text())
    rows=data['blocked_addresses']
    blocked={r['email'].strip().casefold() for r in rows if r.get('blocked') is True}
    if data['count']!=len(rows) or len(blocked)!=len(rows):raise RuntimeError('Invalid suppression register, fail closed')
    recipients=[addr.strip().casefold() for _,addr in getaddresses(values)]
    if not recipients or any('@' not in r or '\n' in r or '\r' in r for r in recipients):raise RuntimeError('No valid explicit recipients')
    hits=sorted(set(recipients)&blocked)
    if hits:raise RuntimeError('DO NOT EMAIL, suppressed recipient(s): '+', '.join(hits))
    return {'allowed':True,'recipients':recipients,'suppression_count':len(blocked),'registry':str(registry),'scope':'Suppression only, not employer/contact/consent or send authorization'}

if __name__=='__main__':
    try:print(json.dumps(check(sys.argv[1:])))
    except Exception as exc:print(json.dumps({'allowed':False,'error':str(exc)}));sys.exit(2)
