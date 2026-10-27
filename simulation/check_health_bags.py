"""Offline audit of every retained case, preserving failures and missing evidence."""
import argparse
import json
from pathlib import Path
from replay_health import replay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix',type=Path,default=Path(__file__).resolve().parents[1]/'setup/verification/unknown_rooms/matrix.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    matrix=json.loads(args.matrix.read_text(encoding='utf-8-sig'))
    results=[]
    for case in matrix['cases']:
        try:
            result=replay(Path(case['result']).parent/'bag')
        except Exception as error:
            result={'error':repr(error),'bag':str(Path(case['result']).parent/'bag')}
        result['case']=case['case']
        results.append(result)
        (args.output/(case['case']+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        print(case['case'],result.get('first_issue_sim_s',result.get('error')),flush=True)
    summary={'cases':len(results),'reports':results,'truth_read':False,
             'process_liveness_verified':False}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__': main()
