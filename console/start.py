"""Start the loopback console from any working directory."""
import argparse
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.chdir(root)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='Check dependencies and built assets without starting the server')
parser.add_argument('--port', type=int, default=8766, help='Loopback HTTP port (default: 8766)')
args=parser.parse_args()
if not 1 <= args.port <= 65535:
    parser.error('--port must be between 1 and 65535')
if not (root/'console/frontend/dist/index.html').is_file():
    raise SystemExit('Build first: npm ci --prefix console/frontend && npm run build --prefix console/frontend')
from console.backend.app import main
if args.check:
    print('Console installation check passed')
else:
    print(f'WHEELTEC console: http://127.0.0.1:{args.port} (Ctrl+C to stop)')
    main(port=args.port)
