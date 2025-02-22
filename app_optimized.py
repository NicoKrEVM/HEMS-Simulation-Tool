import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

# 📷 Firmenlogo einfügen
logo = Image.open("Logo_Energieversorgung_Mittelrhein_(evm).svg.png")
st.image(logo, use_column_width=True)

# 📂 Excel-Datei laden
@st.cache_data
def load_data(sheet_name):
    file_path = "Extrahierte_Daten.xlsx"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df

# Titel der App
st.title("🔋 PV & Batteriespeicher Simulation mit Monatswahl und Optimierung")
st.write("Wähle den Monat, optimiere den Wärmepumpenverbrauch und steuere die Netzladung der Batterie.")

# 📆 Monat auswählen
monat = st.selectbox("📆 Wähle den Monat aus:", ["Juni", "Dezember"])

# Daten laden
df = load_data(monat)

# 📈 PV-Anlagengröße auswählen
pv_leistung = st.slider("📈 PV-Leistung (kWp)", min_value=5.0, max_value=20.0, value=11.0, step=0.5)
pv_scaling_factor = pv_leistung / 11.0
df["PV-Erzeugung"] *= pv_scaling_factor

# 🔋 Batteriespeichergröße auswählen
batterie_kapazitaet = st.slider("🔋 Batteriespeicher-Kapazität (kWh)", min_value=5.0, max_value=15.0, value=10.46, step=0.5)

# ⚡ Tarifwahl
tarifwahl = st.selectbox("⚡ Wähle den Stromtarif:", [
    "📌 Statischer Tarif (33,9 Ct/kWh)",
    "📌 Kombinierter WP-Tarif (33,9 Ct/kWh Haushalt, 24,5 Ct/kWh WP)",
    "📌 Dynamischer Tarif (mit statischem Netzentgelt)",
    "📌 Dynamischer Tarif (mit dynamischem Netzentgelt)"
])

# 🧮 Margenaufschlag für dynamische Tarife
margen_aufschlag = st.slider("📊 Margenaufschlag auf Spotpreis (Ct/kWh)", min_value=5.0, max_value=20.0, value=10.0, step=0.5)

# 💰 Einspeisevergütung
einspeiseverguetung = st.radio("💰 Einspeisevergütung (Ct/kWh)", [8.11, 7.95])

# 🔀 Zusätzliche Optimierungsoptionen
if "Dynamischer" in tarifwahl:
    wp_optimierung = st.checkbox("🔀 Wärmepumpen-Optimierung aktivieren", value=True)
    netzladung_erlaubt = st.checkbox("🔋 Netzladung der Batterie erlauben", value=False)
else:
    wp_optimierung = False
    netzladung_erlaubt = False

# 📊 Netzpreis berechnen
if "Dynamischer" in tarifwahl:
    df["Netzpreis"] = df["Spotpreis"] + margen_aufschlag
    if "dynamischem Netzentgelt" in tarifwahl:
        df.loc[df["Stunde"].isin([17, 18, 19]), "Netzpreis"] += 9.76
        df.loc[df["Stunde"].isin([1, 2, 3]), "Netzpreis"] += 2.09
    else:
        df["Netzpreis"] += 8.35
else:
    df["Netzpreis"] = 33.9 if "Statischer" in tarifwahl else np.where(df["Wärmepumpen-Verbrauch"] > 0, 24.5, 33.9)

# 💡 Wärmepumpen-Optimierung (Lastverschiebung ±3h)
df["WP_Optimiert"] = df["Wärmepumpen-Verbrauch"]
if wp_optimierung:
    for i in range(len(df)):
        aktueller_preis = df.loc[i, "Netzpreis"]
        aktuelle_last = df.loc[i, "Wärmepumpen-Verbrauch"]
        start = max(0, i - 3)
        end = min(len(df) - 1, i + 3)
        fenster = df.loc[start:end, "Netzpreis"]
        guenstigste_stunde = fenster.idxmin()
        if df.loc[guenstigste_stunde, "Netzpreis"] < aktueller_preis:
            df.at[i, "WP_Optimiert"] -= aktuelle_last
            df.at[guenstigste_stunde, "WP_Optimiert"] += aktuelle_last

