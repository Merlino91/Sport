# EasySports · Stremio Live Sports Addon

Addon Stremio per lo streaming e il monitoraggio degli eventi sportivi in diretta, organizzati per disciplina, con integrazione automatica per **EasyProxy**.

---

## 🌟 Caratteristiche Principali

- ⚽ **Copertura completa degli Sport**: Calcio, Basket, Formula 1 / MotoGP, Tennis, UFC / Boxing, Hockey, Baseball, Football Americano, Rugby, Golf, Cricket e altri.
- 🚀 **Bypass DNS Integrato (DoH)**: Risolve nativamente le API tramite DNS-over-HTTPS (Cloudflare/Google) per garantire il funzionamento anche in presenza di blocchi ISP/AGCOM italiani.
- ⚡ **Integrazione Nativa EasyProxy**: Inoltra i flussi HLS/M3U8 protetti e con restrizioni CORS direttamente al tuo server [EasyProxy](https://github.com/realbestia1/EasyProxy).
- 🕒 **Fuso Orario Personalizzabile**: Mostra gli orari delle partite convertiti nel tuo fuso orario locale.
- 🖥️ **Pannello di Configurazione Web**: Interfaccia web elegante per generare il link di installazione in 1-click su Stremio Desktop / Mobile o Stremio Web.
- 🐳 **Docker Ready**: Pronto per essere distribuito su qualsiasi VPS o server casalingo con Docker Compose.

---

## 📦 Installazione ed Esecuzione

### Metodo 1: Python Diretto

1. **Clona o scarica la cartella del progetto**:
   ```bash
   cd EasySports
   ```

2. **Installa le dipendenze**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Avvia il server**:
   ```bash
   python run.py
   ```

Il server sarà attivo su `http://localhost:7000`.

---

### Metodo 2: Docker / Docker Compose

1. **Avvia con Docker Compose**:
   ```bash
   docker-compose up -d --build
   ```

---

## ⚙️ Configurazione e Aggiunta a Stremio

1. Apri nel browser `http://localhost:7000/configure` (o l'IP pubblico del tuo server).
2. Inserisci:
   - **Proxy URL**: l'URL del tuo EasyProxy (es. `https://ep.tuodominio.com`).
   - **Password**: la password API di EasyProxy (se impostata).
   - **Fuso Orario**: seleziona il tuo fuso (es. `Europe/Rome`).
3. Clicca su **"Genera link di installazione"**.
4. Clicca su **"Apri nell'app Stremio"** oppure copia il link manifest generato e incollalo nella barra di ricerca degli Addon di Stremio.

---

## 🛠️ Struttura del Progetto

```
EasySports/
├── app/
│   ├── config.py              # Configurazioni e parametri globali
│   ├── main.py                # Server FastAPI & rotte protocollo Stremio Addon
│   ├── services/
│   │   ├── doh_client.py      # Client HTTP asincrono con DNS-over-HTTPS
│   │   ├── streamed_api.py    # Client API eventi sportivi con cache in memoria
│   │   ├── catalog_service.py # Generatore cataloghi e metadati Stremio
│   │   └── stream_service.py  # Risolutore ed estrattore stream per EasyProxy
│   ├── templates/             # Template HTML interfaccia web
│   └── static/                # Asset statici (CSS, JS, icone)
├── tests/                     # Suite di test unitari e di integrazione
├── run.py                     # Script di avvio
├── Dockerfile                 # Configurazione container Docker
└── docker-compose.yml         # Configurazione Docker Compose
```

---

## 🧪 Esecuzione dei Test

Per eseguire la suite di test automatizzata:

```bash
pytest tests/ -v
```
