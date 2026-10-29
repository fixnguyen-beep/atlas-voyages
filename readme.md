Atlas v2
Structure
`data/catalog.json`: préférences éditoriales et contenu de secours.
`scripts/update_trends.py`: recherche web OpenAI, extraction et validation.
`data/trends.json`: données publiées consommées par les pages HTML.
`atlas.html`: fiches pays, hôtels sourcés et conseils actuels.
`index.html`: ouvertures hôtelières sourcées.
`.github/workflows/update-travel-trends.yml`: exécution chaque lundi et manuelle.
Installation GitHub
Copier les fichiers en respectant les dossiers.
Créer le secret de dépôt `OPENAI_API_KEY`.
Lancer manuellement le workflow `Update travel intelligence` une première fois.
Activer GitHub Pages sur la branche `main`.
Principe
Le catalogue exprime les goûts et fournit un fallback. Le script ajoute des hôtels, conseils et ouvertures issus d'une recherche web. Les éléments dynamiques ne sont gardés que s'ils possèdent des URL HTTPS. Les prix et disponibilités ne sont pas vérifiés.
