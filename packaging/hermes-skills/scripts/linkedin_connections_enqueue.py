"""Queue a due LinkedIn acceptance check for the sole VB Jobs browser owner.
This scheduler intentionally has no browser or send permissions of its own.
"""
from pathlib import Path
import json,datetime,uuid,fcntl,argparse,tempfile
ROOT=Path.home() / ('Hermes/job-applications/linkedin-accepted-followups')

def enqueue(root):
 root.mkdir(parents=True,exist_ok=True)
 with (root/'queue.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);p=root/'pending-request.json'
  if p.exists():return {'queued':False,'reason':'Existing pending request retained','request':json.loads(p.read_text())}
  request={'request_id':str(uuid.uuid4()),'requested_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'type':'linkedin_accepted_job_connections','authorized_interval_hours':12,'owner_job_id':'5da11e02ae22','instructions_file':str(ROOT/'owner-instructions.md'),'status':'pending','no_repeat':True,'application_credit':0}
  temp=p.with_suffix('.json.new');temp.write_text(json.dumps(request,indent=2)+'\n');temp.replace(p)
  with (root/'requests.jsonl').open('a') as f:f.write(json.dumps(request)+'\n')
  return {'queued':True,'request':request}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--test',action='store_true');a=p.parse_args()
 if a.test:
  with tempfile.TemporaryDirectory(prefix='linkedin-queue-test-',dir='~/.hermes/profiles/vb-jobs/cache/scratch') as t:
   root=Path(t);first=enqueue(root);second=enqueue(root)
   assert first['queued'] and not second['queued'] and first['request']['request_id']==second['request']['request_id']
   old=first['request']['request_id'];ack=root/'completed';ack.mkdir();(root/'pending-request.json').replace(ack/(old+'.json'));third=enqueue(root)
   assert third['queued'] and third['request']['request_id']!=old and len((root/'requests.jsonl').read_text().splitlines())==2
   print(json.dumps({'tests_passed':['queues_request','coalesces_pending_without_duplicate','new_request_after_acknowledgment'],'browser_side_effects':0,'messages_sent':0}))
 else:
  enqueue(ROOT)  # Empty stdout: no routine Telegram or local delivery noise.
