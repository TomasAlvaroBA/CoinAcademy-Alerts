# Youtube-Weekly-Crypto-Market

Bot Railway : chaque nouvelle vidéo de la chaîne CoinAcademy devient un « Rapport Alpha »
(convictions de Picsou, narratifs, niveaux chartistes) envoyé dans un groupe Telegram.

- Vérification chaque jour à 20h (heure de Paris), plus un test sur la dernière vidéo à chaque démarrage.
- Lecture : Gemini regarde directement la vidéo (graphiques compris), sinon les sous-titres YouTube.
- Variables Railway : `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
  (et `YOUTUBE_CHANNEL_ID` pour suivre une autre chaîne).
