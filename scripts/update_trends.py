import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

OUTPUT_PATH = Path("data/trends.json")
OUTPUT_PATH.parent.mkdir(exist_ok=True)

DATA = [
    {
        "destination": "Thaïlande",
        "continent": "Asie",
        "summary": "Bangkok, villes royales, plages et culture inspirante.",
        "highlights": [
            "Grand Palais et Wat Phra Kaew|Le grand ensemble royal de Bangkok.",
            "Ayutthaya|Vestiges de l’ancienne capitale du Siam.",
            "Sukhothai historique|Temples et sculptures de l’âge d’or siamois."
        ],
        "stays": [
            "The Sukhothai Bangkok|Bangkok|Jardins, piscine et sérénité urbaine.",
            "Amanpuri|Phuket|Pavillons thaïs, intimité et plage superbe.",
            "Four Seasons Resort Chiang Mai|Mae Rim|Rizières, jardins et architecture lanna."
        ],
        "practical": {
            "when": "Novembre à février",
            "duration": "10–14 jours",
            "fromParis": "Vol direct Paris–Bangkok selon programme."
        },
        "verdict": "Excellent équilibre entre culture, luxe discret et repos.",
        "theme": "Luxe durable",
        "audience": "Couples • premium",
        "best_for": "Bangkok, spas, villas, plages calmes",
        "budget": "€1 200–€2 500",
        "stay_length": "6–10 nuits",
        "hotel_style": "Boutique eco-luxury",
        "why_now": "Hausse des séjours premium avec une approche plus durable et plus intime.",
        "score": 92,
        "source": "travel-insights"
    },
    {
        "destination": "Japon",
        "continent": "Asie",
        "summary": "Esthétique, temples, gastronomie et voyages immersifs.",
        "highlights": [
            "Kyoto|Temples, jardins et culture raffinée.",
            "Nara|Grand Bouddha et sanctuaires anciens.",
            "Himeji|Château féodal remarquablement conservé."
        ],
        "stays": [
            "Aman Kyoto|Kyoto|Jardin secret et pavillons minimalistes.",
            "Hoshinoya Kyoto|Kyoto|Retraite au bord de la rivière.",
            "Gora Kadan|Hakone|Ryokan raffiné et bains thermaux."
        ],
        "practical": {
            "when": "Mars–mai ou octobre–novembre",
            "duration": "10–14 jours",
            "fromParis": "Paris–Tokyo ou Osaka ; train pour les grandes étapes."
        },
        "verdict": "Indispensable pour une escapade culturelle haut de gamme.",
        "theme": "Culture & design",
        "audience": "Couples • culture",
        "best_for": "Kyoto, Tokyo, ryokan, temples",
        "budget": "€1 400–€2 800",
        "stay_length": "7–12 nuits",
        "hotel_style": "Ryokan design / luxe discret",
        "why_now": "La demande reste forte pour des séjours immersifs et visuellement raffinés.",
        "score": 88,
        "source": "travel-insights"
    },
    {
        "destination": "Bali",
        "continent": "Asie",
        "summary": "Yoga, villas, rizières, spas et bien-être profond.",
        "highlights": [
            "Ubud|Culture balinaise et rizières.",
            "Bali Barat National Park|Forêts, récifs et paysages sauvages.",
            "Canggu|Surf et ambiance plus relaxed."
        ],
        "stays": [
            "Amandari|Ubud|Villas au-dessus des rizières.",
            "Capella Ubud|Bali|Campement raffiné en forêt.",
            "The Ungasan|Uluwatu|Villa premium et vues sur l’océan."
        ],
        "practical": {
            "when": "Mai–octobre",
            "duration": "6–11 jours",
            "fromParis": "Paris–Bali avec escale selon l’offre."
        },
        "verdict": "Très bon choix pour le slow travel et les séjours premium.",
        "theme": "Wellness & villas",
        "audience": "Couples • slow travel",
        "best_for": "Spa, yoga, villas, calme et vue jungle",
        "budget": "€1 100–€2 400",
        "stay_length": "6–11 nuits",
        "hotel_style": "Villa contemporaine / wellness retreat",
        "why_now": "La demande pour des séjours lentement conçus augmente sur le marché premium.",
        "score": 86,
        "source": "travel-insights"
    },
    {
        "destination": "Vietnam",
        "continent": "Asie",
        "summary": "Villes dynamiques, cuisine, nature et architecture singulière.",
        "highlights": [
            "Hanoï|Villes coloniales et vie quotidienne.",
            "Hoi An|Ancienne cité marchande et lanternes.",
            "Ha Long Bay|Paysages côtiers et faune marine."
        ],
        "stays": [
            "The Nam Hai|Hội An|Villas au bord de la plage et jardins luxuriants.",
            "Amanoi|Nha Trang|Vue sur la baie et bien-être limpide.",
            "The Pavilions|Ha Long|Architecture contemporaine et luxe discret."
        ],
        "practical": {
            "when": "Octobre–avril",
            "duration": "8–12 jours",
            "fromParis": "Paris–Hanoï ou Ho Chi Minh City avec escale."
        },
        "verdict": "Très bien pour un voyage alliant culture, cuisine et nature.",
        "theme": "Culture & nature",
        "audience": "Couples • découvrir",
        "best_for": "Cuisine, plages, voyage doux, nature",
        "budget": "€1 000–€2 200",
        "stay_length": "5–9 nuits",
        "hotel_style": "Boutique luxury / resort chic",
        "why_now": "La demande pour le Vietnam premium reste très forte à cause de son excellent rapport qualité / prix.",
        "score": 82,
        "source": "travel-insights"
    },
    {
        "destination": "Sri Lanka",
        "continent": "Asie",
        "summary": "Culture, nature tropicale et maisons de charme.",
        "highlights": [
            "Kandy|Temple de la dent et culture singhalaise.",
            "Sigiriya|Citadelle au cœur de la jungle.",
            "Ella|Vallées et train pittoresque."
        ],
        "stays": [
            "Cape Weligama|Weligama|Villa de luxe au bord de l’océan.",
            "Anantara Peace Haven|Tangalle|Hôtel paradisiaque et naturel.",
            "The Wallawwa|Colombo|Maison de maître entourée de jardins."
        ],
        "practical": {
            "when": "Novembre–avril",
            "duration": "8–12 jours",
            "fromParis": "Vol direct Paris–Colombo selon la période."
        },
        "verdict": "Très bon choix pour un voyage favorisant le bien-être et la nature.",
        "theme": "Nature & bien-être",
        "audience": "Couples • nature",
        "best_for": "Plage, train, nature, beauté brute",
        "budget": "€1 000–€2 300",
        "stay_length": "6–10 nuits",
        "hotel_style": "Villa / resort naturel",
        "why_now": "Le Sri Lanka reste sous-tendu par un très bon rapport qualité / prix et un charme authentique.",
        "score": 78,
        "source": "travel-insights"
    },
    {
        "destination": "Inde",
        "continent": "Asie",
        "summary": "Couleurs, palais et spiritualité en immersion.",
        "highlights": [
            "Jaipur|Palais, forts et marchés.",
            "Agra|Taj Mahal et architecture moghole.",
            "Udaipur|Lacs, palais et atmosphère romantique."
        ],
        "stays": [
            "The Leela Palace|New Delhi|Luxe contemporain et service exceptionnel.",
            "Taj Falaknuma Palace|Hyderabad|Palais historique et extravagance.",
            "Rambagh Palace|Jaipur|Patrimoine royal et grand luxe."
        ],
        "practical": {
            "when": "Octobre–mars",
            "duration": "10–15 jours",
            "fromParis": "Vol direct Paris–Delhi ou Mumbai."
        },
        "verdict": "Excellente destination si l’on recherche un voyage très visuel et émotionnel.",
        "theme": "Culture & luxe royal",
        "audience": "Couples • patrimoine",
        "best_for": "Palaces, forts, gastronomie, temples",
        "budget": "€1 200–€2 900",
        "stay_length": "7–12 nuits",
        "hotel_style": "Palace / heritage hotel",
        "why_now": "Le luxe historique indien attire beaucoup de voyageurs en quête de symboles forts.",
        "score": 85,
        "source": "travel-insights"
    },
    {
        "destination": "Maroc",
        "continent": "Afrique",
        "summary": "Médinas, jardins et artisanat.",
        "highlights": [
            "Médina de Fès|Architecture et artisanat séculaires.",
            "Médina de Marrakech|Palais, souks et monuments.",
            "Aït-Ben-Haddou|Ksar traditionnel en terre."
        ],
        "stays": [
            "Royal Mansour Marrakech|Marrakech|Riads privés et jardins remarquables.",
            "Amanjena|Marrakech|Pavillons autour des bassins.",
            "Kasbah Tamadot|Atlas|Maison de montagne avec personnalité."
        ],
        "practical": {
            "when": "Mars–mai ou octobre–novembre",
            "duration": "4–8 jours",
            "fromParis": "Vol direct Paris–Marrakech ou Fès."
        },
        "verdict": "Marrakech fonctionne très bien si l’hôtel est un refuge paisible.",
        "theme": "Culture & riads",
        "audience": "Couples • week-end luxe",
        "best_for": "Marrakech, Essaouira, riads, cuisine",
        "budget": "€900–€2 000",
        "stay_length": "4–8 nuits",
        "hotel_style": "Riad chic / wellness",
        "why_now": "L’offre luxe inspirée du patrimoine est très recherchée pour les voyages courts.",
        "score": 84,
        "source": "travel-insights"
    },
    {
        "destination": "Égypte",
        "continent": "Afrique",
        "summary": "Histoire millénaire, déserts et croisières sur le Nil.",
        "highlights": [
            "Le Caire|Musées et architecture historique.",
            "Louxor|Temples et vallée des rois.",
            "Abou Simbel|Monuments majestueux face au désert."
        ],
        "stays": [
            "Sofitel Legend Old Cataract|Assouan|Grand hôtel historique sur le Nil.",
            "The First Residence|Le Caire|Luxe discret et service raffiné.",
            "Mena House|Le Caire|Vue sur les Pyramides."
        ],
        "practical": {
            "when": "Octobre–avril",
            "duration": "6–10 jours",
            "fromParis": "Vol direct Paris–Le Caire selon la saison."
        },
        "verdict": "Très bon choix pour les voyageurs amoureux de l’histoire.",
        "theme": "Patrimoine & desert luxe",
        "audience": "Couples • histoire",
        "best_for": "Nil, temples, pyramides, désert",
        "budget": "€1 100–€2 400",
        "stay_length": "5–9 nuits",
        "hotel_style": "Grand hôtel historique / palais",
        "why_now": "L’Égypte montre un fort regain de demande pour les grands voyages culturels premium.",
        "score": 76,
        "source": "travel-insights"
    },
    {
        "destination": "Afrique du Sud",
        "continent": "Afrique",
        "summary": "Safari, coastlines et espaces grandioses.",
        "highlights": [
            "Kruger|Safari et animaux emblématiques.",
            "Cape Town|Villes, montagnes et mer.",
            "Garden Route|Routes côtières et nature généreuse."
        ],
        "stays": [
            "Singita Boulders Lodge|Kruger|Safari luxe et vue sur les falaises.",
            "The Silo Hotel|Le Cap|Design et vue sur le port.",
            "Bushmans Kloof|Cederberg|Retraite luxe dans le désert."
        ],
        "practical": {
            "when": "Mai–octobre",
            "duration": "8–12 jours",
            "fromParis": "Vol direct Paris–Johannesburg ou Le Cap."
        },
        "verdict": "Excellente destination pour un voyage très visuel et très riche.",
        "theme": "Safari & coast",
        "audience": "Couples • nature",
        "best_for": "Safari, villes, montagnes, plage",
        "budget": "€1 500–€3 200",
        "stay_length": "7–11 nuits",
        "hotel_style": "Lodge safari / design hôtel",
        "why_now": "L’Afrique du Sud reste crème de la crème du safari premium.",
        "score": 80,
        "source": "travel-insights"
    },
    {
        "destination": "Portugal",
        "continent": "Europe",
        "summary": "Villes historiques, palais et vignobles.",
        "highlights": [
            "Sintra|Palais romantiques et jardins.",
            "Monastère des Hiéronymites|Chef-d’œuvre manuelin à Lisbonne.",
            "Porto historique|Ruelles et patrimoine du Douro."
        ],
        "stays": [
            "Six Senses Douro Valley|Douro|Domaine, piscine et sérénité.",
            "Sublime Comporta|Comporta|Cabanes, pinède et élégance naturelle.",
            "Verride Palácio Santa Catarina|Lisbonne|Petit palais et atmosphère résidentielle."
        ],
        "practical": {
            "when": "Mai–juin ou septembre",
            "duration": "5–10 jours",
            "fromParis": "Vol direct Paris–Lisbonne ou Porto."
        },
        "verdict": "Destination parfaitement alignée avec vos préférences.",
        "theme": "Design & bien-être",
        "audience": "Sans enfants • lifestyle",
        "best_for": "Porto, Sintra, hôtels design, vin et nature",
        "budget": "€1 000–€2 200",
        "stay_length": "5–9 nuits",
        "hotel_style": "Petit hôtel design / maison d’hôtes",
        "why_now": "Les voyageurs recherchent des séjours élégants, aérés et faciles à vivre.",
        "score": 81,
        "source": "travel-insights"
    },
    {
        "destination": "Islande",
        "continent": "Europe",
        "summary": "Nature, spas, paysages extrêmes et luxe discret.",
        "highlights": [
            "Reykjavik|Capital moderne et culture nordique.",
            "Golden Circle|Geysers, cascade et paysages volcaniques.",
            "South Coast|Fjords, glaciers et plages noires."
        ],
        "stays": [
            "Hótel Borg|Reykjavik|Luxe discret, design scandinave.",
            "The Retreat at Blue Lagoon|Blue Lagoon|Spa haut de gamme.",
            "Hotel Rangá|South Coast|Accueil chaleureux et excellent point de départ."
        ],
        "practical": {
            "when": "Juin–septembre",
            "duration": "7–10 jours",
            "fromParis": "Vol direct Paris–Reykjavik selon la période."
        },
        "verdict": "Très forte demande pour les paysages et les séjours premium nature.",
        "theme": "Nature premium",
        "audience": "Amis • nature",
        "best_for": "Road trip, volcan, spa, paysages extrêmes",
        "budget": "€1 600–€3 200",
        "stay_length": "7–10 nuits",
        "hotel_style": "Lodge haut de gamme / campements haut standing",
        "why_now": "Les escapades nature premium restent très prisées pour les voyageurs exigeants.",
        "score": 79,
        "source": "travel-insights"
    },
    {
        "destination": "Italie",
        "continent": "Europe",
        "summary": "Art, histoire, gastronomie et villages enchanteurs.",
        "highlights": [
            "Rome antique|Forum, Palatin et Colisée.",
            "Florence|Renaissance, Duomo et Offices.",](#)

