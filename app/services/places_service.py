"""Real Places API & Pan-India Destination Service.
Provides live location lookup via OpenStreetMap (Overpass / Nominatim APIs),
comprehensive offline fallbacks for all Indian destinations, and categorized
attraction/dining endpoints.
"""

from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, HTTPException, Query

from app.data.india_destinations import (
    INDIAN_DESTINATIONS,
    filter_indian_destinations,
    get_indian_destination,
)


# ============================================================================
# Offline Fallback Places Catalog (Guaranteed 0-crash during demos/viva)
# ============================================================================

OFFLINE_PLACES_DATA: Dict[str, List[Dict[str, Any]]] = {
    "manali_spiti_india": [
        {
            "place_id": "manali_hadimba",
            "name": "Hadimba Devi Ancient Pine Temple",
            "category": "culture",
            "lat": 32.2483,
            "lon": 77.1800,
            "opening_hours": "08:00 - 18:00",
            "typical_duration_hours": 1.5,
            "rating": 4.6,
        },
        {
            "place_id": "manali_solang",
            "name": "Solang Valley Adventure Grounds",
            "category": "adventure",
            "lat": 32.3160,
            "lon": 77.1575,
            "opening_hours": "09:00 - 17:30",
            "typical_duration_hours": 3.5,
            "rating": 4.7,
        },
        {
            "place_id": "manali_rohtang",
            "name": "Rohtang Pass Snow Viewpoint",
            "category": "nature",
            "lat": 32.3716,
            "lon": 77.2466,
            "opening_hours": "07:00 - 16:00",
            "typical_duration_hours": 4.0,
            "rating": 4.8,
        },
        {
            "place_id": "manali_cafe1947",
            "name": "Cafe 1947 Riverside Old Manali",
            "category": "food",
            "lat": 32.2570,
            "lon": 77.1780,
            "opening_hours": "11:00 - 23:00",
            "typical_duration_hours": 1.5,
            "rating": 4.5,
        },
        {
            "place_id": "spiti_key_monastery",
            "name": "Key Gompa Buddhist Monastery",
            "category": "culture",
            "lat": 32.2982,
            "lon": 78.0125,
            "opening_hours": "07:00 - 19:00",
            "typical_duration_hours": 2.0,
            "rating": 4.9,
        },
        {
            "place_id": "spiti_chandratal",
            "name": "Chandratal Crescent Moon Lake",
            "category": "nature",
            "lat": 32.4824,
            "lon": 77.6186,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 3.0,
            "rating": 4.9,
        },
        {
            "place_id": "manali_jogini",
            "name": "Jogini Waterfall Forest Trail",
            "category": "rest",
            "lat": 32.2685,
            "lon": 77.1950,
            "opening_hours": "08:00 - 17:00",
            "typical_duration_hours": 2.5,
            "rating": 4.6,
        },
    ],
    "rishikesh_haridwar_india": [
        {
            "place_id": "rishi_parmarth",
            "name": "Parmarth Niketan Ganga Aarti Ghat",
            "category": "culture",
            "lat": 30.1170,
            "lon": 78.3120,
            "opening_hours": "06:00 - 20:00",
            "typical_duration_hours": 2.0,
            "rating": 4.8,
        },
        {
            "place_id": "rishi_rafting",
            "name": "Shivpuri White Water River Rafting",
            "category": "adventure",
            "lat": 30.1380,
            "lon": 78.3890,
            "opening_hours": "08:00 - 16:00",
            "typical_duration_hours": 3.0,
            "rating": 4.7,
        },
        {
            "place_id": "rishi_beatles",
            "name": "The Beatles Chaurasi Kutia Ashram",
            "category": "culture",
            "lat": 30.1110,
            "lon": 78.3140,
            "opening_hours": "09:00 - 16:00",
            "typical_duration_hours": 2.0,
            "rating": 4.5,
        },
        {
            "place_id": "rishi_harkipauri",
            "name": "Har Ki Pauri Brahma Kund Haridwar",
            "category": "culture",
            "lat": 29.9570,
            "lon": 78.1730,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 2.5,
            "rating": 4.9,
        },
        {
            "place_id": "rishi_chotiwala",
            "name": "Chotiwala Traditional Garhwali Thali",
            "category": "food",
            "lat": 30.1220,
            "lon": 78.3150,
            "opening_hours": "08:00 - 22:30",
            "typical_duration_hours": 1.0,
            "rating": 4.3,
        },
        {
            "place_id": "rishi_neergarh",
            "name": "Neer Garh Crystal Waterfall",
            "category": "nature",
            "lat": 30.1440,
            "lon": 78.3340,
            "opening_hours": "08:00 - 17:30",
            "typical_duration_hours": 2.0,
            "rating": 4.6,
        },
        {
            "place_id": "rishi_kunjapuri",
            "name": "Kunjapuri Temple Himalayan Sunrise Viewpoint",
            "category": "rest",
            "lat": 30.1800,
            "lon": 78.3050,
            "opening_hours": "05:00 - 18:00",
            "typical_duration_hours": 2.5,
            "rating": 4.8,
        },
    ],
    "leh_ladakh_india": [
        {
            "place_id": "leh_pangong",
            "name": "Pangong Tso High Altitude Salt Lake",
            "category": "nature",
            "lat": 33.7595,
            "lon": 78.6674,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 4.0,
            "rating": 4.9,
        },
        {
            "place_id": "leh_thiksey",
            "name": "Thiksey Monastery Maitreya Buddha",
            "category": "culture",
            "lat": 34.0560,
            "lon": 77.6667,
            "opening_hours": "07:00 - 19:00",
            "typical_duration_hours": 2.0,
            "rating": 4.8,
        },
        {
            "place_id": "leh_nubra",
            "name": "Nubra Valley & Hunder Bactrian Dunes",
            "category": "adventure",
            "lat": 34.5760,
            "lon": 77.4720,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 4.0,
            "rating": 4.8,
        },
        {
            "place_id": "leh_shanti_stupa",
            "name": "Shanti Stupa Sunset Panorama",
            "category": "rest",
            "lat": 34.1710,
            "lon": 77.5810,
            "opening_hours": "05:00 - 21:00",
            "typical_duration_hours": 1.5,
            "rating": 4.7,
        },
        {
            "place_id": "leh_gesmo",
            "name": "Gesmo Yak Cheese Cafe & German Bakery",
            "category": "food",
            "lat": 34.1640,
            "lon": 77.5840,
            "opening_hours": "07:30 - 22:00",
            "typical_duration_hours": 1.0,
            "rating": 4.4,
        },
        {
            "place_id": "leh_khardungla",
            "name": "Khardung La World's Highest Motorable Pass",
            "category": "adventure",
            "lat": 34.2787,
            "lon": 77.6047,
            "opening_hours": "08:00 - 17:00",
            "typical_duration_hours": 1.5,
            "rating": 4.7,
        },
    ],
    "varanasi_india": [
        {
            "place_id": "vns_dashashwamedh",
            "name": "Dashashwamedh Ghat Grand Evening Aarti",
            "category": "culture",
            "lat": 25.3060,
            "lon": 83.0100,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 2.5,
            "rating": 4.9,
        },
        {
            "place_id": "vns_vishwanath",
            "name": "Kashi Vishwanath Golden Temple",
            "category": "culture",
            "lat": 25.3109,
            "lon": 83.0107,
            "opening_hours": "03:00 - 23:00",
            "typical_duration_hours": 2.0,
            "rating": 4.9,
        },
        {
            "place_id": "vns_assi",
            "name": "Assi Ghat Subah-e-Banaras Dawn Boat Ride",
            "category": "rest",
            "lat": 25.2890,
            "lon": 83.0060,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 2.0,
            "rating": 4.7,
        },
        {
            "place_id": "vns_sarnath",
            "name": "Sarnath Dhamek Stupa & Deer Park",
            "category": "nature",
            "lat": 25.3810,
            "lon": 83.0230,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 3.0,
            "rating": 4.7,
        },
        {
            "place_id": "vns_bluelassi",
            "name": "Blue Lassi Artisan Heritage Shop",
            "category": "food",
            "lat": 25.3120,
            "lon": 83.0130,
            "opening_hours": "09:00 - 22:00",
            "typical_duration_hours": 0.5,
            "rating": 4.6,
        },
        {
            "place_id": "vns_chaat",
            "name": "Kashi Chaat Tamatar & Palak Chaat",
            "category": "food",
            "lat": 25.3080,
            "lon": 83.0030,
            "opening_hours": "16:00 - 22:30",
            "typical_duration_hours": 1.0,
            "rating": 4.5,
        },
    ],
    "udaipur_mewar_india": [
        {
            "place_id": "udr_city_palace",
            "name": "Udaipur Royal City Palace Complex",
            "category": "culture",
            "lat": 24.5764,
            "lon": 73.6835,
            "opening_hours": "09:00 - 17:30",
            "typical_duration_hours": 3.0,
            "rating": 4.8,
        },
        {
            "place_id": "udr_pichola",
            "name": "Lake Pichola & Jag Mandir Sunset Cruise",
            "category": "nature",
            "lat": 24.5770,
            "lon": 73.6790,
            "opening_hours": "09:00 - 18:30",
            "typical_duration_hours": 1.5,
            "rating": 4.8,
        },
        {
            "place_id": "udr_bagore",
            "name": "Bagore Ki Haveli Dharohar Dance",
            "category": "culture",
            "lat": 24.5790,
            "lon": 73.6820,
            "opening_hours": "09:30 - 20:00",
            "typical_duration_hours": 2.0,
            "rating": 4.6,
        },
        {
            "place_id": "udr_ambrai",
            "name": "Ambrai Lakeside Fine Dining",
            "category": "food",
            "lat": 24.5780,
            "lon": 73.6800,
            "opening_hours": "12:00 - 23:00",
            "typical_duration_hours": 2.0,
            "rating": 4.7,
        },
        {
            "place_id": "udr_saheliyon",
            "name": "Saheliyon Ki Bari Fountains & Gardens",
            "category": "rest",
            "lat": 24.6050,
            "lon": 73.6870,
            "opening_hours": "09:00 - 19:00",
            "typical_duration_hours": 1.5,
            "rating": 4.4,
        },
        {
            "place_id": "udr_sajjangarh",
            "name": "Sajjangarh Monsoon Palace Mountain Ridge",
            "category": "adventure",
            "lat": 24.5930,
            "lon": 73.6360,
            "opening_hours": "09:00 - 18:00",
            "typical_duration_hours": 2.0,
            "rating": 4.5,
        },
    ],
    "jaipur_jodhpur_india": [
        {
            "place_id": "jpr_amber_fort",
            "name": "Amber Fort & Sheesh Mahal",
            "category": "culture",
            "lat": 26.9855,
            "lon": 75.8513,
            "opening_hours": "08:00 - 17:30",
            "typical_duration_hours": 3.0,
            "rating": 4.8,
        },
        {
            "place_id": "jpr_hawa_mahal",
            "name": "Hawa Mahal Palace of the Winds",
            "category": "culture",
            "lat": 26.9239,
            "lon": 75.8267,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 1.5,
            "rating": 4.6,
        },
        {
            "place_id": "jdh_mehrangarh",
            "name": "Mehrangarh Fort Jodhpur",
            "category": "culture",
            "lat": 26.2978,
            "lon": 73.0185,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 3.5,
            "rating": 4.9,
        },
        {
            "place_id": "jpr_rawat",
            "name": "Rawat Mishthan Bhandar Pyaaz Kachori",
            "category": "food",
            "lat": 26.9200,
            "lon": 75.7980,
            "opening_hours": "07:00 - 22:00",
            "typical_duration_hours": 0.5,
            "rating": 4.6,
        },
        {
            "place_id": "jpr_nahargarh",
            "name": "Nahargarh Fort Sunset Terrace",
            "category": "rest",
            "lat": 26.9370,
            "lon": 75.8160,
            "opening_hours": "10:00 - 21:00",
            "typical_duration_hours": 2.0,
            "rating": 4.7,
        },
        {
            "place_id": "jdh_flyingfox",
            "name": "Flying Fox Zipline Over Fort Battlements",
            "category": "adventure",
            "lat": 26.2990,
            "lon": 73.0190,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 2.0,
            "rating": 4.7,
        },
    ],
    "south_goa_india": [
        {
            "place_id": "goa_palolem",
            "name": "Palolem Crescent White Sand Beach",
            "category": "nature",
            "lat": 15.0100,
            "lon": 74.0230,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 3.0,
            "rating": 4.7,
        },
        {
            "place_id": "goa_cabo_rama",
            "name": "Cabo De Rama Fortress & Ocean Cliff",
            "category": "culture",
            "lat": 15.0880,
            "lon": 73.9210,
            "opening_hours": "09:00 - 18:00",
            "typical_duration_hours": 2.0,
            "rating": 4.6,
        },
        {
            "place_id": "goa_martins",
            "name": "Martin's Corner Iconic Goan Seafood",
            "category": "food",
            "lat": 15.3110,
            "lon": 73.9160,
            "opening_hours": "11:30 - 23:30",
            "typical_duration_hours": 2.0,
            "rating": 4.6,
        },
        {
            "place_id": "goa_butterfly",
            "name": "Butterfly Beach Kayak & Dolphin Spotting",
            "category": "adventure",
            "lat": 15.0280,
            "lon": 74.0040,
            "opening_hours": "07:00 - 17:00",
            "typical_duration_hours": 2.5,
            "rating": 4.8,
        },
        {
            "place_id": "goa_agonda",
            "name": "Agonda Turtle Conservation Beach",
            "category": "rest",
            "lat": 15.0450,
            "lon": 73.9870,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 3.0,
            "rating": 4.7,
        },
        {
            "place_id": "goa_bom_jesus",
            "name": "Basilica of Bom Jesus UNESCO Heritage",
            "category": "culture",
            "lat": 15.5009,
            "lon": 73.9116,
            "opening_hours": "09:00 - 18:30",
            "typical_duration_hours": 1.5,
            "rating": 4.7,
        },
    ],
    "kerala_alleppey_india": [
        {
            "place_id": "ker_backwaters",
            "name": "Alleppey Punnamada Backwaters Houseboat",
            "category": "nature",
            "lat": 9.4981,
            "lon": 76.3388,
            "opening_hours": "08:00 - 18:00",
            "typical_duration_hours": 4.0,
            "rating": 4.9,
        },
        {
            "place_id": "ker_eravikulam",
            "name": "Eravikulam National Park & Anamudi",
            "category": "nature",
            "lat": 10.1500,
            "lon": 77.0600,
            "opening_hours": "07:30 - 16:00",
            "typical_duration_hours": 3.0,
            "rating": 4.7,
        },
        {
            "place_id": "ker_kolukkumalai",
            "name": "Kolukkumalai Highest Tea Estate Jeep Safari",
            "category": "adventure",
            "lat": 10.0800,
            "lon": 77.2100,
            "opening_hours": "04:30 - 18:00",
            "typical_duration_hours": 4.0,
            "rating": 4.9,
        },
        {
            "place_id": "ker_marari",
            "name": "Marari Serene Fishermen's Beach",
            "category": "rest",
            "lat": 9.6000,
            "lon": 76.2980,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 2.5,
            "rating": 4.6,
        },
        {
            "place_id": "ker_halais",
            "name": "Halais Authentic Malabar Biryani",
            "category": "food",
            "lat": 9.5010,
            "lon": 76.3390,
            "opening_hours": "11:30 - 22:30",
            "typical_duration_hours": 1.0,
            "rating": 4.4,
        },
        {
            "place_id": "ker_tea_museum",
            "name": "KDHP Tea Processing Museum Munnar",
            "category": "culture",
            "lat": 10.0900,
            "lon": 77.0500,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 1.5,
            "rating": 4.5,
        },
    ],
    "hampi_india": [
        {
            "place_id": "hampi_vittala",
            "name": "Vijaya Vittala Temple & Monolithic Stone Chariot",
            "category": "culture",
            "lat": 15.3350,
            "lon": 76.4750,
            "opening_hours": "08:30 - 17:30",
            "typical_duration_hours": 2.5,
            "rating": 4.9,
        },
        {
            "place_id": "hampi_virupaksha",
            "name": "Virupaksha Sacred Temple Tungabhadra",
            "category": "culture",
            "lat": 15.3350,
            "lon": 76.4600,
            "opening_hours": "06:00 - 20:00",
            "typical_duration_hours": 2.0,
            "rating": 4.8,
        },
        {
            "place_id": "hampi_matanga",
            "name": "Matanga Hill 360-degree Sunset Panorama",
            "category": "rest",
            "lat": 15.3310,
            "lon": 76.4660,
            "opening_hours": "05:30 - 18:30",
            "typical_duration_hours": 2.0,
            "rating": 4.9,
        },
        {
            "place_id": "hampi_sanapur",
            "name": "Sanapur Lake Bouldering & Coracle Ride",
            "category": "adventure",
            "lat": 15.3670,
            "lon": 76.4630,
            "opening_hours": "08:00 - 18:00",
            "typical_duration_hours": 2.5,
            "rating": 4.7,
        },
        {
            "place_id": "hampi_mangotree",
            "name": "Mango Tree Courtyard Thali Cafe",
            "category": "food",
            "lat": 15.3340,
            "lon": 76.4610,
            "opening_hours": "07:30 - 22:00",
            "typical_duration_hours": 1.5,
            "rating": 4.5,
        },
    ],
    "ooty_coorg_india": [
        {
            "place_id": "ooty_toytrain",
            "name": "Nilgiri Mountain Railway Heritage Steam Train",
            "category": "culture",
            "lat": 11.4102,
            "lon": 76.6950,
            "opening_hours": "07:00 - 18:00",
            "typical_duration_hours": 3.0,
            "rating": 4.8,
        },
        {
            "place_id": "coorg_abbey",
            "name": "Abbey Cascading Falls Madikeri",
            "category": "nature",
            "lat": 12.4540,
            "lon": 75.7190,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 2.0,
            "rating": 4.6,
        },
        {
            "place_id": "coorg_coffee",
            "name": "Kodagu Organic Coffee Plantation Tour",
            "category": "nature",
            "lat": 12.4200,
            "lon": 75.7400,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 2.5,
            "rating": 4.8,
        },
        {
            "place_id": "ooty_botanical",
            "name": "Government Botanical Gardens Ooty",
            "category": "rest",
            "lat": 11.4180,
            "lon": 76.7110,
            "opening_hours": "08:30 - 18:30",
            "typical_duration_hours": 2.0,
            "rating": 4.5,
        },
        {
            "place_id": "coorg_raintree",
            "name": "Raintree Traditional Kodava Pandi Curry",
            "category": "food",
            "lat": 12.4240,
            "lon": 75.7380,
            "opening_hours": "12:00 - 22:30",
            "typical_duration_hours": 1.5,
            "rating": 4.5,
        },
        {
            "place_id": "coorg_tadiandamol",
            "name": "Tadiandamol Highest Mountain Peak Trek",
            "category": "adventure",
            "lat": 12.2180,
            "lon": 75.6070,
            "opening_hours": "06:00 - 17:00",
            "typical_duration_hours": 5.0,
            "rating": 4.7,
        },
    ],
    "darjeeling_gangtok_india": [
        {
            "place_id": "darj_tigerhill",
            "name": "Tiger Hill Kanchenjunga Golden Sunrise",
            "category": "rest",
            "lat": 26.9940,
            "lon": 88.2860,
            "opening_hours": "04:00 - 08:00",
            "typical_duration_hours": 2.5,
            "rating": 4.9,
        },
        {
            "place_id": "darj_batasia",
            "name": "Batasia Loop Himalayan Spiral Railway",
            "category": "culture",
            "lat": 27.0180,
            "lon": 88.2520,
            "opening_hours": "05:00 - 20:00",
            "typical_duration_hours": 1.5,
            "rating": 4.7,
        },
        {
            "place_id": "gtk_nathula",
            "name": "Nathu La Indo-China High Mountain Pass",
            "category": "adventure",
            "lat": 27.3860,
            "lon": 88.8310,
            "opening_hours": "08:00 - 15:00",
            "typical_duration_hours": 4.0,
            "rating": 4.8,
        },
        {
            "place_id": "darj_glenarys",
            "name": "Glenary's Heritage Bakery & English Pub",
            "category": "food",
            "lat": 27.0430,
            "lon": 88.2660,
            "opening_hours": "07:00 - 22:00",
            "typical_duration_hours": 1.5,
            "rating": 4.7,
        },
        {
            "place_id": "gtk_rumtek",
            "name": "Rumtek Dharma Chakra Centre Monastery",
            "category": "culture",
            "lat": 27.3000,
            "lon": 88.5400,
            "opening_hours": "08:00 - 18:00",
            "typical_duration_hours": 2.0,
            "rating": 4.7,
        },
        {
            "place_id": "darj_happyvalley",
            "name": "Happy Valley First Flush Tea Estate",
            "category": "nature",
            "lat": 27.0540,
            "lon": 88.2630,
            "opening_hours": "08:00 - 16:30",
            "typical_duration_hours": 2.0,
            "rating": 4.6,
        },
    ],
    "meghalaya_shillong_india": [
        {
            "place_id": "meg_rootbridge",
            "name": "Double Decker Living Root Bridge Nongriat",
            "category": "adventure",
            "lat": 25.2509,
            "lon": 91.6708,
            "opening_hours": "06:00 - 17:00",
            "typical_duration_hours": 5.0,
            "rating": 4.9,
        },
        {
            "place_id": "meg_nohkalikai",
            "name": "Nohkalikai Falls Cherrapunji Plunge",
            "category": "nature",
            "lat": 25.2758,
            "lon": 91.6847,
            "opening_hours": "08:00 - 17:30",
            "typical_duration_hours": 2.0,
            "rating": 4.8,
        },
        {
            "place_id": "meg_dawki",
            "name": "Dawki Umngot Glass-Clear River Boat",
            "category": "rest",
            "lat": 25.1870,
            "lon": 92.0200,
            "opening_hours": "08:00 - 17:00",
            "typical_duration_hours": 3.0,
            "rating": 4.9,
        },
        {
            "place_id": "meg_cafedylan",
            "name": "Dylan's Cafe Shillong Rock Tribute",
            "category": "food",
            "lat": 25.5680,
            "lon": 91.8840,
            "opening_hours": "11:30 - 22:00",
            "typical_duration_hours": 1.5,
            "rating": 4.6,
        },
        {
            "place_id": "meg_mawsmai",
            "name": "Mawsmai Cave Spelunking Cherrapunji",
            "category": "adventure",
            "lat": 25.2440,
            "lon": 91.7240,
            "opening_hours": "09:00 - 17:00",
            "typical_duration_hours": 1.5,
            "rating": 4.6,
        },
        {
            "place_id": "meg_umiam",
            "name": "Umiam Lake Watersport & Quiet Vista",
            "category": "nature",
            "lat": 25.6600,
            "lon": 91.9000,
            "opening_hours": "24 Hours",
            "typical_duration_hours": 2.0,
            "rating": 4.5,
        },
    ],
}

