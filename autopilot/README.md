# Autopilot: 10 clip al giorno, gratis e in automatico

Ogni mattina GitHub Actions (gratis per i repository pubblici):

1. **05:15** – sceglie 10 oggetti di tutti i giorni mai trattati prima, legge
   come vengono prodotti su Wikipedia e fa scrivere a un'AI gratuita (Google
   Gemini) clip **"Come è fatto"**: dalla materia prima al prodotto finito;
2. crea le 10 clip verticali: voce narrante Gemini (umana) con riserva Edge,
   sottotitoli parola per parola, video di fabbrica da Pixabay, musica;
3. le mette in una **Release** chiamata `clips-AAAA-MM-GG` (le trovi nella
   pagina *Releases* del repository, pronte da scaricare);
4. dalle **07:30 alle 22:30** pubblica una clip per volta negli orari migliori:
   07:30 · 09:00 · 11:00 · 12:30 · 14:00 · 16:00 · 18:00 · 19:30 · 21:00 · 22:30.

Tutto funziona senza carte di credito. Ogni canale si accende aggiungendo i suoi
*secret* in **Settings → Secrets and variables → Actions → New repository secret**.

## Consigliato subito (5 minuti, gratis)

| Secret | A cosa serve | Come ottenerlo |
|---|---|---|
| `GEMINI_API_KEY` | Testi AI e **voce narrante umana**. Senza, escono clip più semplici lette dai riassunti di Wikipedia con voce Edge | aistudio.google.com/apikey → *Create API key* (piano gratuito, nessuna carta). Il nome del secret deve essere esattamente `GEMINI_API_KEY`, tra i *Repository secrets* |
| `PIXABAY_API_KEY` | Sfondi video veri invece dei gradienti | Registrati su pixabay.com (gratis) → apri pixabay.com/api/docs/ da loggato → la chiave è nel paragrafo *Parameters*, voce `key` |
| `PEXELS_API_KEY` (alternativa) | Come sopra, se Pexels riapre le nuove chiavi | pexels.com/api |
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
  (vedi gli esempi in `plans/esempi/`): quel giorno verranno usati al posto dell'AI.
- **Prova in locale**: `python autopilot/render.py piano.json out.mp4`.

## Regole editoriali dell'AI
Formato unico "Come è fatto": come si fabbrica un oggetto, passo per passo.
L'AI usa solo i fatti degli estratti di Wikipedia o conoscenze tecniche certe,
non inventa numeri né nomi di aziende e non cita programmi TV o marchi di terzi.
La lista degli oggetti è in `writer.py` (`OBJECTS`): aggiungine quanti vuoi. Le regole sono in `writer.py` (`RULES`).
Controlla comunque le clip nella Release del giorno: puoi cancellarne una
prima dell'orario e verrà saltata.
