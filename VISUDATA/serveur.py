"""
Serveur HTTP local pour VISUDATA.

Deux raisons de ne pas utiliser directement `python -m http.server` :
  * il n'envoie aucun en-tete de cache : apres une modification des fichiers,
    le navigateur continue de servir l'ancienne version depuis son cache ;
  * il ignore le type MIME du WebAssembly, ce qui prive le noyau CAO de
    l'instanciation par flux (chargement plus lent).

Usage :  python serveur.py [port]
"""

import http.server
import mimetypes
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

mimetypes.add_type('application/wasm', '.wasm')
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        super().end_headers()

    def send_head(self):
        # neutralise les reponses 304 : le client ne doit jamais reutiliser de copie
        for h in ('If-Modified-Since', 'If-None-Match'):
            if h in self.headers:
                del self.headers[h]
        return super().send_head()

    def log_message(self, fmt, *args):
        sys.stderr.write('  %s\n' % (fmt % args))


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    try:
        with Server(('127.0.0.1', PORT), Handler) as httpd:
            print(f'  Serveur pret sur http://localhost:{PORT}/  (cache desactive)\n')
            httpd.serve_forever()
    except OSError as e:
        print(f'\n  [ERREUR] Impossible d\'ouvrir le port {PORT} : {e}')
        print(f'  Un autre VISUDATA tourne peut-etre deja. Essayez : python serveur.py 8766\n')
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n  Serveur arrete.')
