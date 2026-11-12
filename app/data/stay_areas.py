"""Curated neighbourhood recommendations, never fabricated hotel listings."""
from urllib.parse import quote
from app.core.assumptions import STAY_RATES_INR, TIER_LABELS

# Coordinates are neighbourhood centres for maps search, not property locations.
AREA_NAMES = {
 'manali_spiti_india': [('Old Manali',32.252,77.181),('Aleo',32.229,77.195),('Mall Road Manali',32.242,77.189)],
 'rishikesh_haridwar_india': [('Tapovan',30.128,78.322),('Swarg Ashram',30.119,78.312),('Triveni Ghat',30.103,78.299)],
 'leh_ladakh_india': [('Changspa',34.169,77.577),('Fort Road Leh',34.160,77.580),('Skara',34.145,77.571)],
 'varanasi_india': [('Assi Ghat',25.289,83.006),('Godowlia',25.309,83.008),('Cantonment Varanasi',25.335,82.982)],
 'amritsar_india': [('Golden Temple precinct',31.620,74.877),('Ranjit Avenue',31.659,74.858),('Lawrence Road',31.650,74.877)],
 'jaipur_jodhpur_india': [('Bani Park Jaipur',26.931,75.789),('Civil Lines Jaipur',26.910,75.777),('Pink City Jaipur',26.924,75.824)],
 'udaipur_india': [('Lake Pichola',24.576,73.679),('Fateh Sagar',24.602,73.681),('Hathi Pol',24.588,73.688)],
 'goa_india': [('Panjim Fontainhas',15.494,73.832),('Calangute',15.544,73.755),('Colva',15.279,73.922)],
 'mumbai_india': [('Colaba',18.916,72.827),('Bandra West',19.060,72.830),('Dadar',19.019,72.843)],
 'rann_of_kutch_india': [('Dhordo',23.839,69.586),('Hodka',23.680,69.617),('Bhirandiyara',23.574,69.629)],
 'kerala_backwaters_india': [('Alappuzha Beach',9.492,76.318),('Punnamada',9.519,76.353),('Mullakkal',9.501,76.343)],
 'munnar_india': [('Munnar Town',10.089,77.060),('Pallivasal',10.035,77.056),('Chithirapuram',10.030,77.046)],
 'ooty_coorg_india': [('Charring Cross Ooty',11.410,76.708),('Fern Hill Ooty',11.395,76.684),('Ooty Lake',11.402,76.686)],
 'hampi_india': [('Kamalapura',15.297,76.476),('Hampi Bazaar',15.335,76.461),('Hosapete',15.269,76.388)],
 'mysuru_india': [('Nazarbad',12.306,76.669),('Lakshmipuram',12.292,76.644),('Gokulam',12.335,76.621)],
 'pondicherry_india': [('White Town',11.932,79.834),('Heritage Town',11.941,79.831),('Kuruchikuppam',11.947,79.837)],
 'kolkata_india': [('Park Street',22.552,88.353),('Ballygunge',22.528,88.365),('Esplanade',22.565,88.352)],
 'darjeeling_gangtok_india': [('Chowrasta Darjeeling',27.044,88.268),('Gandhi Road Darjeeling',27.038,88.264),('Lebong Cart Road',27.057,88.264)],
 'shillong_cherrapunji_india': [('Police Bazaar Shillong',25.578,91.882),('Laitumkhrah Shillong',25.574,91.902),('Laban Shillong',25.566,91.873)],
 'andaman_india': [('Aberdeen Bazaar',11.668,92.741),('Dollygunj',11.635,92.714),('Junglighat',11.655,92.729)],
}


def areas_for_destination(destination_id=None, lat=None, lon=None):
    from app.data.india_destinations import INDIAN_DESTINATIONS
    from app.providers.geo import haversine_distance_km
    # Resolve aliases by matching the destination centre; all 20 catalogue
    # destinations have explicit neighbourhoods below, verified by a test.
    rows = AREA_NAMES.get(destination_id)
    if rows is None and lat is not None:
        nearest = min(AREA_NAMES, key=lambda key: min(haversine_distance_km(lat,lon,a,b) for _,a,b in AREA_NAMES[key]))
        if min(haversine_distance_km(lat,lon,a,b) for _,a,b in AREA_NAMES[nearest]) < 50:
            rows = AREA_NAMES[nearest]
    return [{'area_name': name, 'lat': a, 'lon': b,
             'label': 'Indicative - no live listings',
             'price_bands': {k: {'label': TIER_LABELS[k], 'min_inr': v[0], 'max_inr': v[1]} for k,v in STAY_RATES_INR.items()},
             'external_search_url': 'https://www.google.com/maps/search/?api=1&query='+quote('hotels in '+name)} for name,a,b in (rows or [])]

# Current catalogue aliases and their actual primary-city neighbourhoods.
AREA_NAMES.update({
 'delhi_india': [('Connaught Place Delhi',28.631,77.216),('Karol Bagh Delhi',28.651,77.190),('Civil Lines Delhi',28.677,77.225)],
 'pune_india': [('Shivaji Nagar Pune',18.531,73.847),('Deccan Gymkhana Pune',18.516,73.840),('Koregaon Park Pune',18.538,73.893)],
 'mysuru_india': AREA_NAMES['mysuru_india'],
 'pondicherry_india': AREA_NAMES['pondicherry_india'],
 'udaipur_mewar_india': AREA_NAMES['udaipur_india'],
 'ladakh_leh_india': AREA_NAMES['leh_ladakh_india'],
 'varanasi_kashi_india': AREA_NAMES['varanasi_india'],
 'jaipur_rajasthan_india': AREA_NAMES['jaipur_jodhpur_india'],
 'hampi_karnataka_india': AREA_NAMES['hampi_india'],
 'meghalaya_shillong_india': AREA_NAMES['shillong_cherrapunji_india'],
 'darjeeling_sikkim_india': AREA_NAMES['darjeeling_gangtok_india'],
 'kerala_alleppey_india': AREA_NAMES['kerala_backwaters_india'],
 'amritsar_punjab_india': AREA_NAMES['amritsar_india'],
 'south_goa_india': [('Palolem',15.010,74.023),('Agonda',15.043,73.988),('Colva',15.279,73.922)],
 'andaman_havelock_india': [('Govind Nagar Havelock',12.039,92.984),('Vijay Nagar Havelock',12.012,92.992),('Radhanagar Havelock',12.006,92.951)],
 'agra_braj_india': [('Taj Ganj Agra',27.159,78.044),('Civil Lines Agra',27.203,78.006),('Fatehabad Road Agra',27.157,78.052)],
})
