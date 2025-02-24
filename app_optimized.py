import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 📂 Excel-Datei laden
@st.cache_data
def load_data(sheet_name):
    file_path = "Extrahierte_Daten.xlsx"
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df

# Titel der App
st.title("🔋 PV & Batteriespeicher Simulation mit Optimierung")
st.write("Wähle den Monat, optimiere den Wärmepumpenverbrauch und steuere die Netzladung der Batterie.")

# 📆 Monat auswählen (mit Jahr)
monat = st.selectbox("📆 Wähle den Monat aus:", ["Juni 2024", "Dezember 2024"])

# Mapping für den Excel-Sheetnamen
sheet_mapping = {"Juni 2024": "Juni", "Dezember 2024": "Dezember"}
df = load_data(sheet_mapping[monat])

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
if "Dynamischer" in tarifwahl:
    margen_aufschlag = st.slider("📊 Margenaufschlag auf Spotpreis (Ct/kWh)", min_value=5.0, max_value=20.0, value=10.0, step=0.5)
else:
    margen_aufschlag = 0

# 💰 Einspeisevergütung mit Jahr und neuer Option
einspeiseverguetung = st.radio("💰 Einspeisevergütung (Ct/kWh)", [
    "8,11 (Stand 2024)", 
    "7,95 (Stand 2025)", 
    "0,00 (Abhängig von Regulatorik der neuen BReg)"
])

# Auswahl in den Wert umwandeln
if "8,11" in einspeiseverguetung:
    einspeiseverguetung_value = 8.11
elif "7,95" in einspeiseverguetung:
    einspeiseverguetung_value = 7.95
else:
    einspeiseverguetung_value = 0.0  # Keine Einspeisevergütung

# 💰 Einspeiseerlös berechnen
df["Einspeiseerlös"] = df["Einspeisung"] * (einspeiseverguetung_value / 100)

# ✅ Checkboxen zur Steuerung der Optimierung
wp_optimierung = st.checkbox("🔀 Wärmepumpen-Optimierung aktivieren", value=True)
netzladung_erlaubt = st.checkbox("🔋 Netzladung der Batterie erlauben", value=False)

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

# 💡 Wärmepumpen-Optimierung
df["WP_Optimiert"] = df["Wärmepumpen-Verbrauch"]
if wp_optimierung and "Dynamischer" in tarifwahl:
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
df["Netzladung"] = 0

soc = 0
for day in df["Datum"].dt.date.unique():
    daily_df = df[df["Datum"].dt.date == day].copy()
    
    # 🧮 Tagesbedarf berechnen
    tagesbedarf = max((daily_df["Haushaltsverbrauch"] + daily_df["WP_Optimiert"] - daily_df["PV-Erzeugung"]).sum(), 0)

    # 💡 Netzladung zwischen 0-6 Uhr
    if netzladung_erlaubt:
        early_hours_df = daily_df[daily_df["Stunde"].between(0, 6)]
        guenstigste_stunde_idx = early_hours_df["Netzpreis"].idxmin()

        # Lade maximal den Tagesbedarf, aber nicht mehr als Kapazität
        netzladung = min(tagesbedarf, batterie_kapazitaet - soc)
        df.at[guenstigste_stunde_idx, "Netzladung"] = netzladung
        soc += netzladung * 0.96  # Wirkungsgrad berücksichtigen

    # ⚡ PV-Überschuss laden & Tagesverbrauch decken
    for i in daily_df.index:
        pv_ueberschuss = max(df.loc[i, "PV-Erzeugung"] - (df.loc[i, "Haushaltsverbrauch"] + df.loc[i, "WP_Optimiert"]), 0)
        ladung = min(batterie_kapazitaet - soc, pv_ueberschuss)
        soc += ladung * 0.96
        soc = min(batterie_kapazitaet, max(0, soc))
        df.at[i, "Batterie_Ladung"] = ladung

        # Entladung zur Deckung des Verbrauchs
        strombedarf = max((df.loc[i, "Haushaltsverbrauch"] + df.loc[i, "WP_Optimiert"]) - df.loc[i, "PV-Erzeugung"], 0)
        entladung = min(soc, strombedarf)
        soc -= entladung / 0.96
        df.at[i, "Batterie_Entladung"] = entladung
        df.at[i, "SOC"] = soc

# 💰 Kosten & Erträge berechnen
df["Netzbezug"] = np.maximum(df["Haushaltsverbrauch"] + df["WP_Optimiert"] - df["PV-Erzeugung"] - df["Batterie_Entladung"], 0) + df["Netzladung"]
df["Einspeisung"] = np.maximum(df["PV-Erzeugung"] - (df["Haushaltsverbrauch"] + df["WP_Optimiert"] - df["Batterie_Entladung"]), 0)
df["Einspeiseerlös"] = df["Einspeisung"] * (einspeiseverguetung_value / 100)
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

# 📅 Visualisierungszeitraum auswählen
zeitraum = st.radio("📊 Wähle den Zeitraum für die Visualisierung:", ["Tag", "Woche", "Monat"])
if zeitraum == "Tag":
    unique_days = df["Datum"].dt.date.unique()
    selected_day = st.slider("📅 Wähle den Tag aus:", min_value=0, max_value=len(unique_days)-1, value=0)
    df_filtered = df[df["Datum"].dt.date == unique_days[selected_day]]
elif zeitraum == "Woche":
    unique_weeks = df["Datum"].dt.isocalendar().week.unique()
    selected_week = st.slider("📅 Wähle die Woche aus:", min_value=min(unique_weeks), max_value=max(unique_weeks), value=min(unique_weeks))
    df_filtered = df[df["Datum"].dt.isocalendar().week == selected_week]
else:
    df_filtered = df

# 📊 Visualisierung: PV, SOC, Verbrauch
fig, ax1 = plt.subplots(figsize=(15, 6))
ax1.plot(df_filtered["Index"], df_filtered["PV-Erzeugung"], label="PV-Erzeugung", color="orange", linewidth=2)
ax1.plot(df_filtered["Index"], df_filtered["SOC"], label="Batterie-SOC", color="green", linewidth=2)
bar_width = 0.4
x = df_filtered["Index"]
ax1.bar(x - bar_width/2, df_filtered["Haushaltsverbrauch"], width=bar_width, label="Haushaltsverbrauch", color="blue", alpha=0.7)
ax1.bar(x + bar_width/2, df_filtered["WP_Optimiert"], width=bar_width, label="WP-Verbrauch", color="red", alpha=0.7)

ax1.set_xlabel("Index-Stunde")
ax1.set_ylabel("kWh")
ax1.set_title("PV-Erzeugung, Verbrauch & Batterie-SOC")
ax1.legend()
ax1.grid(True)
st.pyplot(fig)

# 📥 CSV-Download
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Download CSV",
    data=csv,
    file_name='simulationsergebnisse.csv',
    mime='text/csv',
)
