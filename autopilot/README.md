# Autopilot: 10 clip al giorno, gratis e in automatico

Ogni mattina GitHub Actions (gratis per i repository pubblici):

1. **05:15** – legge i trend del giorno (Google Trends + Google News Italia),
   fa scegliere a un'AI gratuita (GitHub Models) i 10 argomenti più adatti e
   scrive testi, titoli, didascalie e hashtag;
2. crea le 10 clip verticali (voce Edge TTS, sottotitoli dinamici, musica);
3. le mette in una **Release** chiamata `clips-AAAA-MM-GG` (le trovi nella
   pagina *Releases* del repository, pronte da scaricare);
4. dalle **07:30 alle 22:30** pubblica una clip per volta negli orari migliori:
   07:30 · 09:00 · 11:00 · 12:30 · 14:00 · 16:00 · 18:00 · 19:30 · 21:00 · 22:30.

Tutto funziona senza carte di credito. Ogni canale si accende aggiungendo i suoi
*secret* in **Settings → Secrets and variables → Actions → New repository secret**.

## Consigliato subito (5 minuti, gratis)

| Secret | A cosa serve | Come ottenerlo |
|---|---|---|
| `PEXELS_API_KEY` | Sfondi video veri invece dei gradienti | Registrati su pexels.com/api → copia la chiave |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Ti arriva ogni clip sul telefono, all'orario giusto, con didascalia pronta da incollare su TikTok | Su Telegram scrivi a **@BotFather** → `/newbot` → copia il token. Poi scrivi un messaggio al tuo bot e apri `https://api.telegram.org/bot<TOKEN>/getUpdates`: il numero in `"chat":{"id":…}` è il CHAT_ID |

## Pubblicazione automatica sui social (gratis)

### Instagram Reels – pubblica in automatico, pubblico
Serve un account Instagram **Professional** (Creator o Business, gratis da app).
1. developers.facebook.com → *Crea app* → tipo *Business* → aggiungi il prodotto **Instagram** → *API setup with Instagram login*.
2. Aggiungi il tuo account Instagram come tester e genera il token.
3. Secret: `IG_USER_ID` e `IG_ACCESS_TOKEN`.
Il token dura 60 giorni e il sistema lo rinnova a ogni pubblicazione.

### YouTube Shorts
1. console.cloud.google.com → nuovo progetto → abilita **YouTube Data API v3**.
2. *Schermata consenso OAuth* (esterna, aggiungi te stesso come utente di test) → *Credenziali* → *ID client OAuth* tipo **App desktop**.
3. Sul tuo computer: `python autopilot/youtube_auth.py CLIENT_ID CLIENT_SECRET` → copia il refresh token.
4. Secret: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

⚠️ Regola di Google: finché il progetto non supera la verifica gratuita
("audit" dell'API, qualche settimana), i video caricati via API restano **privati**.
Nel frattempo li trovi in YouTube Studio e li rendi pubblici con un tocco.

### TikTok
L'API ufficiale di TikTok pubblica solo in privato finché l'app non viene approvata.
Opzioni gratuite:
- **Telegram** (sopra): ricevi la clip all'orario giusto e la pubblichi in 20 secondi;
- **Upload-Post** (piano gratis: 10 upload al mese): secret `UPLOAD_POST_API_KEY`
  e `UPLOAD_POST_USER` (nome profilo creato su upload-post.com).

## Comandi utili

- **Rigenerare oggi**: *Actions → Autopilot - genera le clip del giorno → Run workflow*.
- **Pubblicare subito la prossima**: *Actions → Autopilot - pubblica le clip → Run workflow* con "Pubblica subito".
- **Scrivere tu i piani di un giorno**: crea `autopilot/plans/AAAA-MM-GG/*.json`
  (vedi gli esempi in `plans/2026-10-16/`): quel giorno verranno usati al posto dell'AI.
- **Prova in locale**: `python autopilot/render.py piano.json out.mp4`.

## Regole editoriali dell'AI
L'AI usa solo fatti presenti nei titoli del giorno, evita tragedie di persone
comuni, nomi di indagati o minori, consigli medici e finanziari, politica di
parte e sfide pericolose. Le regole sono in `writer.py` (`RULES`).
Controlla comunque le clip nella Release del giorno: puoi cancellarne una
prima dell'orario e verrà saltata.
