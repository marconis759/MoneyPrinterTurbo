"""Da eseguire UNA volta sul tuo computer per ottenere il refresh token di YouTube.

    python autopilot/youtube_auth.py CLIENT_ID CLIENT_SECRET

Si apre il browser, accedi con l'account del canale e autorizzi. Lo script stampa
YT_REFRESH_TOKEN da incollare nei secret del repository GitHub.
"""
import http.server
import json
import sys
import urllib.parse
import urllib.request
import webbrowser

PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    client_id, client_secret = sys.argv[1], sys.argv[2]
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "access_type": "offline", "prompt": "consent"})
    code = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            code.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Fatto! Puoi chiudere questa pagina.".encode())

        def log_message(self, *_):
            pass

    print("Se il browser non si apre, visita:\n" + url)
    webbrowser.open(url)
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).handle_request()
    if "code" not in code:
        sys.exit(f"Autorizzazione non riuscita: {code}")
    data = urllib.parse.urlencode({
        "code": code["code"][0], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data) as r:
        token = json.load(r)
    print("\nYT_REFRESH_TOKEN =", token["refresh_token"])


if __name__ == "__main__":
    main()
