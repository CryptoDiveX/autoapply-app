from pathlib import Path
import datetime,json,collections,os
from zoneinfo import ZoneInfo
B=Path.home() / ('Hermes/job-applications');D=B/'daily-100-applications';D.mkdir(exist_ok=True);N=B/'overnight-100-more-20261017T005251Z';C=B/'overnight-approved-100-20261015T0155Z/continuation-20261015';tz=ZoneInfo('America/Vancouver');now=datetime.datetime.now(datetime.timezone.utc);local=now.astimezone(tz);start=datetime.datetime.combine(local.date(),datetime.time(),tz);end=datetime.datetime.combine(local.date()+datetime.timedelta(days=1),datetime.time(),tz)
paths=[C.parent/'verified-submissions.jsonl',C/'verified-submissions.jsonl'];latest={};events=[];source_counts={}
for p in paths:
 rows=[json.loads(l) for l in p.read_text().splitlines() if l.strip()];source_counts[str(p)]=len(rows)
 for r in rows:
  key=(r.get('end_client') or r.get('direct_employer') or r.get('company') or '').strip().casefold()
  if key:latest[key]=r;events.append(r)
# Later lifecycle events replace earlier positives. Original application timestamps, not log/update times, assign a day.
verified=[];unresolved=[]
for key,r in latest.items():
 if r.get('status')!='verified_submitted':continue
 stamp=r.get('submitted_at') or r.get('submitted_utc') or r.get('applied_at')
 if not stamp:continue
 try:t=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
 except (ValueError,TypeError):continue
 if t.tzinfo is None:unresolved.append({'company':r.get('company'),'reason':'naive submission timestamp'});continue
 if not (start<=t.astimezone(tz)<end):continue
 verified.append(r)
# Keep advertiser status explicit. Unknown role type or absent files cannot earn strict daily named-job credit.
counted=[];general=[];excluded=[]
def exists_any(r,fields):
 for key in fields:
  v=r.get(key)
  if not isinstance(v,str) or not v:continue
  p=Path(v)
  if not p.is_absolute():p=Path(r.get('artifact_root') or C)/p
  if p.is_file():return True
 return False
for r in verified:
 v={'company':r.get('company'),'role':r.get('role'),'submitted_at':r.get('submitted_at'),'teal_id':r.get('teal_id'),'artifact_root':r.get('artifact_root'),'named_vacancy':r.get('named_vacancy'),'application_type':r.get('application_type')}
 if r.get('named_vacancy') is False:general.append(v);continue
 if r.get('named_vacancy') is not True:v['reason']='advertised named vacancy not explicitly established';excluded.append(v);continue
 gates={'submit_proof':exists_any(r,['submit_proof','native_request_proof','native_response_proof']),'resume_receipt':exists_any(r,['resume_receipt','approved_resume_receipt','approved_file_receipt']),'Teal_proof':exists_any(r,['teal_readback','teal_proof']),'claim_form_QA':exists_any(r,['claim_qa','form_qa','independent_audit'])}
 if not all(gates.values()):v['reason']='missing saved proof reference';v['proof_gates']=gates;excluded.append(v);continue
 if r.get('strict_approved_file_checkpoint_credit')==0 or r.get('application_credit')==0:v['reason']='explicit strict credit withheld';excluded.append(v);continue
 counted.append(v)
# Additional named native submissions withheld from strict ledger remain visible as unresolved, not resubmitted.
for key,r in latest.items():
 status=r.get('status') or '';stamp=r.get('submitted_at') or r.get('submitted_utc') or r.get('applied_at')
 if status=='verified_submitted' or not stamp:continue
 try:t=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
 except (ValueError,TypeError):continue
 if t.tzinfo is not None and start<=t.astimezone(tz)<end and any(s in status for s in ['file_binding','unverified','profile_only','withheld']):unresolved.append({'company':r.get('company'),'role':r.get('role'),'status':status,'submitted_at':stamp,'reason':'not strict verified named credit; do not resubmit'})
actual_day_seconds=(end.astimezone(datetime.timezone.utc)-start.astimezone(datetime.timezone.utc)).total_seconds();elapsed=(now-start.astimezone(datetime.timezone.utc)).total_seconds();target=100;expected=target*max(0,min(elapsed,actual_day_seconds))/actual_day_seconds
result={'checked_at':now.isoformat(),'date':local.date().isoformat(),'timezone':'America/Vancouver','day_start_utc':start.astimezone(datetime.timezone.utc).isoformat(),'day_end_utc':end.astimezone(datetime.timezone.utc).isoformat(),'daily_named_job_target':target,'named_job_verified_status_and_saved_proof_count':len(counted),'remaining_named_job_target':max(0,target-len(counted)),'general_future_intakes_separate':len(general),'unresolved_or_excluded_named':len(excluded),'expected_by_elapsed_day_fraction':round(expected,2),'behind_elapsed_day_pace':len(counted)<expected,'required_average_verified_per_hour':round(target/(actual_day_seconds/3600),4),'source_rows':source_counts,'counted_named':counted,'general_intakes':general,'proof_or_type_exclusions':excluded,'other_unresolved_lifecycle':unresolved,'count_basis':'Latest source lifecycle plus actual provider/native timestamp in Vancouver day, explicit named vacancy, saved proof-reference presence and no explicit withheld credit. Mechanical checkpoint, not a fresh live-account/full-content audit. Later bounces/withdrawals/quality incidents must update source lifecycle and revoke credit. One employer/endclient per30days still enforced by submission owner.','continuous_authorization':'Daily target and daily report are not automatic stop signals; original100MORE ledger and historical totals are not reset.'}
for p in [D/(local.date().isoformat()+'.json'),D/'latest.json']:
 temp=p.with_suffix(p.suffix+'.new');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');os.replace(temp,p)
if __name__=='__main__' and '--print' in __import__('sys').argv:print(json.dumps({k:result[k] for k in ['date','timezone','daily_named_job_target','named_job_verified_status_and_saved_proof_count','remaining_named_job_target','general_future_intakes_separate','unresolved_or_excluded_named','expected_by_elapsed_day_fraction','required_average_verified_per_hour','behind_elapsed_day_pace']},indent=2))
