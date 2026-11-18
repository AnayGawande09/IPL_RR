"""Serve the dashboard on localhost (pure Python standard library).
usage: python -I serve_dashboard.py [port]      then open http://localhost:<port>/  (default 8000)"""
import sys, os, functools, http.server

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'report', 'site')
if not os.path.exists(os.path.join(SITE, 'index.html')):
    sys.exit('report/site/index.html not found - run build_dashboard.py first')
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITE)
with http.server.ThreadingHTTPServer(('127.0.0.1', PORT), handler) as srv:
    print(f'Dashboard running at http://localhost:{PORT}/  (Ctrl+C to stop)', flush=True)
    srv.serve_forever()
