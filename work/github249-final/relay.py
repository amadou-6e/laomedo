"""Start a loopback-only real-service relay; never generate provider responses."""
import argparse
from pathlib import Path
from http.server import ThreadingHTTPServer
from relay_handler import RelayHandler


def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--upstream',type=int,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--drop-flag',type=Path);args=p.parse_args();server=ThreadingHTTPServer(('127.0.0.1',args.port),RelayHandler);server.upstream_port=args.upstream;server.audit=args.audit;server.drop_flag=args.drop_flag;server.serve_forever()

if __name__=='__main__':main()
