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
st.title("🔋 PV & Batteriespeicher Simulation mit Monatswahl und Optimierung")
st.write("Wähle den Monat, optimiere den Wärmepumpenverbrauch und steuere die Netzladung der Batterie.")

# 📆 Monat auswählen
monat = st.selectbox("📆 Wähle den Monat aus:", ["Juni", "Dezember"])

# Daten laden
df = load_data(monat)

# 📈 PV-Anlagengröße auswählen
pv_leistung = st.slider("📈 PV-Leistung (kWp)", min_value=5.0, max_value=20.0, value=11.0, step=0.5)
pv_scaling_factor = pv_leistung / 11.0  # Skalierung basierend auf 11 kWp
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
        df.loc[df["Stunde"].isin([17, 18, 19]), "Netzpreis"] += 9.76  # Peak-Zeiten
        df.loc[df["Stunde"].isin([1, 2, 3]), "Netzpreis"] += 2.09  # Niedrige Zeiten
    else:
        df["Netzpreis"] += 8.35  # Statisches Netzentgelt
else:
    df["Netzpreis"] = 33.9 if "Statischer" in tarifwahl else np.where(df["Wärmepumpen-Verbrauch"] > 0, 24.5, 33.9)

# 💡 Wärmepumpen-Optimierung (Lastverschiebung ±3h) mit Fehlerbehebung
df["WP_Optimiert"] = df["Wärmepumpen-Verbrauch"]
if wp_optimierung:
    for i in range(len(df)):
        aktueller_preis = df.loc[i, "Netzpreis"]
        aktuelle_last = df.loc[i, "Wärmepumpen-Verbrauch"]
        start = max(0, i - 3)
        end = min(df.index.max(), i + 3)  # Verwende df.index.max() statt len(df) - 1
        fenster = df.loc[start:end, ["Netzpreis"]]

        # Prüfen, ob das Fenster leer ist
        if not fenster.empty:
            guenstigste_stunde = fenster["Netzpreis"].idxmin()

            # Prüfen, ob der Index existiert
            if guenstigste_stunde in df.index:
                if df.loc[guenstigste_stunde, "Netzpreis"] < aktueller_preis:
                    df.at[i, "WP_Optimiert"] -= aktuelle_last
                    df.at[guenstigste_stunde, "WP_Optimiert"] += aktuelle_last
            else:
                st.warning(f"⚠️ Kein gültiger Index gefunden für die Lastverschiebung bei Stunde {i}.")
        else:
            st.warning(f"⚠️ Leeres Optimierungsfenster bei Stunde {i}.")

# ⚡ Batteriespeicher: Laden & Entladen (fortlaufend über den Monat)
df["SOC"] = 0  # State of Charge
df["Batterie_Ladung"] = 0
df["Batterie_Entladung"] = 0

soc = 0  # Initialer SOC

for i in df.index:
    # 💡 Berechne PV-Überschuss pro Stunde
    pv_ueberschuss = max(df.loc[i, "PV-Erzeugung"] - (df.loc[i, "Haushaltsverbrauch"] + df.loc[i, "WP_Optimiert"]), 0)

    # 🔋 Lade die Batterie mit PV-Überschuss (96% Wirkungsgrad)
    ladung = min(batterie_kapazitaet - soc, pv_ueberschuss)
    soc += ladung * 0.96  # 96% Wirkungsgrad
    soc = min(batterie_kapazitaet, max(0, soc))  # Begrenzung des SOC
    df.at[i, "Batterie_Ladung"] = ladung

    # ⚡ Netzladung falls erlaubt
    if netzladung_erlaubt and soc < batterie_kapazitaet:
        netzladung = min(batterie_kapazitaet - soc, max(df.loc[i, "Netzpreis"], 0))
        soc += netzladung * 0.96
        df.at[i, "Batterie_Ladung"] += netzladung

    # ⚡ Entlade die Batterie bei Bedarf
    strombedarf = max((df.loc[i, "Haushaltsverbrauch"] + df.loc[i, "WP_Optimiert"]) - df.loc[i, "PV-Erzeugung"], 0)
    entladung = min(soc, strombedarf)
    soc -= entladung / 0.96  # Entladung mit Wirkungsgradverlust
    df.at[i, "Batterie_Entladung"] = entladung

    # ✅ Aktualisiere SOC
    df.at[i, "SOC"] = soc

