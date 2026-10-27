"""Generate provenance-preserving realism YAML from a calibration JSON."""
import argparse
from pathlib import Path
from realism import generate_profile

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--replace-generated',action='store_true')
    args=parser.parse_args()
    if args.output.exists() and not args.replace_generated:
        parser.error('Output exists; use --replace-generated only for generated YAML')
    profile=generate_profile(args.input,args.output)
    print('Generated',args.output,'calibration_complete=',profile.get('calibration_complete',False))