# ⚡ Batteriespeicher: Laden & Entladen
df["SOC"] = 0
df["Batterie_Ladung"] = 0
df["Batterie_Entladung"] = 0

soc = 0

for i in df.index:
    pv_ueberschuss = max(df.loc[i, "PV-Erzeugung"] - (df.loc[i, "Haushaltsverbrauch"] + df.loc[i, "WP_Optimiert"]), 0)
    ladung = min(batterie_kapazitaet - soc, pv_ueberschuss)
    soc += ladung * 0.96
    soc = min(batterie_kapazitaet, max(0, soc))
    df.at[i, "Batterie_Ladung"] = ladung

    if netzladung_erlaubt and soc < batterie_kapazitaet:
        netzladung = min(batterie_kapazitaet - soc, max(df.loc[i, "Netzpreis"], 0))
        soc += netzladung * 0.96
        df.at[i, "Batterie_Ladung"] += netzladung

    strombedarf = max((df.loc[i, "Haushaltsverbrauch"] + df.loc[i, "WP_Optimiert"]) - df.loc[i, "PV-Erzeugung"], 0)
    entladung = min(soc, strombedarf)
    soc -= entladung / 0.96
    df.at[i, "Batterie_Entladung"] = entladung
    df.at[i, "SOC"] = soc

# 💸 Kosten & Erträge berechnen
df["Netzbezug"] = np.maximum(df["Haushaltsverbrauch"] + df["WP_Optimiert"] - df["PV-Erzeugung"] - df["Batterie_Entladung"], 0)
df["Einspeisung"] = np.maximum(df["PV-Erzeugung"] - (df["Haushaltsverbrauch"] + df["WP_Optimiert"] - df["Batterie_Entladung"]), 0)
df["Einspeiseerlös"] = df["Einspeisung"] * (einspeiseverguetung / 100)
df["Netzkosten"] = df["Netzbezug"] * (df["Netzpreis"] / 100)

# 💸 Gesamtkosten
total_cost = df["Netzkosten"].sum()
total_income = df["Einspeiseerlös"].sum()
total_balance = total_cost - total_income

# 🏆 Ergebnisse anzeigen
st.subheader("💰 Simulationsergebnisse")
st.write(f"**Gesamtkosten für Netzstrom:** {total_cost:.2f} €")
st.write(f"**Einnahmen aus Einspeisung:** {total_income:.2f} €")
st.write(f"**Endsaldo (Netzkosten - Einspeiseerlöse):** {total_balance:.2f} €")

# 📊 Visualisierung: PV, SOC/Preis, Verbrauch
fig, ax1 = plt.subplots(figsize=(15, 6))

ax1.plot(df["Datum"], df["PV-Erzeugung"], label="PV-Erzeugung", color="orange", linewidth=2)
ax1.bar(df["Datum"], df["Haushaltsverbrauch"], width=0.03, label="Haushaltsverbrauch", color="blue", alpha=0.7)
ax1.bar(df["Datum"], df["WP_Optimiert"], width=0.03, label="WP-Verbrauch", color="red", alpha=0.7)
ax1.set_xlabel("Zeit")
ax1.set_ylabel("kWh")
ax1.set_title("PV-Erzeugung, Verbrauch & SOC/Strompreis")
ax1.legend(loc='upper left')
ax1.grid(True)

ax2 = ax1.twinx()
df["SOC_%"] = (df["SOC"] / batterie_kapazitaet) * 100
ax2.plot(df["Datum"], df["SOC_%"], label="Batterie-SOC (%)", color="green", linestyle="--", linewidth=2)
ax2.set_ylabel("Batterie-SOC (%)", color="green")
ax2.tick_params(axis='y', labelcolor="green")
ax2.set_ylim(0, 100)

st.pyplot(fig)

# 📥 CSV-Download
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Download CSV",
    data=csv,
    file_name='simulationsergebnisse.csv',
    mime='text/csv',
)

# 📬 Kontaktinformationen als Footer
st.markdown("---")
st.markdown("""
### 📧 Kontaktinformationen  
Bei Rückfragen zum Tool sowie dem Projekt **"Smartes Energiesystem"** wenden Sie sich gerne an das Team des Innovationsmanagements.  
**Ihr Ansprechpartner:** Nicolai Kretz  
📩 **E-Mail:** nicolai.kretz@evm.de  
""")