# 💰 Kosten & Erträge berechnen
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

# 📅 7-Tage-Slider für Visualisierung
min_day = df["Datum"].min().date()
max_day = df["Datum"].max().date()

start_date = st.slider("📅 Wähle Startdatum für die 7 Tage", min_value=min_day, max_value=max_day, value=min_day)
end_date = start_date + pd.Timedelta(days=7)

df_filtered = df[(df["Datum"] >= pd.to_datetime(start_date)) & (df["Datum"] < pd.to_datetime(end_date))]

# 📅 Erstelle fortlaufenden Zeitstempel (Datum + Stunde)
df_filtered["Zeit"] = pd.to_datetime(df_filtered["Datum"]) + pd.to_timedelta(df_filtered["Stunde"], unit='h')

# 📊 Visualisierung: PV, SOC/Preis, Verbrauch (mit erweiterter Auswahl)
fig, ax1 = plt.subplots(figsize=(15, 6))

if df_filtered.empty:
    st.warning("⚠️ Keine Daten für den ausgewählten Zeitraum.")
else:
    # 📊 Auswahl: SOC (%) oder Strompreis anzeigen
    plot_option = st.selectbox("🔄 Wähle Anzeige auf rechter Achse:", ["Batterie-SOC (%)", "Strompreis (Ct/kWh)"])

    # ✅ PV und Verbrauch auf linker Achse
    ax1.plot(df_filtered["Zeit"], df_filtered["PV-Erzeugung"], label="PV-Erzeugung", color="orange", linewidth=2)
    bar_width = 0.03  # Schmaler Balken für Zeitreihe
    x = df_filtered["Zeit"]
    ax1.bar(x - pd.Timedelta(minutes=15), df_filtered["Haushaltsverbrauch"], width=bar_width, label="Haushaltsverbrauch", color="blue", alpha=0.7)
    ax1.bar(x + pd.Timedelta(minutes=15), df_filtered["WP_Optimiert"], width=bar_width, label="WP-Verbrauch", color="red", alpha=0.7)

    # Achsentitel & Skalierung linke Achse
    ax1.set_xlabel("Zeit")
    ax1.set_ylabel("kWh")
    ax1.set_title("PV-Erzeugung, Verbrauch & SOC/Strompreis (7-Tages-Ansicht)")
    ax1.legend(loc='upper left')
    ax1.grid(True)

    # ➡️ Rechte Achse hinzufügen
    ax2 = ax1.twinx()

    if plot_option == "Batterie-SOC (%)":
        # SOC in % berechnen und darstellen
        df_filtered["SOC_%"] = (df_filtered["SOC"] / batterie_kapazitaet) * 100
        ax2.plot(df_filtered["Zeit"], df_filtered["SOC_%"], label="Batterie-SOC (%)", color="green", linestyle="--", linewidth=2)
        ax2.set_ylabel("Batterie-SOC (%)", color="green")
        ax2.tick_params(axis='y', labelcolor="green")
        ax2.set_ylim(0, 100)
    else:
        # Strompreis darstellen
        ax2.plot(df_filtered["Zeit"], df_filtered["Netzpreis"], label="Strompreis (Ct/kWh)", color="purple", linestyle="--", linewidth=2)
        ax2.set_ylabel("Strompreis (Ct/kWh)", color="purple")
        ax2.tick_params(axis='y', labelcolor="purple")

    # Legende kombinieren
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc="upper right")

# 📊 Plot anzeigen
st.pyplot(fig)

# 📥 CSV-Download
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Download CSV",
    data=csv,
    file_name='simulationsergebnisse.csv',
    mime='text/csv',
)