# Alias resolution map
DEST_ALIASES = {
    "manali": "manali_spiti_india",
    "spiti": "manali_spiti_india",
    "manali_spiti": "manali_spiti_india",
    "rishikesh": "rishikesh_haridwar_india",
    "haridwar": "rishikesh_haridwar_india",
    "rishikesh_haridwar": "rishikesh_haridwar_india",
    "leh": "leh_ladakh_india",
    "ladakh": "leh_ladakh_india",
    "leh_ladakh": "leh_ladakh_india",
    "varanasi": "varanasi_india",
    "udaipur": "udaipur_mewar_india",
    "udaipur_mewar": "udaipur_mewar_india",
    "jaipur": "jaipur_jodhpur_india",
    "jodhpur": "jaipur_jodhpur_india",
    "jaipur_jodhpur": "jaipur_jodhpur_india",
    "goa": "south_goa_india",
    "south_goa": "south_goa_india",
    "kerala": "kerala_alleppey_india",
    "alleppey": "kerala_alleppey_india",
    "munnar": "kerala_alleppey_india",
    "munnar_alleppey": "kerala_alleppey_india",
    "hampi": "hampi_india",
    "ooty": "ooty_coorg_india",
    "coorg": "ooty_coorg_india",
    "ooty_coorg": "ooty_coorg_india",
    "darjeeling": "darjeeling_gangtok_india",
    "gangtok": "darjeeling_gangtok_india",
    "darjeeling_gangtok": "darjeeling_gangtok_india",
    "meghalaya": "meghalaya_shillong_india",
    "shillong": "meghalaya_shillong_india",
    "cherrapunji": "meghalaya_shillong_india",
    "meghalaya_shillong": "meghalaya_shillong_india",
}


