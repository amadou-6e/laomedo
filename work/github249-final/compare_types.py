"""Compare complete TS messages, normalizing only checkout roots and union order."""
import collections,json,re
from pathlib import Path


def main():
 root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';candidate=Path(json.loads((e/'frontend-path.json').read_text())['path']).as_posix();baseline=Path(json.loads((e/'ts-baseline-path.json').read_text())['path']).as_posix()
 def quoted(match):
  text=match.group(1);parts=[];depth=0;last=0
  for index,char in enumerate(text):
   if char in '<([{':depth+=1
   elif char in '>)]}':depth-=1
   elif char=='|' and depth==0:parts.append(text[last:index].strip());last=index+1
  parts.append(text[last:].strip());return "'"+' | '.join(sorted(parts))+"'"
 def records(path):
  data=path.read_bytes();text=data.decode('utf-16') if data.startswith(b'\xff\xfe') else data.decode('utf-8-sig');items=[]
  for chunk in re.split(r'(?=^.+?\(\d+,\d+\): error TS\d+:)',text,flags=re.M):
   found=re.match(r'(.+?)\(\d+,\d+\): error (TS\d+): ([\s\S]*)',chunk)
   if not found:continue
   message=found[3].strip().replace('\\','/').replace(candidate,'<FRONTEND>').replace(baseline,'<FRONTEND>');message=re.sub("'([^']*)'",quoted,message)
   items.append((found[1].replace('\\','/'),found[2],message))
  return collections.Counter(items)
 a=records(e/'ts-accepted-full.log');b=records(e/'ts-candidate-full.log');result={'accepted_base':'7c72d94cfd1e40ec3df3ef9617584cbbd8c1d3ea','head':'9d8c65790d6722cd222907d17dddb3f20748f758','accepted_diagnostics':sum(a.values()),'candidate_diagnostics':sum(b.values()),'normalization':'Ignore source line/column offsets; substitute only the two known frontend checkout roots; sort top-level unions inside quoted type expressions. Full messages compiled with --noErrorTruncation; no diagnostics removed.','added':[{'diagnostic':key,'count':value} for key,value in (b-a).items()],'removed':[{'diagnostic':key,'count':value} for key,value in (a-b).items()],'full_typecheck':'Both fail on inherited diagnostics; not a green full typecheck.'};(e/'ts-final-comparison.json').write_bytes(json.dumps(result,indent=2).encode());print(json.dumps(result)[:6000])

if __name__=='__main__':main()
