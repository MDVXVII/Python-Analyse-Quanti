import numpy as np
from scipy.stats import norm

# Paramètres du trade : call spread 80/90 sur le TTF Nov26
F = 74.28 # Prix du future (EUR/MWh)
K1 = 80 # Strike du call acheté
K2 = 90 # Strike du call vendu
sigma = 0.75 # Volatilité implicite
jours = 36 # Jours calendaires jusqu'à l'échéance des options
T = jours / 365 # Maturité en années
r = 0.02 # Taux sans risque, sert juste à actualiser
volume = 100_000 # Volume en MWh pour avoir des montants en euros


# Modèle de Black 76 : comme Black-Scholes mais sur un future (pas de r dans d1)
def black76(F, K, sigma, T, r):
    d1 = (np.log(F / K) + sigma**2 / 2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    actu = np.exp(-r * T) # Facteur d'actualisation

    call = actu * (F * norm.cdf(d1) - K * norm.cdf(d2))
    delta = actu * norm.cdf(d1)
    vega = actu * F * norm.pdf(d1) * np.sqrt(T) / 100 # Pour +1 point de vol
    theta = (- actu * F * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) + r * call) / 365 # Par jour
    proba = norm.cdf(d2) # Proba risque-neutre de finir au-dessus du strike

    return {"call": call, "delta": delta, "vega": vega, "theta": theta, "proba": proba}


# Prix des deux jambes et du spread
jambe1 = black76(F, K1, sigma, T, r) # Call 80 acheté
jambe2 = black76(F, K2, sigma, T, r) # Call 90 vendu
prime = jambe1["call"] - jambe2["call"] # Ce qu'on paye pour le spread (= perte max)
largeur = K2 - K1
gain_max = largeur - prime # Si F finit au-dessus de 90
point_mort = K1 + prime
proba_zone = prime / (largeur * np.exp(-r * T)) # Prime / largeur = proba approx de finir dans la zone

# Greeks du spread : jambe achetée - jambe vendue
delta = jambe1["delta"] - jambe2["delta"]
vega = jambe1["vega"] - jambe2["vega"]
theta = jambe1["theta"] - jambe2["theta"]


# Affichage des resultats
print(f"\nCall spread {K1}/{K2} sur TTF Nov26 (F = {F:.2f}, vol = {sigma:.0%}, T = {jours} j)\n")
print(f"  Call {K1} achete : {jambe1['call']:6.3f} EUR/MWh")
print(f"  Call {K2} vendu : {jambe2['call']:6.3f} EUR/MWh")
print(f"  Prime nette : {prime:6.3f} EUR/MWh")
print(f"  Point mort : {point_mort:6.2f} ({point_mort / F - 1:+.1%} vs F)")
print(f"  Gain max / perte max : {gain_max:.2f} / {prime:.2f}  (ratio {gain_max / prime:.2f})")
print(f"  Proba implicite ~ : {proba_zone:.1%}")
print(f"  P(F_T > {K1}) / P(F_T > {K2}) : {jambe1['proba']:.1%} / {jambe2['proba']:.1%}")
print(f"  Delta {delta:.3f} | Vega {vega:.3f} /pt vol | Theta {theta:.3f} /jour")
print(f"\n  Pour {volume:,.0f} MWh : prime {prime * volume:,.0f} EUR, gain max {gain_max * volume:,.0f} EUR\n")


# Sensibilité de la prime à la vol : on reprice le spread avec plusieurs vols
print("  Sensibilite a la volatilite :")
for vol in [0.45, 0.60, 0.75, 0.90, 1.05, 1.20]:
    c1 = black76(F, K1, vol, T, r)["call"]
    c2 = black76(F, K2, vol, T, r)["call"]
    print(f"    vol {vol * 100:4.0f} %  ->  prime {c1 - c2:5.3f}  (call {K1} {c1:5.2f}, call {K2} {c2:5.2f})")