def canonicalize_dest_id(dest_id: str) -> str:
    """Resolves arbitrary destination id or alias to canonical catalog ID."""
    clean = dest_id.lower().strip()
    if clean in OFFLINE_PLACES_DATA:
        return clean
    if clean in DEST_ALIASES:
        return DEST_ALIASES[clean]
    # Check suffix
    if f"{clean}_india" in OFFLINE_PLACES_DATA:
        return f"{clean}_india"
    # Substring search
    for k in OFFLINE_PLACES_DATA:
        if clean in k or k in clean:
            return k
    return dest_id


def get_offline_places_for_destination(dest_id: str) -> List[Dict[str, Any]]:
    """Returns curated fallback places list for a given destination."""
    canon = canonicalize_dest_id(dest_id)
    return OFFLINE_PLACES_DATA.get(canon, OFFLINE_PLACES_DATA["manali_spiti_india"])


# ============================================================================
# OpenStreetMap Live API Query
# ============================================================================

def fetch_osm_live_places(
    lat: float, lon: float, radius_m: int = 8000, timeout: float = 3.5
) -> Optional[List[Dict[str, Any]]]:
    """Queries OpenStreetMap Overpass API for live attractions, viewpoints,
    and restaurants within radius_m of the target coordinates.
    Returns None on any network error, rate-limit, timeout, or empty response.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    # Overpass QL query targeting tourist attractions, museums, viewpoints, and dining
    query = f"""
    [out:json][timeout:3];
    (
      node["tourism"~"attraction|museum|viewpoint"](around:{radius_m},{lat},{lon});
      node["amenity"~"restaurant|cafe"](around:{radius_m},{lat},{lon});
      node["historic"](around:{radius_m},{lat},{lon});
    );
    out center 15;
    """
    headers = {"User-Agent": "RLTravelGuide/1.0 (academic; btech-ai-ml)"}

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(overpass_url, data={"data": query}, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            elements = data.get("elements", [])
            if not elements:
                return None

            places = []
            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name:en") or tags.get("name")
                if not name:
                    continue

                # Category classification
                amenity = tags.get("amenity", "")
                tourism = tags.get("tourism", "")
                historic = tags.get("historic", "")

                if amenity in ("restaurant", "cafe", "fast_food", "food_court"):
                    category = "food"
                elif tourism == "viewpoint":
                    category = "nature"
                elif historic or tourism in ("museum", "monument") or "religion" in tags:
                    category = "culture"
                elif "sport" in tags or tourism == "theme_park":
                    category = "adventure"
                else:
                    category = "rest"

                places.append({
                    "place_id": f"osm_{el.get('id', len(places))}",
                    "name": name,
                    "category": category,
                    "lat": float(el.get("lat") or lat),
                    "lon": float(el.get("lon") or lon),
                    "opening_hours": tags.get("opening_hours", "09:00 - 18:00"),
                    "typical_duration_hours": 1.5 if category == "food" else 2.0,
                    "rating": 4.5,
                })

            return places if places else None
    except Exception:
        return None


def get_places_for_destination(
    destination_id: str,
    force_offline: bool = False,
    timeout: float = 3.5,
) -> Dict[str, Any]:
    """Retrieves places for a destination: attempts live OpenStreetMap fetch,
    falling back to guaranteed curated offline data.
    """
    canon_id = canonicalize_dest_id(destination_id)
    dest_info = get_indian_destination(canon_id)

    if not dest_info:
        # Fall back to first available destination coordinates if unknown
        lat, lon = 28.6139, 77.2090
        name = destination_id.replace("_", " ").title()
    else:
        lat, lon = dest_info["lat"], dest_info["lon"]
        name = dest_info["name"]

    places = None
    source = "offline-fallback"

    if not force_offline:
        places = fetch_osm_live_places(lat, lon, timeout=timeout)
        if places:
            source = "openstreetmap-live"

    if not places:
        places = get_offline_places_for_destination(canon_id)
        source = "offline-fallback"

    # Categorize places into activity & dining buckets
    by_category: Dict[str, List[Dict[str, Any]]] = {
        "culture": [],
        "nature": [],
        "food": [],
        "adventure": [],
        "rest": [],
    }
    for p in places:
        cat = p.get("category", "rest")
        by_category.setdefault(cat, []).append(p)

    return {
        "destination_id": canon_id,
        "destination_name": name,
        "coordinates": {"lat": lat, "lon": lon},
        "source": source,
        "total_places": len(places),
        "places": places,
        "by_category": by_category,
    }


# ============================================================================
# FastAPI Endpoints
# ============================================================================

router = APIRouter(tags=["places"])


@router.get("/destinations/india")
@router.get("/api/destinations/india")
def list_indian_destinations_endpoint(
    budget_tier: Optional[str] = Query(None, description="budget, mid_range, luxury"),
    interest: Optional[str] = Query(None, description="e.g. spiritual, adventure, beach, mountains, heritage"),
    max_budget_inr: Optional[int] = Query(None, description="Maximum budget threshold in INR"),
    region: Optional[str] = Query(None, description="North, West, South, East & NE"),
):
    """GET /api/destinations/india
    Returns curated pan-India destinations filtered by budget tier, regional interest, or max budget.
    """
    destinations = filter_indian_destinations(
        budget_tier=budget_tier,
        interest=interest,
        max_budget_inr=max_budget_inr,
        region=region,
    )
    return {
        "total": len(destinations),
        "destinations": destinations,
    }


@router.get("/places/live/{destination_id}")
@router.get("/api/places/live/{destination_id}")
def get_live_places_endpoint(
    destination_id: str,
    category: Optional[str] = Query(None, description="Optional filter: culture, nature, food, adventure, rest"),
    force_offline: bool = Query(False, description="Simulate network disconnect and force offline fallback"),
):
    """GET /api/places/live/{destination_id}
    Returns real-time or offline places categorized by activity & dining.
    """
    result = get_places_for_destination(destination_id, force_offline=force_offline)

    # Optional category filter
    if category:
        cat_clean = category.lower().strip()
        filtered = [p for p in result["places"] if p.get("category") == cat_clean]
        result["places"] = filtered
        result["total_places"] = len(filtered)

    return result


# Automatic attachment to global app routers so routes are registered everywhere
try:
    from app.api import router as _api_router
    _api_router.include_router(router)
except Exception:
    pass

try:
    from main import app as _main_app
    _main_app.include_router(router)
except Exception:
    pass
