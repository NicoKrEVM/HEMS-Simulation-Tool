import streamlit as st
import pandas as pd
import numpy as np

# Titel des Tools
st.title("🔋 PV & Batteriespeicher Simulation")
st.write("Dieses Tool ermöglicht die Simulation von verschiedenen PV-Anlagen, Batteriespeichern und Stromtarifen.")

# 📊 **Eingabeparameter**

# PV-Anlagengröße
pv_leistung = st.slider("📈 PV-Leistung (kWp)", min_value=5.0, max_value=20.0, value=11.0, step=0.5)
st.write(f"PV-Daten basieren auf einer 11 kWp-Anlage (0° Azimut, 35° Aufständerung). Deine Auswahl: {pv_leistung} kWp")

# Batteriespeichergröße
batterie_kapazitaet = st.slider("🔋 Batteriespeicher-Kapazität (kWh)", min_value=5.0, max_value=15.0, value=10.46, step=0.5)
st.write(f"Dein gewählter Batteriespeicher: {batterie_kapazitaet} kWh")

# Tarifwahl
tarifoptionen = [
    "📌 Statischer Tarif (33,9 Ct/kWh)",
    "📌 Kombinierter WP-Tarif (33,9 Ct/kWh Haushalt, 24,5 Ct/kWh WP)",
    "📌 Dynamischer Tarif (mit statischem Netzentgelt)",
    "📌 Dynamischer Tarif (mit dynamischem Netzentgelt)"
]
tarifwahl = st.selectbox("⚡ Wähle den Stromtarif:", tarifoptionen)

# Margenaufschlag für dynamische Tarife
margen_aufschlag = st.slider("📊 Margenaufschlag auf Spotpreis (Ct/kWh)", min_value=5.0, max_value=20.0, value=10.0, step=0.5)
st.write(f"Gewählter Margenaufschlag: {margen_aufschlag} Ct/kWh")

# Einspeisevergütung
einspeiseverguetung = st.radio("💰 Einspeisevergütung (Ct/kWh)", [8.11, 7.95])
st.write(f"Gewählte Einspeisevergütung: {einspeiseverguetung} Ct/kWh")

# 🟢 **Berechnung der PV-Erträge basierend auf Skalierung**
# Hier werden die PV-Daten entsprechend skaliert
pv_scaling_factor = pv_leistung / 11.0  # Skalierung basierend auf 11 kWp-Daten

# Beispielhafte Rohdaten (später durch echte Daten ersetzen)
df = pd.DataFrame({
    "Stunde": np.tile(np.arange(24), 7),  # Eine Woche simulieren
    "PV-Erzeugung": np.random.uniform(0, 5, 24*7) * pv_scaling_factor,  # Skalierung der Erträge
    "Haushaltsverbrauch": np.random.uniform(0.5, 2.5, 24*7),
    "WP-Verbrauch": np.random.uniform(0, 3, 24*7)
})

# 🟡 Berechnung des Netzstrompreises basierend auf der Tarifwahl
if "Dynamischer" in tarifwahl:
    df["Spotpreis"] = np.random.uniform(5, 25, 24*7)  # Zufällige Spotpreise
    df["Netzpreis"] = df["Spotpreis"] + margen_aufschlag
    if "dynamischem Netzentgelt" in tarifwahl:
        df.loc[df["Stunde"].isin([17, 18, 19]), "Netzpreis"] += 9.76  # Peak-Zeiten
        df.loc[df["Stunde"].isin([1, 2, 3]), "Netzpreis"] += 2.09  # Niedrige Zeiten
    else:
        df["Netzpreis"] += 8.35  # Statisches Netzentgelt
else:
    df["Netzpreis"] = 33.9 if "Statischer" in tarifwahl else np.where(df["WP-Verbrauch"] > 0, 24.5, 33.9)

# 💡 Berechnung der Einspeisung & Netzbezug
df["Netzbezug"] = np.maximum(df["Haushaltsverbrauch"] + df["WP-Verbrauch"] - df["PV-Erzeugung"], 0)
df["Einspeisung"] = np.maximum(df["PV-Erzeugung"] - (df["Haushaltsverbrauch"] + df["WP-Verbrauch"]), 0)
df["Einspeiseerlös"] = df["Einspeisung"] * (einspeiseverguetung / 100)
df["Netzkosten"] = df["Netzbezug"] * (df["Netzpreis"] / 100)

total_cost = df["Netzkosten"].sum()
total_income = df["Einspeiseerlös"].sum()
total_balance = total_cost - total_income

# 🏆 **Ergebnisse anzeigen**
st.subheader("💰 Simulationsergebnisse")
st.write(f"**Gesamtkosten für Netzstrom:** {total_cost:.2f} €")
st.write(f"**Einnahmen aus Einspeisung:** {total_income:.2f} €")
st.write(f"**Endsaldo (Netzkosten - Einspeiseerlöse):** {total_balance:.2f} €")

# 📈 Diagramm
st.subheader("📊 Visualisierung")
st.line_chart(df[["Netzpreis", "Spotpreis"]])
