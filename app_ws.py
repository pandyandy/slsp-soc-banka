import streamlit as st
import json
import os
import pandas as pd
import base64
import time
import requests
import re
from datetime import date, datetime, timezone, timedelta

from PIL import Image

# Force reload the database manager to get the latest version
import importlib
import database.snowflake_manager
importlib.reload(database.snowflake_manager)
from database.snowflake_manager import get_db_manager

# ==============================
# OpenAI API konfigurácia
# ==============================
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
except KeyError:
    OPENAI_API_KEY = None  # Will be handled in the AI functions

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


mini_logo_path = os.path.join(os.path.dirname(__file__), "static", "logo_mini.png")
logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")

MINI_LOGO = Image.open(mini_logo_path)

# Load and encode logo
with open(logo_path, "rb") as f:
    logo_data = base64.b64encode(f.read()).decode()
st.set_page_config(
    page_title="Sociálna banka – Dotazník", 
    page_icon=MINI_LOGO, 
    layout="wide")

def background_color(background_color, text_color, header_text, text=None):
     content = f'<div style="font-size:20px;margin:0px 0;">{header_text}</div>'
     if text:
        content += f'<div style="font-size:16px;margin-top:5px;">{text}</div>'
     
     st.markdown(f'<div style="background-color:{background_color};color:{text_color};border-radius:0px;padding:10px;margin:0px 0;">{content}</div>', unsafe_allow_html=True)

def initialize_connection_once():
    """
    Initialize database connection and check table status (runs only once per session)
    Returns: (db_manager, connection_status, message)
    """
    # Check if already initialized in session state
    if "db_manager" in st.session_state and "connection_initialized" in st.session_state:
        return st.session_state.db_manager, True, "✅ Using cached database connection"
    
    try:
        db_manager = get_db_manager()
        
        # Test connection
        conn = db_manager.get_connection()
        if not conn:
            return None, False, "❌ Failed to connect to Snowflake workspace"
        
        # Initialize table if needed (only once)
        table_initialized = db_manager.initialize_table()
        if not table_initialized:
            return db_manager, False, "⚠️ Connected but failed to initialize SLSP_DEMO table"
        
        # Cache in session state
        st.session_state.db_manager = db_manager
        st.session_state.connection_initialized = True
        
        return db_manager, True, "✅ Connected to workspace and SLSP_DEMO table ready"
        
    except Exception as e:
        return None, False, f"❌ Connection error: {str(e)}"

def read_table_data(db_manager):
    """
    Read all data from SLSP_DEMO table using cursor and pandas
    Returns: (success, data_list, message)
    """
    try:
        # Use cursor to get data and convert to pandas DataFrame
        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT CID, DATA, PHASE, LAST_UPDATED FROM SLSP_DEMO ORDER BY CID")
            rows = cursor.fetchall()
            
            if rows:
                # Convert to pandas DataFrame
                df_snowflake = pd.DataFrame(rows, columns=['CID', 'DATA', 'PHASE', 'LAST_UPDATED'])
                
                # Convert DataFrame to list of dictionaries
                data_list = []
                for _, row in df_snowflake.iterrows():
                    try:
                        # Parse JSON data
                        json_data = json.loads(row['DATA']) if row['DATA'] else {}
                        data_list.append({
                            'CID': row['CID'],
                            'DATA': json_data,
                            'DATA_RAW': row['DATA'],
                            'PHASE': row['PHASE'],
                            'LAST_UPDATED': row['LAST_UPDATED']
                        })
                    except json.JSONDecodeError:
                        # Handle invalid JSON
                        data_list.append({
                            'CID': row['CID'],
                            'DATA': {},
                            'DATA_RAW': row['DATA'],
                            'PHASE': row['PHASE'],
                            'LAST_UPDATED': row['LAST_UPDATED']
                        })
                
                return True, data_list, f"📊 Found {len(data_list)} records in SLSP_DEMO table"
            else:
                return True, [], "📝 SLSP_DEMO table is empty"
                
    except Exception as e:
        return False, [], f"❌ Error reading table: {str(e)}"


def auto_save_data(db_manager, cid, data_to_save):
    """
    Optimized auto-save function using SnowflakeManager methods
    """
    if not cid or not cid.strip():
        return None, "CID required for auto-save"
    
    cid_value = cid.strip()
    #st.write(cid_value)
    # Check if CID already exists to determine operation type
    existing_data = db_manager.load_form_data(cid_value)
    is_update = existing_data is not None
    
    # Use the optimized save method
    success = db_manager.save_form_data(cid_value, data_to_save)
    
    if success:
        if is_update:
            return "updated", f"Auto-updated CID: {cid_value}"
        else:
            return "created", f"Auto-created CID: {cid_value}"
    else:
        return "error", f"Auto-save failed for CID: {cid_value}"


# ==============================
# AI Helper Functions
# ==============================
def call_openai_completion(prompt, temperature=1, model="gpt-5-mini-2025-08-07h", messages=None):
    """Helper function for calling OpenAI Chat Completions"""
    if not OPENAI_API_KEY:
        raise Exception("OpenAI API key not configured")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Use provided messages or create a simple user message
    if messages is None:
        messages = [{"role": "user", "content": prompt}]
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
    }
    response = requests.post(OPENAI_API_URL, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    else:
        raise Exception(f"Chyba pri volaní OpenAI API: {response.status_code}, {response.text}")


def extract_tzs_history(zivotny_pribeh, tzs_history):
    """Extract TZS history from client's story"""
    prompt = f"""Si asistent bankového poradcu v Slovenskej Sporiteľni. Tvojou úlohou je extrahovať informácie o čerpaní ŤŽS (odkladu splátok) za posledných 24 mesiacov z poskytnutého životného príbehu klienta a informácií o ŤŽS.

Na základe nasledujúceho životného príbehu klienta a informácií o ŤŽS zisti, koľkokrát klient čerpal ŤŽS (odklad splátok) za posledných 24 mesiacov. Ak nie je uvedené nič o čerpaní ŤŽS, predpokladaj, že ŤŽS nebola čerpaná. Vráť odpoveď v nasledujúcom formáte:
**Počet ŤŽS (za 24mes.)**: [číslo]
**Zdôvodnenie**: [Krátke vysvetlenie, napr. "V texte nie je zmienka o ŤŽS" alebo "Klient uviedol čerpanie odkladu splátok dvakrát v roku 2024"]

Životný príbeh:
{zivotny_pribeh}

ŤŽS história:
{tzs_history}

Analýza:"""

    result = call_openai_completion(prompt, temperature=1) #, max_tokens=500)

    # Parse TZS count from response
    tzs_count = 0
    try:
        m = re.search(r"\*\*Počet\s*ŤŽS\s*\(za\s*24mes\.\)\*\*\s*:\s*(\d+)", result, re.IGNORECASE)
        if m:
            tzs_count = int(m.group(1))
    except Exception:
        tzs_count = 0

    return tzs_count, result


def check_deferral_sufficiency(zivotny_pribeh, tzs_history, zivotne_naklady, uverove_prods):
    """Check if payment deferral is sufficient to solve the situation"""
    prompt = f"""Si asistent bankového poradcu v Slovenskej Sporiteľni. Tvojou úlohou je posúdiť, či 6-mesačný odklad splátok s predĺžením splatnosti o 6 mesiacov vyrieši klientovu finančnú situáciu na základe poskytnutých informácií. Zabráň duplicitnému započítaniu splátok úverov uvedených v cashflow a úverových produktoch.

Životný príbeh klienta:
{zivotny_pribeh}

ŤŽS história:
{tzs_history}

Náklady na život klienta:
{zivotne_naklady}

Úverové produkty:
{uverove_prods}

Na základe týchto informácií posúď, či by 6-mesačný odklad splátok s predĺžením splatnosti o 6 mesiacov vyriešil klientovu situáciu. Zohľadni, či je klientova situácia dočasná (napr. dočasná strata príjmu) a či po 6 mesiacoch bude schopný pokračovať v splácaní. Ak odklad nestačí (napr. pretrvávajúci negatívny cashflow alebo hrozba exekúcie), odporuč pokračovanie do komplexnej analýzy. V odpovedi uveď stručné zdôvodnenie.

**Dôležité**: Ak sú splátky úverov uvedené v "Náklady na život klienta" aj v "Úverové produkty", zohľadni ich iba raz, aby nedošlo k duplicitnému započítaniu. Skontroluj konzistentnosť údajov a použij sumy zo sekcie "Úverové produkty" ako primárne, ak sú tam uvedené podrobnejšie (napr. s úrokovou sadzbou alebo zostatkom). Ak sú údaje nekonzistentné, uveď to v zdôvodnení.

Odpoveď vygeneruj v slovenčine a v nasledujúcom formáte:
**Výsledok analýzy odkladu splátok**:
- Stačí odklad: [Áno/Nie]
- Zdôvodnenie: [Krátke vysvetlenie]

Analýza:"""

    return call_openai_completion(prompt, temperature=1)#, max_tokens=800)


def generate_action_plan(zivotny_pribeh, tzs_history, zivotne_naklady, uverove_prods, history=None):
    """Generate comprehensive action plan for the client"""
    if history is None:
        history = []

    # Build context from history if available
    history_context = ""
    if history:
        history_context = "\n\nPredchádzajúca konverzácia:\n"
        for msg in history:
            if msg.get("role") == "user":
                history_context += f"Používateľ: {msg.get('content', '')}\n"
            elif msg.get("role") == "assistant":
                history_context += f"Asistent: {msg.get('content', '')}\n"

    prompt = f"""CONTEXT: Sme pracovníci v banke Slovenská Sporiteľňa a máme na starosti poradenstvo pre klientov, ktorí sa dostali do ťažkej životnej situácie. Na základe ich životného príbehu, finančnej situácie a úverových produktov navrhujeme riešenie na mieru.

ROLE: Tvojou úlohou je navrhnúť riešenie pre klienta. Analýza bude stručná a jasná. Každé riešenie musí byť presne vyčíslené.

TASK: Si asistent bankového poradcu v SLSP.

1. **Overenie životnej situácie**:
   - V pár vetách popíš situáciu klienta.
   - Over, či klientova situácia spĺňa definíciu "ťažkej životnej situácie" podľa **ZOZNAMU ŤAŽKÝCH ŽIVOTNÝCH SITUÁCIÍ** (zoznam nie je konečný).
   - **Definícia ťažkej životnej situácie**: Závažná udalosť, ktorá spôsobila akútnu finančnú krízu, vedúcu k bezprostrednej hrozbe straty nehnuteľnosti (napr. dražba), exekúcii alebo iným likvidačným problémom. Klient je "unlikely to pay" (neschopný splácať záväzky bez intervencie banky), čo je preukázané negatívnym a/alebo nedostatočným cashflow po pokrytí životných nákladov a splátok.
   - **Kľúčové kritérium finančnej stability**: Klient s výrazne pozitívnym cashflow (príjmy výrazne prevyšujú výdavky vrátane splátok úverov) nespĺňa definíciu "ťažkej životnej situácie", aj keď zažil udalosť zo zoznamu, pretože je schopný splácať záväzky bez intervencie. **Ak klient žiada prevzatie úveru alebo iné opatrenia z dôvodu osobnej túžby (napr. oslobodenie inej osoby od dlhu, zlepšenie životnej úrovne, súrodenecké vyrovnanie) a nie z dôvodu bezprostrednej hrozby straty bývania alebo exekúcie, situácia nespĺňa definíciu "ťažkej životnej situácie".**
   - **Vylúčené situácie**:
     - Klienti s pozitívnym cashflow, ktorí sú schopní splácať svoje záväzky a prekonať finančné problémy bez intervencie banky (napr. dočasné zníženie príjmu, ktoré neohrozuje ich stabilitu).
     - Klienti žiadajúci pomoc na zvýšenie životnej úrovne (napr. kúpa lepšieho bývania, dovolenka, auto) alebo udržanie vysokej životnej úrovne.
     - Klienti, ktorí žiadajú prevzatie úverov alebo iné opatrenia z dôvodu osobných preferencií (napr. vyplatenie súrodenca, prepis nehnuteľnosti bez akútnej potreby) a nie z dôvodu bezprostrednej finančnej krízy.
     - Klienti neochotní prispôsobiť výdavky svojej situácii.
     - Klienti zneužívajúci situáciu na získanie výhodnejších podmienok alebo obchádzanie štandardných postupov banky.
   - Riešenie poskytni iba klientom, ktorí spĺňajú definíciu "ťažkej životnej situácie" a sú "unlikely to pay" na základe analýzy cashflow. Ak klient nespĺňa kritériá (napr. má pozitívny cashflow a je schopný splácať, alebo žiada opatrenia z dôvodu osobnej túžby), **jasne uveď, že jeho situácia nespĺňa definíciu "ťažkej životnej situácie", vysvetli prečo (napr. pozitívny cashflow, absencia bezprostrednej hrozby straty bývania), a odporuč štandardné bankové produkty (napr. refinancovanie, finančné poradenstvo) alebo alternatívne kroky (napr. právne poradenstvo pre prepis nehnuteľnosti).**

2. **Navrhni riešenie**:
   - Riešenia zober zo ZOZNAM RIESENI. Zabráň duplicitnému započítaniu splátok úverov uvedených v cashflow a úverových produktoch.
   - Uprednostni riešenia podľa ich jednoduchosti a efektivity (čím menej krokov). Ak je to možné, navrhni aj konkrétne číselné hodnoty (napr. zníženie úrokovej sadzby na 3% alebo predĺženie doby splatnosti na 10 rokov).
   - Zmeny zo ZOZNAM RIESENI vieš realizovať iba na úveroch v SLSP. Na ostatných úveroch odporuč spoluprácu s pôvodným veriteľom alebo refinancovanie do SLSP (ak má klient už stabilizovaný príjem), prípadne iné riešenie v súlade so slovenskou legislatívou.
   - Negatívny cashflow (ak by po poskytnutí riešenia vychádzal stále v mínuse) kompenzuj radami k optimalizácii príjmov a výdavkov (ak je tam priestor). Pri klientoch s príjmami blízko hranice chudoby (životného minima) navrhni riešenie viac v prospech klienta (lepšie podmienky na úveroch, výraznejšie zníženie splátky) a netlač na klienta za bežné výdavky.
   - Navrhnutým riešením zohľadni ťažku situáciu klienta, ale nie na úkor banky. Vytvor priestor na ozdravenie klienta, ale nie za každú cenu. Riešenie musí vytvárať rovnováhu medzi klientom a bankou a zohľadňovať obe strany rovnako.
   - **Špecifické pravidlo pre odklad splátok (položka k)**: Odklad splátok na 3-9 mesiacov (položka k) navrhni **iba** v akútnych situáciách, kde:
     - Klient má **negatívny cashflow** (príjmy nedokážu pokryť životné náklady a splátky) alebo **cashflow blízko nuly**, čo ohrozuje jeho schopnosť pokračovať v splácaní bez intervencie.
     - Klientova situácia je **dočasná a akútna** (napr. strata zamestnania, vážna choroba, dočasný výpadok príjmu), kde odklad splátok je nevyhnutný na preklenutie krátkodobého obdobia, aby klient mohol pokryť základné životné náklady.
     - Ak je odklad splátok súčasťou viacerých opatrení, najprv prepočítaj vplyv všetkcýh ostatných opatrení na cashflow, zisti či je stále negatívny a až na základe toho použi aj tento nástroj. Ak ostatné opatrenia cashflow "opravia" na pozitívny, odklad už neaplikuj.
     - **Nevhodné situácie pre odklad splátok**: Ak má klient pozitívny cashflow (príjmy prevyšujú výdavky vrátane splátok), alebo tak bude po aplikovaní ostatných opatrení, alebo jeho situácia nie je akútna (napr. chce si „oddýchnuť" alebo zlepšiť životnú úroveň, ale nie je v bezprostrednom riziku nesplácania), odklad splátok **nenavrhuj**. Namiesto toho uprednostni iné riešenia, ako zníženie úrokovej sadzby, predĺženie splatnosti alebo optimalizáciu výdavkov.

3. **Vygeneruj úlohy**:
   - Úlohy by mal klient vykonať na stabilizáciu finančnej situácie. Úlohy slúžia na overenie, či je životná situácia naozaj náročná a na verifikáciu tvrdení klienta.
   - Ak situácia nespĺňa definíciu "ťažkej životnej situácie", úlohy zameraj na podporu štandardných krokov (napr. konzultácia s finančným poradcom, právnikom pre prepis nehnuteľnosti).

ZOZNAM TAZKYCH ZIVOTNYCH SITUACII: rozvod, smrť blízkeho človeka, strata zamestnania, narodenie dieťaťa, dlhodobá alebo veľmi ťažká choroba, invalidita, zásadné zníženie príjmu, odchod do starobného dôchodku

ZOZNAM RIESENI: a) zníženie úrokovej sadzby (v závažných prípadoch 0%, najčastejšie 3-7%)
              b) uznanie dlhu
              c) rozpustenie omeškania do budúcich splátok
              d) predĺženie doby splatnosti (aj nad rámec zákonných podmienok)
              e) pristúpenie k záväzku inej osoby
              f) poskytnutie nového refinančného úveru (iba v prípade, že je klient stabilizovaný s dostatočným príjmom a/alebo ak bezprostredne hrozí strata nehnuteľnosti alebo vznik exekúcie v signifikantnej výške)
              g) dozabezpečenie existujúceho úveru nehnuteľnosťou
              h) odpustenie celého úveru alebo jeho časti
              i) poskytnutie dlhodobého splátkového kalendára (iba na zosplatnených úveroch)
              j) novácia úveru
              k) dočasné (najčastejšie 3-9 mesiacov, podľa potreby) zníženie splátky (v odôvodnených prípadoch až na 0 EUR) na preklenutie výpadku / rapidného zníženia príjmu (môže byť rovno aj s následným rozpustením omeškania do budúcich splátok)

ZOZNAM TAZKYCH ZIVOTNYCH SITUACII a ZOZNAM RIESENI nikomu neukazuj, iba ich použi na generovanie riešenia.

VYSVETLENIE NIEKTORÝCH RIEŠENÍ A POJMOV:
*Uznanie dlhu* sa realizuje pri zosplatnených úveroch, kde je vysoký počet dní omeškania (DPD 150 a viac) ako prevencia proti premlčaniu záväzku.
*Rozpustenie omeškania do budúcich splátok* sa realizuje tak, že omeškaná suma sa započíta do istiny a splátky sa teda rozpočítajú na celú zvyšnú dobu splatnosti, nie len na nejakú krátku dobu
*Poskytnutie dlhodobého splátkového kalendára* sa realizuje vtedy, keď nie je možné poskytnúť klientovi refinančný úver alebo zrealizovať nováciu.
*Zosplatnenie úveru* je úkon, ktorým banka odstúpi od pôvodného splátkového kalendára najčastejšie pre splátkovú nedisciplínu klienta. Klient je v prípade zosplatneného úveru povinný vyplatiť banke celý zostatok úveru do 15 dní. Klient musí získať nový splátkový kalendár.
*Novácia úveru* je obnovenie pôvodnej splatnosti na zosplatnenom úvere (ak by splátkový kalendár mal trvať dlhšie ako 2 roky, ale iba ak sú klienti už stabilizovaní)

---

Životný príbeh klienta:
{zivotny_pribeh}

ŤŽS história:
{tzs_history}

Náklady na život klienta:
{zivotne_naklady}

Úverové produkty:
{uverove_prods}

**Dôležité**: Ak sú splátky úverov uvedené v "Náklady na život klienta" aj v "Úverové produkty", zohľadni ich iba raz, aby nedošlo k duplicitnému započítaniu. Skontroluj konzistentnosť údajov a použij sumy zo sekcie "Úverové produkty" ako primárne, ak sú tam uvedené podrobnejšie (napr. s úrokovou sadzbou alebo zostatkom). Ak sú údaje nekonzistentné, uveď to v analýze a odporuč kroky na overenie údajov klientom.

{history_context}

Na základe týchto informácií navrhni riešenie na mieru pre klienta.

Analýza a návrh riešenia:"""

    return call_openai_completion(prompt, temperature=1)


def generate_follow_up_response(follow_up_input, zivotny_pribeh, tzs_history, zivotne_naklady, uverove_prods, history=None):
    """Generate follow-up response for additional questions"""
    if history is None:
        history = []
    
    # Build conversation messages for chat completions
    messages = []
    
    # Add system message with context
    system_message = """Si asistent bankového poradcu v Slovenskej Sporiteľni. Odpovedáš na doplňujúce otázky k už vygenerovanému akčnému plánu pre klienta v ťažkej životnej situácii. Buď stručný a praktický v odpovediach."""
    messages.append({"role": "system", "content": system_message})
    
    # Add conversation history
    for msg in history:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    
    # Add current follow-up question with context
    context_prompt = f"""Kontext klienta:
Životný príbeh: {zivotny_pribeh}
ŤŽS história: {tzs_history}
Náklady na život: {zivotne_naklady}
Úverové produkty: {uverove_prods}

Doplňujúca otázka: {follow_up_input}

Odpovedz na otázku v kontexte klientovej situácie."""
    
    messages.append({"role": "user", "content": context_prompt})
    
    return call_openai_completion("", temperature=1, messages=messages)


def format_form_data_for_ai(data_to_save):
    """Format form data for AI analysis"""
    # Extract key information for AI analysis
    zivotny_pribeh = f"{data_to_save.get('pribeh', '')}\n\nRiešenie podľa klienta: {data_to_save.get('riesenie', '')}"
    
    # Format household information
    domacnost_info = f"""
    Počet členov domácnosti: {data_to_save.get('pocet_clenov_domacnosti', 0)}
    Typ bydliska: {', '.join(data_to_save.get('typ_bydliska', []))}
    Poznámky k domácnosti: {data_to_save.get('domacnost_poznamky', '')}
    """
    
    # Format income data
    prijmy_data = data_to_save.get('prijmy_domacnosti', [])
    prijmy_text = "Príjmy domácnosti:\n"
    if prijmy_data:
        for prijem in prijmy_data:
            prijmy_text += f"- {prijem.get('Kto:', 'N/A')}: TPP/Brigáda: {prijem.get('Čistý mesačný príjem (TPP, brigáda)', 0)}€, Podnikanie: {prijem.get('Čistý mesačný príjem z podnikania', 0)}€, Sociálne dávky: {prijem.get('Sociálne dávky (PN, dôchodok, rodičovský príspevok)', 0)}€, Iné: {prijem.get('Iné (výživné, podpora od rodiny)', 0)}€\n"
    else:
        prijmy_text += "Žiadne príjmy nie sú evidované.\n"
    prijmy_text += f"Poznámky k príjmom: {data_to_save.get('poznamky_prijmy', '')}"
    
    # Format expenses
    vydavky_text = f"""
    Výdavky domácnosti:
    - Bývanie: Nájom: {data_to_save.get('najom', 0)}€, Elektrina: {data_to_save.get('elektrina', 0)}€, Plyn: {data_to_save.get('plyn', 0)}€, Voda: {data_to_save.get('voda', 0)}€, Kúrenie: {data_to_save.get('kurenie', 0)}€, Domácnosť: {data_to_save.get('domacnost', 0)}€, Iné náklady na bývanie: {data_to_save.get('ine_naklady_byvanie', 0)}€
    - Rodina: Strava: {data_to_save.get('strava_potraviny', 0)}€, Oblečenie: {data_to_save.get('oblecenie_obuv', 0)}€, Hygiena: {data_to_save.get('hygiena_kozmetika_drogeria', 0)}€, Lieky: {data_to_save.get('lieky_zdravie', 0)}€, Výdavky na deti: {data_to_save.get('vydavky_na_deti', 0)}€, Výživné: {data_to_save.get('vyzivne', 0)}€, Podpora rodičov: {data_to_save.get('podpora_rodicov', 0)}€, Domáce zvieratá: {data_to_save.get('domace_zvierata', 0)}€
    - Komunikácia: TV+Internet: {data_to_save.get('tv_internet', 0)}€, Telefón: {data_to_save.get('telefon', 0)}€, Volný čas: {data_to_save.get('volny_cas', 0)}€, Predplatné: {data_to_save.get('predplatne', 0)}€, Alkohol/lotéria: {data_to_save.get('alkohol_loteria_zreby', 0)}€, Cigarety: {data_to_save.get('cigarety', 0)}€
    - Doprava: MHD: {data_to_save.get('mhd_autobus_vlak', 0)}€, Auto pohonné hmoty: {data_to_save.get('auto_pohonne_hmoty', 0)}€, Auto servis: {data_to_save.get('auto_servis_pzp_dialnicne_poplatky', 0)}€
    - Financie: Sporenie: {data_to_save.get('sporenie', 0)}€, Odvody: {data_to_save.get('odvody', 0)}€, Poistky: {data_to_save.get('poistky', 0)}€, Splátky úverov: {data_to_save.get('splatky_uverov', 0)}€
    - Ostatné: {data_to_save.get('ine', 0)}€
    Poznámky k výdavkom: {data_to_save.get('poznamky_vydavky', '')}
    """
    
    # Format debts information
    uvery_data = data_to_save.get('uvery_df', [])
    uvery_text = "Úvery a pôžičky:\n"
    if uvery_data:
        for uver in uvery_data:
            uvery_text += f"- {uver.get('Kde som si požičal?', 'N/A')}: Účel: {uver.get('Na aký účel?', 'N/A')}, Požičané: {uver.get('Koľko som si požičal?', 0)}€, Zostatok: {uver.get('Koľko ešte dlžím?', 0)}€, Mesačná splátka: {uver.get('Akú mám mesačnú splátku?', 0)}€, Úroková sadzba: {uver.get('Úroková sadzba?', 0)}%\n"
    else:
        uvery_text += "Žiadne úvery nie sú evidované.\n"
    
    exekucie_data = data_to_save.get('exekucie_df', [])
    exekucie_text = "Exekúcie:\n"
    if exekucie_data:
        for exekucia in exekucie_data:
            exekucie_text += f"- Exekútor: {exekucia.get('Meno exekútora', 'N/A')}, Pre koho: {exekucia.get('Pre koho exekútor vymáha dlh?', 'N/A')}, Výška: {exekucia.get('Aktuálna výška exekúcie?', 0)}€, Mesačná splátka: {exekucia.get('Akou sumou ju mesačne splácam?', 0)}€\n"
    else:
        exekucie_text += "Žiadne exekúcie nie sú evidované.\n"
    
    nedoplatky_data = data_to_save.get('nedoplatky_data', [])
    nedoplatky_text = "Nedoplatky:\n"
    if nedoplatky_data:
        for nedoplatok in nedoplatky_data:
            nedoplatky_text += f"- {nedoplatok.get('Kde mám nedoplatok?', 'N/A')}: Výška: {nedoplatok.get('V akej výške mám nedoplatok?', 0)}€, Mesačná splátka: {nedoplatok.get('Akou sumou ho mesačne splácam?', 0)}€\n"
    else:
        nedoplatky_text += "Žiadne nedoplatky nie sú evidované.\n"
    
    dlhy_text = f"{uvery_text}\n{exekucie_text}\n{nedoplatky_text}\nPoznámky k dlhom: {data_to_save.get('poznamky_dlhy', '')}"
    
    return zivotny_pribeh, domacnost_info, prijmy_text, vydavky_text, dlhy_text



def main():
    st.markdown(f"""
        <div style="
            background-color: #2870ed; 
            padding: 20px; 
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        ">
            <div>
                <div style="color: white; font-size: 32px; font-weight: bold;">
                    Sociálna banka – Dotazník
                </div>
            </div>
            <div>
                <img src="data:image/png;base64,{logo_data}" style="height: 60px;" />
            </div>
        </div>
        """, unsafe_allow_html=True)
    # Initialize database connection and read data only when needed
    db_manager = None
    conn_status = False
    conn_message = ""
    
    # Show existing data if available
   # if table_data:
    #    st.write(table_data)
        #col_expander, col_refresh = st.columns([4, 1])
        #with col_expander:
            #show_records = st.checkbox(f"📋 View Existing Records ({len(table_data)} found)", value=False)
       # with col_refresh:
        #    st.write("")  # Space for alignment
         #   if st.button("🔄 Refresh"):
                # Clear cache to force refresh
          #      for key in ["table_data", "table_data_loaded", "table_read_message"]:
           #         if key in st.session_state:
            #            del st.session_state[key]
             #   st.rerun()
        
        #if show_records:
         #   for i, record in enumerate(table_data):
          #      st.write(f"**Record {i+1}: CID = {record['CID']}**")
           #     st.write("**Data:**")
            #    st.json(record['DATA'])
             #   st.markdown("---")
    
    with st.sidebar:

        st.header("Vyhľadať CID")


        # CID input and lookup section
        cid = st.text_input(
            "CID", 
            placeholder="Zadajte CID klienta",
            label_visibility="collapsed",
            )
        lookup_clicked = st.button(
            "Vyhľadať",
            type="primary",
            #disabled=not cid.strip(), 
            use_container_width=True)
        
        # Display CID lookup status in sidebar
        if st.session_state.get("cid_checked", False) and st.session_state.get("current_cid"):
            st.markdown("---")
            #st.write(st.session_state.cid_exists)
            if st.session_state.get("cid_exists", False):
                st.sidebar.success("Formulár nájdený")
            else:
                st.sidebar.info("Nový formulár bude vytvorený")
    
    # Initialize session state for CID lookup
    if "cid_checked" not in st.session_state:
        st.session_state.cid_checked = False
    if "cid_exists" not in st.session_state:
        st.session_state.cid_exists = False
    if "existing_data" not in st.session_state:
        st.session_state.existing_data = {}
    if "current_cid" not in st.session_state:
        st.session_state.current_cid = ""
    
    # Handle CID lookup
    if lookup_clicked and cid.strip():
        # Initialize database connection only when user clicks "Vyhľadať"
        if "db_manager" not in st.session_state:
            db_manager, conn_status, conn_message = initialize_connection_once()
        else:
            db_manager, conn_status, conn_message = initialize_connection_once()
        
        # Check if connection was successful
        if not db_manager:
            st.error("❌ Failed to connect to database. Please try again.")
            st.stop()
        
        # Use the optimized database manager method to get data with metadata
        existing_data = db_manager.load_form_data(cid.strip())
        
        if existing_data:
            cid_exists = True
            # Remove metadata from form data before storing in session
            form_data = {k: v for k, v in existing_data.items() if not k.startswith('_')}
            message = f"✅ CID '{cid}' found in database"
        else:
            cid_exists = False
            form_data = {}
            message = f"📝 No record found for CID '{cid}'. A new form will be created."
        
        st.session_state.cid_checked = True
        st.session_state.cid_exists = cid_exists
        st.session_state.existing_data = form_data
        st.session_state.current_cid = cid.strip()
        st.session_state.last_updated_info = existing_data.get('_last_updated', None) if existing_data else None
        st.session_state.needs_fix = False  # Reset fix flag on successful load
        
        # Reset income data to force reload from database on next form render
        if 'prijmy_domacnosti' in st.session_state:
            del st.session_state.prijmy_domacnosti
        
        # Display lookup result immediately
        if cid_exists is True:
            st.sidebar.markdown("---")
            st.sidebar.success(f"Formulár nájdený")
        elif cid_exists is False:
            st.sidebar.markdown("---")
            st.sidebar.info(f"Nový formulár bude vytvorený")
        
        # Show last updated info immediately when CID is found
        if st.session_state.get('last_updated_info'):
            try:
                # Parse UTC time
                last_updated = datetime.fromisoformat(st.session_state.last_updated_info.replace('Z', '+00:00'))
                
                # Convert to CET (UTC+1)
                cet = timezone(timedelta(hours=1))
                last_updated_cet = last_updated.astimezone(cet)
                
                st.sidebar.info(f"🕒 Formulár bol naposledy upravený: {last_updated_cet.strftime('%d.%m.%Y o %H:%M')} CET")
            except:
                st.sidebar.finfo(f"🕒 Formulár bol naposledy upravený: {st.session_state.last_updated_info}")
    
    # Reset if CID changed
    if cid.strip() != st.session_state.current_cid:
        st.session_state.cid_checked = False
        st.session_state.needs_fix = False  # Reset fix flag when CID changes
    
    # Show data entry form only after CID is checked and database is connected
    if st.session_state.cid_checked and cid.strip() and "db_manager" in st.session_state:
        # Add fix button for corrupted data
        if st.session_state.get('needs_fix', False):
            st.markdown("---")
            st.warning("⚠️ This CID has corrupted data that needs fixing.")
            
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("🔧 Fix This CID", type="primary"):
                    #with st.spinner("Fixing corrupted data..."):
                    db_manager = st.session_state.get("db_manager")
                    if db_manager:
                        success = db_manager.fix_corrupted_record(cid.strip())
                        if success:
                            st.success("✅ CID fixed successfully! Please refresh the page.")
                            st.rerun()
                        else:
                            st.error("❌ Failed to fix CID. Please contact support.")
                    else:
                        st.error("❌ Database not connected. Please try searching again.")
            
            with col2:
                if st.button("🔄 Refresh Page"):
                    st.rerun()
            
            with col3:
                st.info("💡 The fix will clean up quotes, newlines, and other problematic characters.")
        
        #st.markdown("---")
        # Pre-fill values if existing data found
        default_meno_priezvisko = st.session_state.existing_data.get("meno_priezvisko", "")
        default_datum_narodenia = st.session_state.existing_data.get("datum_narodenia", date(1900, 1, 1))
        default_sap_id = st.session_state.existing_data.get("sap_id", "")
        default_email_zamestnanca = st.session_state.existing_data.get("email_zamestnanca", "@slsp.sk")

        default_pribeh = st.session_state.existing_data.get("pribeh", "")
        default_riesenie = st.session_state.existing_data.get("riesenie", "")
        default_pocet_clenov_domacnosti = st.session_state.existing_data.get("pocet_clenov_domacnosti", 0)
        default_typ_bydliska = st.session_state.existing_data.get("typ_bydliska", [])
        default_domacnost_poznamky = st.session_state.existing_data.get("domacnost_poznamky", "")
        default_najom = st.session_state.existing_data.get("najom", 0.0)
        default_tv_internet = st.session_state.existing_data.get("tv_internet", 0.0)
        default_oblecenie_obuv = st.session_state.existing_data.get("oblecenie_obuv", 0.0)
        default_sporenie = st.session_state.existing_data.get("sporenie", 0.0)
        default_elektrina = st.session_state.existing_data.get("elektrina", 0.0)
        default_lieky_zdravie = st.session_state.existing_data.get("lieky_zdravie", 0.0)
        default_vydavky_na_deti = st.session_state.existing_data.get("vydavky_na_deti", 0.0)
        default_vyzivne = st.session_state.existing_data.get("vyzivne", 0.0)
        default_voda = st.session_state.existing_data.get("voda", 0.0)
        default_hygiena_kozmetika_drogeria = st.session_state.existing_data.get("hygiena_kozmetika_drogeria", 0.0)
        default_domace_zvierata = st.session_state.existing_data.get("domace_zvierata", 0.0)
        default_podpora_rodicov = st.session_state.existing_data.get("podpora_rodicov", 0.0)
        default_plyn = st.session_state.existing_data.get("plyn", 0.0)
        default_strava_potraviny = st.session_state.existing_data.get("strava_potraviny", 0.0)
        default_predplatne = st.session_state.existing_data.get("predplatne", 0.0)
        default_odvody = st.session_state.existing_data.get("odvody", 0.0)
        default_poistky = st.session_state.existing_data.get("poistky", 0.0)
        default_splatky_uverov = st.session_state.existing_data.get("splatky_uverov", 0.0)
        default_domacnost = st.session_state.existing_data.get("domacnost", 0.0)
        default_kurenie = st.session_state.existing_data.get("kurenie", 0.0)
        default_mhd_autobus_vlak = st.session_state.existing_data.get("mhd_autobus_vlak", 0.0)
        default_cigarety = st.session_state.existing_data.get("cigarety", 0.0)
        default_ine = st.session_state.existing_data.get("ine", 0.0)
        default_ine_naklady_byvanie = st.session_state.existing_data.get("ine_naklady_byvanie", 0.0)
        default_auto_pohonne_hmoty = st.session_state.existing_data.get("auto_pohonne_hmoty", 0.0)
        default_alkohol_loteria_zreby = st.session_state.existing_data.get("alkohol_loteria_zreby", 0.0)
        default_telefon = st.session_state.existing_data.get("telefon", 0.0)
        default_auto_servis_pzp_dialnicne_poplatky = st.session_state.existing_data.get("auto_servis_pzp_dialnicne_poplatky", 0.0)
        default_volny_cas = st.session_state.existing_data.get("volny_cas", 0.0)
        default_poznamky_vydavky = st.session_state.existing_data.get("poznamky_vydavky", "")
        default_komentar_pracovnika_slsp = st.session_state.existing_data.get("komentar_pracovnika_slsp", "")

        default_poznamky_prijmy = st.session_state.existing_data.get("poznamky_prijmy", "")
        default_prijmy_domacnosti = st.session_state.existing_data.get("prijmy_domacnosti", [])
        default_uvery_domacnosti = st.session_state.existing_data.get("uvery_df", [])
        default_exekucie_domacnosti = st.session_state.existing_data.get("exekucie_df", [])
        default_nedoplatky_data = st.session_state.existing_data.get("nedoplatky_data", [])

        default_poznamky_dlhy = st.session_state.existing_data.get("poznamky_dlhy", "")
                
        # Employee information section
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write("SAP ID zamestnanca:")
            sap_id = st.text_input(
                "SAP ID zamestnanca:",
                value=default_sap_id,
                label_visibility="collapsed",
            )
        
        with col2:
            st.write("E-mail zamestnanca:")
            # Initialize email with @slsp.sk if not set
            if "email_zamestnanca" not in st.session_state or not st.session_state.email_zamestnanca:
                st.session_state.email_zamestnanca = "@slsp.sk"
            
            email_zamestnanca = st.text_input(
                "E-mail zamestnanca:",
                value=default_email_zamestnanca,
                help="E-mail musí končiť doménou @slsp.sk",
                label_visibility="collapsed",
            )
            if email_zamestnanca and not email_zamestnanca.endswith("@slsp.sk"):
                st.warning("E-mail musí končiť doménou @slsp.sk", icon="⚠️")
        
        with col3:
            st.write("Dnešný dátum:")
            dnesny_datum = st.date_input(
                "Dnešný dátum:", 
                value="today",
                format="DD.MM.YYYY",
                label_visibility="collapsed",
            )
        col1, col2 = st.columns(2)
        with col1:
            st.write("Meno a priezvisko klienta:")
            meno_priezvisko = st.text_input(
                "Meno a priezvisko klienta:",
                value=default_meno_priezvisko,
                label_visibility="collapsed",
            )

        with col2:
            st.write("Dátum narodenia:")
            datum_narodenia = st.date_input(
                "Dátum narodenia:",
                min_value=date(1900, 1, 1),
                max_value="today",
                format="DD.MM.YYYY",
                value=default_datum_narodenia,
                label_visibility="collapsed",
            )
        ""
        background_color(
            background_color="#2870ed", 
            text_color="#ffffff", 
            header_text="1. Životná situácia",
            #header_text="1. Príbeh klienta", 
            #text="Ako ste sa dostali do finančných problémov? Čo sa zmenilo vo vašom živote? Situácia stále trvá alebo už je vyriešená?"
        )
        with st.container(border=True):
            st.markdown("#### Príbeh klienta")
            st.markdown("Ako ste sa dostali do finančných problémov? Čo sa zmenilo vo vašom živote? Situácia stále trvá alebo už je vyriešená?")
            pribeh = st.text_area(
                "Príbeh klienta",
                value=default_pribeh,
                label_visibility="collapsed",
                height=150,
                key="pribeh_textarea"
            )
       # background_color(
        #    background_color="#2870ed",
         #   text_color="#ffffff", 
          #  header_text="2. Riešenie podľa klienta", 
         #   text="Ako by ste chceli riešiť Vašu finančnú situáciu? Ako Vám môžeme pomôcť my? Koľko by ste vedeli mesačne splácať?"
        #)
        #with st.container(border=True):
            st.markdown("#### Riešenie podľa klienta")
            st.markdown("Ako by ste chceli riešiť Vašu finančnú situáciu? Ako Vám môžeme pomôcť my? Koľko by ste vedeli mesačne splácať?")
            riesenie = st.text_area(
                "Riešenie podľa klienta",
                value=default_riesenie,
                label_visibility="collapsed",
                height=150,
                key="riesenie_textarea"
            )

        background_color(
            background_color="#2870ed", 
            text_color="#ffffff", 
            header_text="2. Domácnosť", 
        )
        with st.container(border=True):
            col1, col2 = st.columns([0.4, 0.6])
            with col1:
                st.write("Počet členov domácnosti:")
                pocet_clenov_domacnosti = st.number_input(
                    "Počet členov domácnosti:",
                    min_value=0,
                    value=default_pocet_clenov_domacnosti,
                    step=1,
                    width=120,
                    label_visibility="collapsed",
                )
            with col2:
                st.write("Typ bydliska:")
                typ_bydliska = st.multiselect(
                    "Typ bydliska:",
                    options=["Byt", "Rodinný dom", "Dvojgeneračná domácnosť", "Nájom", "Ve vlastníctve"],
                    default=default_typ_bydliska,
                    placeholder="Vyberte typ bydliska",
                    label_visibility="collapsed",
                )

            domacnost_poznamky = st.text_area(
                "Poznámky:", 
                value=default_domacnost_poznamky,
                height=75
            )


                    # Create initial dataframe with the specified columns
            column_names = {
                "kto": "Kto:",
                "tpp_brigada": "Čistý mesačný príjem (TPP, brigáda)",
                "podnikanie": "Čistý mesačný príjem z podnikania", 
                "socialne_davky": "Sociálne dávky (PN, dôchodok, rodičovský príspevok)",
                "ine": "Iné (výživné, podpora od rodiny)"
            }

                    # Initialize prijmy storage in session state
            if "prijmy_domacnosti" not in st.session_state:
                # Check if we have existing data to load
                if default_prijmy_domacnosti:
                    # Load existing income data from database
                    try:
                        loaded_df = pd.DataFrame(default_prijmy_domacnosti)
                        # Ensure all required columns exist
                        required_columns = {
                            "Vybrať": "bool",
                            "ID": "string",
                            column_names["kto"]: "string",
                            column_names["tpp_brigada"]: "int",
                            column_names["podnikanie"]: "int",
                            column_names["socialne_davky"]: "int",
                            column_names["ine"]: "int",
                        }
                        
                        for col, dtype in required_columns.items():
                            if col not in loaded_df.columns:
                                if dtype == "bool":
                                    loaded_df[col] = False
                                elif dtype == "string":
                                    loaded_df[col] = ""
                                elif dtype == "int":
                                    loaded_df[col] = 0
                        
                        # Reorder columns to match expected order
                        column_order = ["Vybrať", "ID", column_names["kto"], column_names["tpp_brigada"], 
                                    column_names["podnikanie"], column_names["socialne_davky"], column_names["ine"]]
                        st.session_state.prijmy_domacnosti = loaded_df.reindex(columns=column_order, fill_value="")
                    except Exception as e:
                        # If loading fails, create empty dataframe
                        st.session_state.prijmy_domacnosti = pd.DataFrame({
                            "Vybrať": pd.Series(dtype="bool"),
                            "ID": pd.Series(dtype="string"),
                            column_names["kto"]: pd.Series(dtype="string"),
                            column_names["tpp_brigada"]: pd.Series(dtype="float"),
                            column_names["podnikanie"]: pd.Series(dtype="float"),
                            column_names["socialne_davky"]: pd.Series(dtype="float"),
                            column_names["ine"]: pd.Series(dtype="float"),
                        })
                else:
                    # Create empty dataframe for new records
                    st.session_state.prijmy_domacnosti = pd.DataFrame({
                        "Vybrať": pd.Series(dtype="bool"),
                        "ID": pd.Series(dtype="string"),
                        column_names["kto"]: pd.Series(dtype="string"),
                        column_names["tpp_brigada"]: pd.Series(dtype="float"),
                        column_names["podnikanie"]: pd.Series(dtype="float"),
                        column_names["socialne_davky"]: pd.Series(dtype="float"),
                        column_names["ine"]: pd.Series(dtype="float"),
                    })

            # Ensure selection column exists for older sessions
            if "Vybrať" not in st.session_state.prijmy_domacnosti.columns:
                st.session_state.prijmy_domacnosti.insert(0, "Vybrať", False)

            # Migrate old data to include ID column
            if "ID" not in st.session_state.prijmy_domacnosti.columns:
                st.session_state.prijmy_domacnosti.insert(1, "ID", "")
                # Generate IDs for existing entries
                for i in range(len(st.session_state.prijmy_domacnosti)):
                    if pd.isna(st.session_state.prijmy_domacnosti.iloc[i]["ID"]) or st.session_state.prijmy_domacnosti.iloc[i]["ID"] == "":
                        st.session_state.prijmy_domacnosti.iloc[i, st.session_state.prijmy_domacnosti.columns.get_loc("ID")] = f"PR{int(time.time()*1000) + i}"

            # Initialize prijmy ID counter if not exists
            if "prijmy_id_counter" not in st.session_state:
                st.session_state.prijmy_id_counter = 1

            initial_data = pd.DataFrame({
                column_names["kto"]: [""],
                column_names["tpp_brigada"]: [0.0], 
                column_names["podnikanie"]: [0.0],
                column_names["socialne_davky"]: [0.0],
                column_names["ine"]: [0.0]
            })

            def _generate_prijmy_id() -> str:
                """Generate a unique ID for income entries"""
                timestamp = int(time.time() * 1000)  # milliseconds since epoch
                counter = st.session_state.prijmy_id_counter
                st.session_state.prijmy_id_counter += 1
                return f"PR{timestamp}{counter:03d}"

            def update_prijmy():
                """Callback function to handle data editor changes and preserve data during reruns"""
                # This function is called when the data editor changes
                # Store the edited data in a separate session state key to prevent loss
                if "prijmy_data" in st.session_state:
                    edited_data = st.session_state["prijmy_data"]
                    if isinstance(edited_data, pd.DataFrame):
                        # Store the edited data in a separate key for persistence
                        # Note: We don't update st.session_state.prijmy_domacnosti here as it causes
                        # the data editor issue described in the Streamlit discussion
                        st.session_state["prijmy_edited_data"] = edited_data.copy()

            def _get_prijmy_data_for_save():
                """Get the most up-to-date prijmy data for saving to database"""
                # If main dataframe is empty, always return empty list (don't use cached data)
                if st.session_state.prijmy_domacnosti.empty:
                    return []
                
                # First try to get edited data, then fall back to main dataframe
                if "prijmy_edited_data" in st.session_state and st.session_state["prijmy_edited_data"] is not None:
                    edited_data = st.session_state["prijmy_edited_data"]
                    if isinstance(edited_data, pd.DataFrame) and not edited_data.empty:
                        # Add ID column back to edited data for saving
                        if "ID" in st.session_state.prijmy_domacnosti.columns:
                            edited_with_id = edited_data.copy()
                            edited_with_id.insert(1, "ID", st.session_state.prijmy_domacnosti["ID"])
                            return edited_with_id.to_dict('records')
                        else:
                            return edited_data.to_dict('records')
                
                # Fall back to main dataframe
                return st.session_state.prijmy_domacnosti.to_dict('records')

            def _get_exekucie_data_for_save():
                """Get the most up-to-date exekucie data for saving to database"""
                # If main dataframe is empty, always return empty list (don't use cached data)
                if st.session_state.exekucie_df.empty:
                    return []
                
                # First try to get edited data, then fall back to main dataframe
                if "exekucie_edited_data" in st.session_state and st.session_state["exekucie_edited_data"] is not None:
                    edited_data = st.session_state["exekucie_edited_data"]
                    if isinstance(edited_data, pd.DataFrame) and not edited_data.empty:
                        # Add ID column back to edited data for saving
                        if "ID" in st.session_state.exekucie_df.columns:
                            edited_with_id = edited_data.copy()
                            edited_with_id.insert(1, "ID", st.session_state.exekucie_df["ID"])
                            return edited_with_id.to_dict('records')
                        else:
                            return edited_data.to_dict('records')
                
                # Fall back to main dataframe
                return st.session_state.exekucie_df.to_dict('records')

            def _get_nedoplatky_data_for_save():
                """Get the most up-to-date nedoplatky data for saving to database"""
                # If main dataframe is empty, always return empty list (don't use cached data)
                if st.session_state.nedoplatky_data.empty:
                    return []
                
                # First try to get edited data, then fall back to main dataframe
                if "nedoplatky_edited_data" in st.session_state and st.session_state["nedoplatky_edited_data"] is not None:
                    edited_data = st.session_state["nedoplatky_edited_data"]
                    if isinstance(edited_data, pd.DataFrame) and not edited_data.empty:
                        # Add ID column back to edited data for saving
                        if "ID" in st.session_state.nedoplatky_data.columns:
                            edited_with_id = edited_data.copy()
                            edited_with_id.insert(1, "ID", st.session_state.nedoplatky_data["ID"])
                            return edited_with_id.to_dict('records')
                        else:
                            return edited_data.to_dict('records')
                
                # Fall back to main dataframe
                return st.session_state.nedoplatky_data.to_dict('records')

            def add_new_prijem():
                """Add a new income row to the dataframe"""
                # First, save any current edits from the data editor to prevent data loss
                # Use the stored edited data if available, otherwise use the current widget data
                edited_data = None
                if "prijmy_edited_data" in st.session_state:
                    edited_data = st.session_state["prijmy_edited_data"]
                elif "prijmy_data" in st.session_state:
                    edited_data = st.session_state["prijmy_data"]
                
                if edited_data is not None and isinstance(edited_data, pd.DataFrame):
                    # Merge the edited data with the main dataframe, preserving IDs
                    if "ID" in st.session_state.prijmy_domacnosti.columns:
                        edited_data_with_id = edited_data.copy()
                        edited_data_with_id.insert(1, "ID", st.session_state.prijmy_domacnosti["ID"])
                        st.session_state.prijmy_domacnosti = edited_data_with_id
                    else:
                        st.session_state.prijmy_domacnosti = edited_data
                
                new_id = _generate_prijmy_id()
                new_row = {
                    "Vybrať": False,
                    "ID": new_id,
                    column_names["kto"]: "",
                    column_names["tpp_brigada"]: 0,
                    column_names["podnikanie"]: 0,
                    column_names["socialne_davky"]: 0,
                    column_names["ine"]: 0,
                }
                
                # Add to dataframe
                new_df = pd.DataFrame([new_row])
                st.session_state.prijmy_domacnosti = pd.concat([st.session_state.prijmy_domacnosti, new_df], ignore_index=True)

            # Removed edit_prijmy_dialog function - now using inline editing


            #background_color(
            #    background_color="#2870ed", 
            #    text_color="#ffffff", 
            #    header_text="Príjmy a výdavky domácnosti", 
            #)

            #with st.container(border=True):
                # Controls: add / delete selected
            st.markdown("<hr style='border: 1px solid #2870ed'>", unsafe_allow_html=True)
            
            st.markdown("#### Príjmy domácnosti")
            ctrl_pr1, ctrl_pr2 = st.columns([1, 1], vertical_alignment="bottom")
            
            # Add income button
            with ctrl_pr1:
                if st.button("➕ Pridať príjem", use_container_width=True, key="add_prijmy_btn"):
                    add_new_prijem()
                    st.rerun()
            
            # Delete income button  
            with ctrl_pr2:
                if st.button("🗑️ Zmazať vybraný", use_container_width=True, key="delete_prijmy_btn"):
                    # First, save any current edits from the data editor to prevent data loss
                    edited_data = None
                    if "prijmy_edited_data" in st.session_state:
                        edited_data = st.session_state["prijmy_edited_data"]
                    elif "prijmy_data" in st.session_state:
                        edited_data = st.session_state["prijmy_data"]
                    
                    if edited_data is not None and isinstance(edited_data, pd.DataFrame):
                        # Merge the edited data with the main dataframe, preserving IDs
                        if "ID" in st.session_state.prijmy_domacnosti.columns:
                            edited_data_with_id = edited_data.copy()
                            edited_data_with_id.insert(1, "ID", st.session_state.prijmy_domacnosti["ID"])
                            st.session_state.prijmy_domacnosti = edited_data_with_id
                        else:
                            st.session_state.prijmy_domacnosti = edited_data
                    
                    df = st.session_state.prijmy_domacnosti
                    # Find selected rows
                    if "Vybrať" in df.columns:
                        selected_idxs = df.index[df["Vybrať"] == True].tolist()
                        if len(selected_idxs) == 0:
                            st.warning("⚠️ Označte jeden riadok v tabuľke na zmazanie (stĺpec 'Vybrať').")
                        elif len(selected_idxs) > 1:
                            st.warning("⚠️ Označte iba jeden riadok na zmazanie.")
                        else:
                            # Get the ID of the row being deleted
                            deleted_id = df.iloc[selected_idxs[0]]["ID"] if "ID" in df.columns else "N/A"
                            # Delete the selected row
                            st.session_state.prijmy_domacnosti = df.drop(index=selected_idxs[0]).reset_index(drop=True)
                            #st.success(f"✅ Príjem {deleted_id} bol zmazaný")
                            st.rerun()
                    else:
                        st.error("❌ Chyba: Stĺpec 'Vybrať' nebol nájdený")

            # Display income entries in an editable table
            prijmy_df = st.session_state.prijmy_domacnosti
            if prijmy_df.empty:
                st.caption("Zatiaľ nie sú evidované žiadne príjmy. Kliknite na '➕ Pridať príjem' pre pridanie nového.")
            else:
                # Create a display version without ID column
                display_df = prijmy_df.drop(columns=["ID"], errors="ignore")
                
                # Configure columns for editing
                editable_column_config = {
                    "Vybrať": st.column_config.CheckboxColumn("Vybrať"),
                    column_names["kto"]: st.column_config.TextColumn("Kto:", max_chars=200, required=True),
                    column_names["tpp_brigada"]: st.column_config.NumberColumn("Čistý mesačný príjem (TPP, brigáda)", min_value=0, step=0.10, format="%.2f €"),
                    column_names["podnikanie"]: st.column_config.NumberColumn("Čistý mesačný príjem z podnikania", min_value=0, step=0.10, format="%.2f €"),
                    column_names["socialne_davky"]: st.column_config.NumberColumn("Sociálne dávky (PN, dôchodok, rodičovský príspevok)", min_value=0, step=0.10, format="%.2f €"),
                    column_names["ine"]: st.column_config.NumberColumn("Iné (výživné, podpora od rodiny)", min_value=0, step=0.10, format="%.2f €"),
                }
                edited = st.data_editor(
                    display_df,
                    column_config=editable_column_config,
                    num_rows="fixed",
                    use_container_width=True,
                    hide_index=True,
                    key="prijmy_data",
                    on_change=update_prijmy,
                    row_height=40,
                )
                
                # Store the edited data for persistence across reruns
                # Note: We don't update st.session_state.prijmy_domacnosti here as it causes
                # the data editor issue described in the Streamlit discussion
                st.session_state["prijmy_edited_data"] = edited.copy()

            # Calculate totals for income from the most up-to-date data
            # Clear cached edited data if main dataframe is empty
            if st.session_state.prijmy_domacnosti.empty and "prijmy_edited_data" in st.session_state:
                del st.session_state["prijmy_edited_data"]
            
            prijmy_data_for_totals = _get_prijmy_data_for_save()
            if prijmy_data_for_totals and len(prijmy_data_for_totals) > 0:
                df_prijmy = pd.DataFrame(prijmy_data_for_totals)
                income_columns = [column_names["tpp_brigada"], column_names["podnikanie"], column_names["socialne_davky"], column_names["ine"]]
                for col in income_columns:
                    if col in df_prijmy.columns:
                        df_prijmy[col] = pd.to_numeric(df_prijmy[col], errors="coerce").fillna(0)
                total_income = float(df_prijmy[income_columns].sum().sum())
            else:
                total_income = 0

            st.markdown(f"##### Príjmy celkom: {total_income} €")
            
            poznamky_prijmy = st.text_area(
                "Poznámky k príjmom:",
                height=75,
                value=default_poznamky_prijmy,
            )
            
        #background_color(
        #    background_color="#2870ed", 
        #    text_color="#ffffff", 
        #    header_text="5. Výdavky domácnosti", 
        #)
        #with st.container(border=True):
            st.markdown("<hr style='border: 1px solid #2870ed'>", unsafe_allow_html=True)
            
            st.markdown("#### Výdavky domácnosti")
            #st.markdown("##### Bývanie a domácnosť")
            with st.expander(f"Bývanie a domácnosť", expanded=True):
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Nájom (bytosprávca, prenajímateľ):")
                    najom = st.number_input(
                        "Nájom (bytosprávca, prenajímateľ):",
                        step=0.10,
                        value=default_najom,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2:
                    st.write("Elektrina:")
                    elektrina = st.number_input(
                        "Elektrina:",
                        step=0.10,
                        value=default_elektrina,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3:
                    st.write("Plyn:")
                    plyn = st.number_input(
                        "Plyn:",
                        step=0.10,
                        value=default_plyn,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col4:
                    st.write("Voda:")
                    voda = st.number_input(
                        "Voda:",
                        step=0.10,
                        value=default_voda,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )

                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Kúrenie:")
                    kurenie = st.number_input(
                        "Kúrenie:",
                        step=0.10,
                        value=default_kurenie,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2:
                    st.write("Domácnosť (čistiace prostriedky, opravy, vybavenie):")
                    domacnost = st.number_input(
                        "Domácnosť (čistiace prostriedky, opravy, vybavenie):",
                        step=0.10,
                        value=default_domacnost,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )                
                with col3:
                    st.write("Iné náklady na bývanie:")
                    ine_naklady_byvanie = st.number_input(
                        "Iné náklady na bývanie:",
                        step=0.10,
                        value=default_ine_naklady_byvanie,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                byvanie_sum = najom + elektrina + plyn + voda + kurenie + domacnost + ine_naklady_byvanie
                st.write(f"**Celkom: {byvanie_sum:.2f} €**")
 #           ""
            with st.expander("Rodina a osobné potreby", expanded=True):
#            st.markdown("##### Rodina a osobné potreby")
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Strava a potraviny:")
                    strava_potraviny = st.number_input(
                        "Strava a potraviny:",
                        step=0.10,
                        value=default_strava_potraviny,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2: 
                    st.write("Oblečenie a obuv:")
                    oblecenie_obuv = st.number_input(
                        "Oblečenie a obuv:",
                        step=0.10,
                        value=default_oblecenie_obuv,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3:
                    st.write("Hygiena, kozmetika a drogéria:")
                    hygiena_kozmetika_drogeria = st.number_input(
                        "Hygiena, kozmetika a drogéria:",
                        step=0.10,
                        value=default_hygiena_kozmetika_drogeria,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col4: 
                    st.write("Lieky, zdravie a zdravotnícko pomôcky:")
                    lieky_zdravie = st.number_input(
                        "Lieky, zdravie a zdravotnícko pomôcky:",
                        step=0.10,
                        value=default_lieky_zdravie,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )        
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Škôlka, škola, krúžky, družina, vreckové a iné výdavky na deti:")
                    vydavky_na_deti = st.number_input(
                        "Škôlka, škola, krúžky, družina, vreckové a iné výdavky na deti:",
                        step=0.10,
                        value=default_vydavky_na_deti,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2:
                    st.write("Výživné:")
                    vyzivne = st.number_input(
                        "Výživné:",
                        step=0.10,
                        value=default_vyzivne,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3:
                    st.write("Podpora rodičov, rodiny alebo iných osôb:")
                    podpora_rodicov = st.number_input(
                        "Podpora rodičov, rodiny alebo iných osôb:",
                        step=0.10,
                        value=default_podpora_rodicov,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col4:
                    st.write("Domáce zvieratá:")
                    domace_zvierata = st.number_input(
                        "Domáce zvieratá:",
                        step=0.10,
                        value=default_domace_zvierata,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                rodina_sum = strava_potraviny + oblecenie_obuv + hygiena_kozmetika_drogeria + lieky_zdravie + vydavky_na_deti + vyzivne + podpora_rodicov + domace_zvierata
                st.write(f"**Celkom: {rodina_sum:.2f} €**")

            with st.expander("Komunikácia a voľný čas", expanded=True):
#            st.markdown("##### Komunikácia a voľný čas")
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("TV + Internet:")
                    tv_internet = st.number_input(
                        "TV + Internet:",
                        step=0.10,
                        value=default_tv_internet,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2:
                    st.write("Telefón:")
                    telefon = st.number_input(
                        "Telefón:",
                        step=0.10,
                        value=default_telefon,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3: 
                    st.write("Volný čas a dovolenka:")
                    volny_cas = st.number_input(
                        "Volný čas a dovolenka:",
                        step=0.10,
                        value=default_volny_cas,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Predplatné  (Tlač, aplikácie, permanentky, fitko apod.):")
                    predplatne = st.number_input(
                        "Predplatné  (Tlač, aplikácie, permanentky, fitko apod.):",
                        step=0.10,
                        value=default_predplatne,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2:
                    st.write("Alkohol, lotéria, žreby, tipovanie, stávkovanie a herné automaty:")
                    alkohol_loteria_zreby = st.number_input(
                        "Alkohol, lotéria, žreby, tipovanie, stávkovanie a herné automaty:",
                        step=0.10,
                        value=default_alkohol_loteria_zreby,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3:
                    st.write("Cigarety:")
                    cigarety = st.number_input(
                        "Cigarety:",
                        step=0.10,
                        value=default_cigarety,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                komunikacia_sum = tv_internet + telefon + volny_cas + predplatne + alkohol_loteria_zreby + cigarety
                st.write(f"**Celkom: {komunikacia_sum:.2f} €**")

            with st.expander("Doprava", expanded=True):
           # st.markdown("##### Doprava")
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("MHD, autobus, vlak:")
                    mhd_autobus_vlak = st.number_input(
                        "MHD, autobus, vlak:",
                        step=0.10,
                        value=default_mhd_autobus_vlak,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2: 
                    st.write("Auto – pohonné hmoty:")
                    auto_pohonne_hmoty = st.number_input(
                        "Auto – pohonné hmoty:",
                        step=0.10,
                        value=default_auto_pohonne_hmoty,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3:
                    st.write("Auto – servis, PZP, diaľničné poplatky:")
                    auto_servis_pzp_dialnicne_poplatky = st.number_input(
                        "Auto – servis, PZP, diaľničné poplatky:",
                        step=0.10,
                        value=default_auto_servis_pzp_dialnicne_poplatky,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                doprava_sum = mhd_autobus_vlak + auto_pohonne_hmoty + auto_servis_pzp_dialnicne_poplatky
                st.write(f"**Celkom: {doprava_sum:.2f} €**")

            with st.expander("Financie a záväzky", expanded=True):
            #st.markdown("##### Financie a záväzky")
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Sporenie:")
                    sporenie = st.number_input(
                        "Sporenie:",
                        step=0.10,
                        value=default_sporenie,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col2:
                    st.write("Odvody (ak si ich platím sám):")
                    odvody = st.number_input(
                        "Odvody (ak si ich platím sám):",
                        step=0.1,
                        value=default_odvody,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col3:
                    st.write("Poistky:")
                    poistky = st.number_input(
                        "Poistky:",
                        step=0.10,
                        value=default_poistky,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                with col4:
                    st.write("Splátky úverov:")
                    splatky_uverov = st.number_input(
                        "Splátky úverov:",
                        step=0.10,
                        value=default_splatky_uverov,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
                financie_zavazky_sum = sporenie + odvody + poistky + splatky_uverov
                st.write(f"**Celkom: {financie_zavazky_sum:.2f} €**")
                
            with st.expander("Ostatné", expanded=True):
            #st.markdown("##### Ostatné")
                col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
                with col1:
                    st.write("Iné:")
                    ine = st.number_input(
                        "Iné:",
                        step=0.10,
                        value=default_ine,
                        min_value=0.0,
                        width=120,
                        label_visibility="collapsed",
                    )
            total_expenses = byvanie_sum + rodina_sum + komunikacia_sum + doprava_sum + financie_zavazky_sum + ine
            # Calculate total expenses
            #expense_keys = [
            #    "najom", "tv_internet", "oblecenie_obuv", "sporenie",
            #    "elektrina", "lieky_zdravie", "vydavky_na_deti", "vyzivne",
            #    "voda", "hygiena_kozmetika_drogeria", "domace_zvierata", "podpora_rodicov",
            #    "plyn", "strava_potraviny", "predplatne", "odvody",
            #    "kurenie", "mhd_autobus_vlak", "cigarety", "ine",
            #    "ine_naklady_byvanie", "auto_pohonne_hmoty", "alkohol_loteria_zreby",
            #    "telefon", "auto_servis_pzp_dialnicne_poplatky", "volny_cas"
            #]
            #total_expenses = sum(st.session_state.get(key, 0) for key in expense_keys)
            
            st.markdown(f"##### **Výdavky celkom: {total_expenses:.2f} €**")

            poznamky_vydavky = st.text_area(
                "Poznámky k výdavkom:",
                height=75,
                value=default_poznamky_vydavky
            )

        background_color(
            background_color="#2870ed", 
            text_color="#ffffff", 
            header_text="3. Dlhy", 
        )
        with st.container(border=True):

            # Create debts dataframe with structure from the image
            debts_columns = {
                "kde_som_si_pozical": "Kde som si požičal?",
                "na_aky_ucel": "Na aký účel?", 
                "kedy_som_si_pozical": "Kedy som si požičal?",
                "urokova_sadzba": "Úroková sadzba?",
                "kolko_som_si_pozical": "Koľko som si požičal?",
                "kolko_este_dlzim": "Koľko ešte dlžím?",
                "aku_mam_mesacnu_splatku": "Akú mám mesačnú splátku?"
            }
            
            # First table - ÚVERY (Loans)
            st.markdown("#### **Úvery**")

            # Define columns mapping (reuse existing headers)
            bank_types = [
                "banka",
                "nebankovka",
                "súkromné",
                "pôžička od rodiny/priateľov",
                "iné"
            ]
            #bank_type_options = ["— Vyberte —"] + bank_types

            uvery_columns = {
                "kde_som_si_pozical": debts_columns["kde_som_si_pozical"],
                "na_aky_ucel": debts_columns["na_aky_ucel"],
                "kedy_som_si_pozical": debts_columns["kedy_som_si_pozical"],
                "urokova_sadzba": debts_columns["urokova_sadzba"],
                "kolko_som_si_pozical": debts_columns["kolko_som_si_pozical"],
                "kolko_este_dlzim": debts_columns["kolko_este_dlzim"],
                "aku_mam_mesacnu_splatku": debts_columns["aku_mam_mesacnu_splatku"],
            }

            # Initialize loans storage in session state
            if "uvery_df" not in st.session_state:
                # Check if we have existing data to load
                if default_uvery_domacnosti:
                    # Load existing úvery data from database
                    try:
                        loaded_df = pd.DataFrame(default_uvery_domacnosti)
                        # Ensure all required columns exist
                        required_columns = {
                            "Vybrať": "bool",
                            "ID": "string",
                            uvery_columns["kde_som_si_pozical"]: "string",
                            uvery_columns["na_aky_ucel"]: "string",
                            uvery_columns["kedy_som_si_pozical"]: "object",
                            uvery_columns["urokova_sadzba"]: "float",
                            uvery_columns["kolko_som_si_pozical"]: "int",
                            uvery_columns["kolko_este_dlzim"]: "int",
                            uvery_columns["aku_mam_mesacnu_splatku"]: "int",
                        }
                        
                        for col, dtype in required_columns.items():
                            if col not in loaded_df.columns:
                                if dtype == "bool":
                                    loaded_df[col] = False
                                elif dtype == "string":
                                    loaded_df[col] = ""
                                elif dtype == "object":
                                    loaded_df[col] = None
                                elif dtype == "float":
                                    loaded_df[col] = 0.0
                        
                        # Reorder columns to match expected order
                        column_order = ["Vybrať", "ID", uvery_columns["kde_som_si_pozical"], uvery_columns["na_aky_ucel"], 
                                      uvery_columns["kedy_som_si_pozical"], uvery_columns["urokova_sadzba"], 
                                      uvery_columns["kolko_som_si_pozical"], uvery_columns["kolko_este_dlzim"], 
                                      uvery_columns["aku_mam_mesacnu_splatku"]]
                        st.session_state.uvery_df = loaded_df.reindex(columns=column_order, fill_value="")
                    except Exception as e:
                        # If loading fails, create empty dataframe
                        st.session_state.uvery_df = pd.DataFrame({
                            "Vybrať": pd.Series(dtype="bool"),
                            "ID": pd.Series(dtype="string"),
                            uvery_columns["kde_som_si_pozical"]: pd.Series(dtype="string"),
                            uvery_columns["na_aky_ucel"]: pd.Series(dtype="string"),
                            uvery_columns["kedy_som_si_pozical"]: pd.Series(dtype="object"),  # store date objects
                            uvery_columns["urokova_sadzba"]: pd.Series(dtype="float"),
                            uvery_columns["kolko_som_si_pozical"]: pd.Series(dtype="float"),
                            uvery_columns["kolko_este_dlzim"]: pd.Series(dtype="float"),
                            uvery_columns["aku_mam_mesacnu_splatku"]: pd.Series(dtype="float"),
                        })
                else:
                    # Create empty dataframe for new records
                    st.session_state.uvery_df = pd.DataFrame({
                        "Vybrať": pd.Series(dtype="bool"),
                        "ID": pd.Series(dtype="string"),
                        uvery_columns["kde_som_si_pozical"]: pd.Series(dtype="string"),
                        uvery_columns["na_aky_ucel"]: pd.Series(dtype="string"),
                        uvery_columns["kedy_som_si_pozical"]: pd.Series(dtype="object"),  # store date objects
                        uvery_columns["urokova_sadzba"]: pd.Series(dtype="float"),
                        uvery_columns["kolko_som_si_pozical"]: pd.Series(dtype="float"),
                        uvery_columns["kolko_este_dlzim"]: pd.Series(dtype="float"),
                        uvery_columns["aku_mam_mesacnu_splatku"]: pd.Series(dtype="float"),
                    })

            # Ensure selection column exists for older sessions
            if "Vybrať" not in st.session_state.uvery_df.columns:
                st.session_state.uvery_df.insert(0, "Vybrať", False)
            
            # Migrate old data to include ID column
            if "ID" not in st.session_state.uvery_df.columns:
                st.session_state.uvery_df.insert(1, "ID", "")
                # Generate IDs for existing entries
                for i in range(len(st.session_state.uvery_df)):
                    if pd.isna(st.session_state.uvery_df.iloc[i]["ID"]) or st.session_state.uvery_df.iloc[i]["ID"] == "":
                        st.session_state.uvery_df.iloc[i, st.session_state.uvery_df.columns.get_loc("ID")] = f"UV{int(time.time()*1000) + i}"

            # Initialize loan ID counter if not exists
            if "uvery_id_counter" not in st.session_state:
                st.session_state.uvery_id_counter = 1

            def _generate_uvery_id() -> str:
                """Generate a unique ID for loans"""
                timestamp = int(time.time() * 1000)  # milliseconds since epoch
                counter = st.session_state.uvery_id_counter
                st.session_state.uvery_id_counter += 1
                return f"UV{timestamp}{counter:03d}"

            @st.dialog("Pridať nový úver")
            def add_uver_dialog():
                st.write("Vyplňte údaje o novom úvere:")
                
                with st.form("add_uver_form"):
                    kde_som_si_pozical = st.text_input(
                        uvery_columns["kde_som_si_pozical"],
                        placeholder="Zadajte kde ste si požičali"
                    )
                    
                    na_aky_ucel = st.text_input(
                        uvery_columns["na_aky_ucel"],
                        placeholder="Zadajte účel úveru"
                    )
                    
                    kedy_som_si_pozical = st.date_input(
                        uvery_columns["kedy_som_si_pozical"],
                        value=date.today(),
                        min_value=date(1900, 1, 1),
                        format="DD.MM.YYYY"
                    )
                    
                    col1, col2 = st.columns(2, vertical_alignment="bottom")
                    with col1:
                        urokova_sadzba = st.number_input(
                            uvery_columns["urokova_sadzba"] + " (%)",
                            min_value=0.0,
                            max_value=100.0,
                            step=0.1,
                            value=0.0,
                            width=120,
                        )
                        
                        kolko_som_si_pozical = st.number_input(
                            uvery_columns["kolko_som_si_pozical"] + " (€)",
                            min_value=0.0,
                            step=0.10,
                            value=0.0,
                            width=120,
                        )
                    
                    with col2:
                        kolko_este_dlzim = st.number_input(
                            uvery_columns["kolko_este_dlzim"] + " (€)",
                            min_value=0.0,
                            step=0.10,
                            value=0.0,
                            width=120,
                        )
                        
                        mesacna_splatka = st.number_input(
                            uvery_columns["aku_mam_mesacnu_splatku"] + " (€)",
                            min_value=0.0,
                            step=0.10,
                            value=0.0,
                            width=120,
                        )
                    
                    # Form buttons
                    col1, col2 = st.columns(2)
                    with col1:
                        submit = st.form_submit_button("✅ Pridať úver", use_container_width=True, type="primary")
                    with col2:
                        cancel = st.form_submit_button("❌ Zrušiť", use_container_width=True)
                    
                    if submit:
                        # Validate required fields
                        if not kde_som_si_pozical.strip():
                            st.error("⚠️ Zadajte kde ste si požičali!")
                            return
                            
                        if not na_aky_ucel.strip():
                            st.warning("⚠️ Účel úveru je povinný!")
                            return
                        
                        # Generate new ID and create record
                        new_id = _generate_uvery_id()
                        new_row = {
                            "Vybrať": False,
                            "ID": new_id,
                            uvery_columns["kde_som_si_pozical"]: kde_som_si_pozical.strip(),
                            uvery_columns["na_aky_ucel"]: na_aky_ucel.strip(),
                            uvery_columns["kedy_som_si_pozical"]: kedy_som_si_pozical,
                            uvery_columns["urokova_sadzba"]: float(urokova_sadzba),
                            uvery_columns["kolko_som_si_pozical"]: float(kolko_som_si_pozical),
                            uvery_columns["kolko_este_dlzim"]: float(kolko_este_dlzim),
                            uvery_columns["aku_mam_mesacnu_splatku"]: float(mesacna_splatka),
                        }
                        
                        # Add to dataframe
                        new_df = pd.DataFrame([new_row])
                        st.session_state.uvery_df = pd.concat([st.session_state.uvery_df, new_df], ignore_index=True)
                       # st.success(f"✅ Úver {new_id} bol úspešne pridaný!")
                        st.rerun()
                    
                    elif cancel:
                        st.rerun()

            @st.dialog("Upraviť úver")
            def edit_uver_dialog(row_index):
                if row_index >= len(st.session_state.uvery_df):
                    st.error("❌ Chyba: Riadok neexistuje!")
                    return
                    
                # Get current values
                current_row = st.session_state.uvery_df.iloc[row_index]
                current_id = current_row["ID"]
                
                st.write(f"Upravujete úver: **{current_id}**")
                
                with st.form("edit_uver_form"):
                    # Get current type and set default index
                    current_typ = current_row[uvery_columns["kde_som_si_pozical"]]
                    #default_index = bank_types.index(current_typ) + 1 if current_typ in bank_types else 0
                    
                    kde_som_si_pozical = st.text_input(
                        uvery_columns["kde_som_si_pozical"],
                        value=str(current_row[uvery_columns["kde_som_si_pozical"]] or ""),
                        placeholder="Zadajte kde ste si požičali"
                    )
                    
                    na_aky_ucel = st.text_input(
                        uvery_columns["na_aky_ucel"],
                        value=str(current_row[uvery_columns["na_aky_ucel"]] or ""),
                        placeholder="Zadajte účel úveru"
                    )
                    
                    # Handle date properly
                    default_date = current_row[uvery_columns["kedy_som_si_pozical"]]
                    if pd.isna(default_date) or default_date is None or default_date == "":
                        default_date = date.today()
                    
                    kedy_som_si_pozical = st.date_input(
                        uvery_columns["kedy_som_si_pozical"],
                        value=default_date,
                        min_value=date(1900, 1, 1),
                        format="DD.MM.YYYY"
                    )
                    
                    col1, col2 = st.columns(2, vertical_alignment="bottom")
                    with col1:
                        urokova_sadzba = st.number_input(
                            uvery_columns["urokova_sadzba"] + " (%)",
                            min_value=0.0,
                            max_value=100.0,
                            step=0.1,
                            value=float(current_row[uvery_columns["urokova_sadzba"]] or 0.0),
                            width=120,
                        )
                        
                        kolko_som_si_pozical = st.number_input(
                            uvery_columns["kolko_som_si_pozical"] + " (€)",
                            min_value=0.0,
                            step=0.10,
                            value=float(current_row[uvery_columns["kolko_som_si_pozical"]] or 0.0),
                            width=120,
                        )
                    
                    with col2:
                        kolko_este_dlzim = st.number_input(
                            uvery_columns["kolko_este_dlzim"] + " (€)",
                            min_value=0.0,
                            step=0.10,
                            value=float(current_row[uvery_columns["kolko_este_dlzim"]] or 0.0),
                            width=120,
                        )
                        
                        mesacna_splatka = st.number_input(
                            uvery_columns["aku_mam_mesacnu_splatku"] + " (€)",
                            min_value=0.0,
                            step=0.10,
                            value=float(current_row[uvery_columns["aku_mam_mesacnu_splatku"]] or 0.0),
                            width=120,
                        )
                    
                    # Form buttons
                    col1, col2 = st.columns(2)
                    with col1:
                        submit = st.form_submit_button("✅ Uložiť zmeny", use_container_width=True, type="primary")
                    with col2:
                        cancel = st.form_submit_button("❌ Zrušiť", use_container_width=True)
                    
                    if submit:
                        # Validate required fields
                        if not kde_som_si_pozical.strip():
                            st.warning("⚠️ Zadajte kde ste si požičali!")
                            return
                            
                        if not na_aky_ucel.strip():
                            st.warning("⚠️ Účel úveru je povinný!")
                            return
                        
                        # Update the row
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["kde_som_si_pozical"])] = kde_som_si_pozical.strip()
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["na_aky_ucel"])] = na_aky_ucel.strip()
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["kedy_som_si_pozical"])] = kedy_som_si_pozical
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["urokova_sadzba"])] = float(urokova_sadzba)
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["kolko_som_si_pozical"])] = float(kolko_som_si_pozical)
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["kolko_este_dlzim"])] = float(kolko_este_dlzim)
                        st.session_state.uvery_df.iloc[row_index, st.session_state.uvery_df.columns.get_loc(uvery_columns["aku_mam_mesacnu_splatku"])] = float(mesacna_splatka)
                        
                       # st.success(f"✅ Úver {current_id} bol úspešne upravený!")
                        st.rerun()
                    
                    elif cancel:
                        st.rerun()

            # Controls: add / edit / delete selected
            ctrl_uv1, ctrl_uv2, ctrl_uv3 = st.columns([1, 1, 1], vertical_alignment="bottom")
            
            # Add loan button
            with ctrl_uv1:
                if st.button("➕ Pridať úver", use_container_width=True, key="add_uver_btn"):
                    add_uver_dialog()
            
            # Edit loan button  
            with ctrl_uv2:
                if st.button("✏️ Upraviť vybraný", use_container_width=True, key="edit_uver_btn"):
                    df = st.session_state.uvery_df
                    # Find selected rows
                    if "Vybrať" in df.columns:
                        selected_idxs = df.index[df["Vybrať"] == True].tolist()
                        if len(selected_idxs) == 0:
                            st.warning("⚠️ Označte jeden riadok v tabuľke na úpravu (stĺpec 'Vybrať').")
                        elif len(selected_idxs) > 1:
                            st.warning("⚠️ Označte iba jeden riadok na úpravu.")
                        else:
                            edit_uver_dialog(selected_idxs[0])
                    else:
                        st.error("❌ Chyba: Stĺpec 'Vybrať' nebol nájdený")
            
            # Delete loan button  
            with ctrl_uv3:
                if st.button("🗑️ Zmazať vybraný", use_container_width=True, key="delete_uver_btn"):
                    df = st.session_state.uvery_df
                    # Find selected rows
                    if "Vybrať" in df.columns:
                        selected_idxs = df.index[df["Vybrať"] == True].tolist()
                        if len(selected_idxs) == 0:
                            st.warning("⚠️ Označte jeden riadok v tabuľke na zmazanie (stĺpec 'Vybrať').")
                        elif len(selected_idxs) > 1:
                            st.warning("⚠️ Označte iba jeden riadok na zmazanie.")
                        else:
                            # Get the ID of the row being deleted
                            deleted_id = df.iloc[selected_idxs[0]]["ID"] if "ID" in df.columns else "N/A"
                            # Delete the selected row
                            st.session_state.uvery_df = df.drop(index=selected_idxs[0]).reset_index(drop=True)
                            #st.success(f"✅ Úver {deleted_id} bol zmazaný")
                            st.rerun()
                    else:
                        st.error("❌ Chyba: Stĺpec 'Vybrať' nebol nájdený")

            # Display loans in a clean, read-only table
            uvery_df = st.session_state.uvery_df
            if uvery_df.empty:
                st.caption("Zatiaľ nie sú pridané žiadne úvery. Kliknite na '➕ Pridať úver' pre pridanie nového.")
            else:
                # Create a display version with proper column order (without ID)
                display_columns = ["Vybrať", uvery_columns["kde_som_si_pozical"], uvery_columns["na_aky_ucel"], uvery_columns["kedy_som_si_pozical"], uvery_columns["urokova_sadzba"], uvery_columns["kolko_som_si_pozical"], uvery_columns["kolko_este_dlzim"], uvery_columns["aku_mam_mesacnu_splatku"]]
                df_for_display = uvery_df.reindex(columns=display_columns, fill_value="").copy()
                
                # Configure columns for display only (checkbox for selection, rest disabled)
                display_column_config = {
                    "Vybrať": st.column_config.CheckboxColumn("Vybrať"),
                    uvery_columns["kde_som_si_pozical"]: st.column_config.TextColumn("Kde som si požičal?", disabled=True),
                    uvery_columns["na_aky_ucel"]: st.column_config.TextColumn("Na aký účel?", disabled=True),
                    uvery_columns["kedy_som_si_pozical"]: st.column_config.DateColumn("Kedy som si požičal?", disabled=True, format="DD.MM.YYYY"),
                    uvery_columns["urokova_sadzba"]: st.column_config.NumberColumn("Úroková sadzba (%)", disabled=True, format="%.1f%%"),
                    uvery_columns["kolko_som_si_pozical"]: st.column_config.NumberColumn("Koľko som si požičal?", disabled=True, format="%.2f €"),
                    uvery_columns["kolko_este_dlzim"]: st.column_config.NumberColumn("Koľko ešte dlžím?", disabled=True, format="%.2f €"),
                    uvery_columns["aku_mam_mesacnu_splatku"]: st.column_config.NumberColumn("Mesačná splátka", disabled=True, format="%.2f €"),
                }

                edited = st.data_editor(
                    df_for_display,
                    column_config=display_column_config,
                    num_rows="fixed",
                    use_container_width=True,
                    hide_index=True,
                    key="uvery_data",
                    row_height=40,
                )
                
                # Update session state only with selection changes (checkbox column)
                if "Vybrať" in edited.columns:
                    st.session_state.uvery_df["Vybrať"] = edited["Vybrať"]

            # Calculate totals for loans from state
            loan_total_borrowed = uvery_df[uvery_columns["kolko_som_si_pozical"]].fillna(0).sum() if not uvery_df.empty else 0
            loan_total_remaining = uvery_df[uvery_columns["kolko_este_dlzim"]].fillna(0).sum() if not uvery_df.empty else 0
            loan_total_monthly = uvery_df[uvery_columns["aku_mam_mesacnu_splatku"]].fillna(0).sum() if not uvery_df.empty else 0

            ""
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**Celkom požičky: {loan_total_borrowed:.2f} €**")
            with col2:
                st.markdown(f"**Celkom dlhy: {loan_total_remaining:.2f} €**")
            with col3:
                st.markdown(f"**Splátky mesačne: {loan_total_monthly:.2f} €**")
            
            #st.markdown("---")
            
            # Second table - EXEKÚCIE (Executions)
            st.markdown("<hr style='border: 1px solid #2870ed'>", unsafe_allow_html=True)
            
            st.markdown("#### **Exekúcie**")

            # Initialize executions storage in session state
            if "exekucie_df" not in st.session_state:
                # Check if we have existing data to load
                if default_exekucie_domacnosti:
                    # Load existing execution data from database
                    try:
                        loaded_df = pd.DataFrame(default_exekucie_domacnosti)
                        # Ensure all required columns exist
                        required_columns = {
                            "Vybrať": "bool",
                            "ID": "string",
                            "Meno exekútora": "string",
                            "Pre koho exekútor vymáha dlh?": "string",
                            "Od kedy mám exekúciu?": "string",
                            "Aktuálna výška exekúcie?": "int",
                            "Akou sumou ju mesačne splácam?": "int",
                        }
                        
                        for col, dtype in required_columns.items():
                            if col not in loaded_df.columns:
                                if dtype == "bool":
                                    loaded_df[col] = False
                                elif dtype == "string":
                                    loaded_df[col] = ""
                                elif dtype == "int":
                                    loaded_df[col] = 0
                        
                        # Reorder columns to match expected order
                        column_order = ["Vybrať", "ID", "Meno exekútora", "Pre koho exekútor vymáha dlh?", 
                                      "Od kedy mám exekúciu?", "Aktuálna výška exekúcie?", "Akou sumou ju mesačne splácam?"]
                        st.session_state.exekucie_df = loaded_df.reindex(columns=column_order, fill_value="")
                    except Exception as e:
                        # If loading fails, create empty dataframe
                        st.session_state.exekucie_df = pd.DataFrame({
                            "Vybrať": pd.Series(dtype="bool"),
                            "ID": pd.Series(dtype="string"),
                            "Meno exekútora": pd.Series(dtype="string"),
                            "Pre koho exekútor vymáha dlh?": pd.Series(dtype="string"),
                            "Od kedy mám exekúciu?": pd.Series(dtype="string"),
                            "Aktuálna výška exekúcie?": pd.Series(dtype="int"),
                            "Akou sumou ju mesačne splácam?": pd.Series(dtype="int"),
                        })
                else:
                    # Create empty dataframe for new records
                    st.session_state.exekucie_df = pd.DataFrame({
                        "Vybrať": pd.Series(dtype="bool"),
                        "ID": pd.Series(dtype="string"),
                        "Meno exekútora": pd.Series(dtype="string"),
                        "Pre koho exekútor vymáha dlh?": pd.Series(dtype="string"),
                        "Od kedy mám exekúciu?": pd.Series(dtype="string"),
                        "Aktuálna výška exekúcie?": pd.Series(dtype="int"),
                        "Akou sumou ju mesačne splácam?": pd.Series(dtype="int"),
                    })

            # Ensure selection column exists for older sessions
            if "Vybrať" not in st.session_state.exekucie_df.columns:
                st.session_state.exekucie_df.insert(0, "Vybrať", False)
            
            # Migrate old "Číslo" column to new "ID" system for existing data
            if "Číslo" in st.session_state.exekucie_df.columns and "ID" not in st.session_state.exekucie_df.columns:
                st.session_state.exekucie_df = st.session_state.exekucie_df.rename(columns={"Číslo": "ID"})
                # Generate proper IDs for existing entries
                for i in range(len(st.session_state.exekucie_df)):
                    if pd.isna(st.session_state.exekucie_df.iloc[i]["ID"]) or st.session_state.exekucie_df.iloc[i]["ID"] == "":
                        st.session_state.exekucie_df.iloc[i, st.session_state.exekucie_df.columns.get_loc("ID")] = f"EX{int(time.time()*1000) + i}"

            # Initialize execution ID counter if not exists
            if "exekucie_id_counter" not in st.session_state:
                st.session_state.exekucie_id_counter = 1

            def _generate_exekucie_id() -> str:
                """Generate a unique ID for executions"""
                timestamp = int(time.time() * 1000)  # milliseconds since epoch
                counter = st.session_state.exekucie_id_counter
                st.session_state.exekucie_id_counter += 1
                return f"EX{timestamp}{counter:03d}"

            def add_new_exekucia():
                """Add a new execution row to the dataframe"""
                # First, save any current edits from the data editor to prevent data loss
                # Use the stored edited data if available, otherwise use the current widget data
                edited_data = None
                if "exekucie_edited_data" in st.session_state:
                    edited_data = st.session_state["exekucie_edited_data"]
                elif "_exekucie_data" in st.session_state:
                    edited_data = st.session_state["_exekucie_data"]
                
                if edited_data is not None and isinstance(edited_data, pd.DataFrame):
                    # Merge the edited data with the main dataframe, preserving IDs
                    if "ID" in st.session_state.exekucie_df.columns:
                        edited_data_with_id = edited_data.copy()
                        edited_data_with_id.insert(1, "ID", st.session_state.exekucie_df["ID"])
                        st.session_state.exekucie_df = edited_data_with_id
                    else:
                        st.session_state.exekucie_df = edited_data
                
                new_id = _generate_exekucie_id()
                new_row = {
                    "Vybrať": False,
                    "ID": new_id,
                    "Meno exekútora": "",
                    "Pre koho exekútor vymáha dlh?": "",
                    "Od kedy mám exekúciu?": "",
                    "Aktuálna výška exekúcie?": 0,
                    "Akou sumou ju mesačne splácam?": 0,
                }
                
                # Add to dataframe - ensure we're working with the current session state
                new_df = pd.DataFrame([new_row])
                st.session_state.exekucie_df = pd.concat([st.session_state.exekucie_df, new_df], ignore_index=True)

            # Editor for executions
            exekucie_column_config = {
                "Vybrať": st.column_config.CheckboxColumn("Vybrať"),
                "ID": st.column_config.TextColumn("ID", disabled=True, width="small"),
                "Meno exekútora": st.column_config.TextColumn("Meno exekútora", max_chars=200),
                "Pre koho exekútor vymáha dlh?": st.column_config.TextColumn("Pre koho exekútor vymáha dlh?", max_chars=200),
                "Od kedy mám exekúciu?": st.column_config.TextColumn("Od kedy mám exekúciu?", max_chars=100),
                "Aktuálna výška exekúcie?": st.column_config.NumberColumn("Aktuálna výška exekúcie?", min_value=0, step=1, format="%d €"),
                "Akou sumou ju mesačne splácam?": st.column_config.NumberColumn("Akou sumou ju mesačne splácam?", min_value=0, step=1, format="%d €"),
            }

            # Order columns in the editor
            cols_order = [
                "Vybrať",
                "ID",
                "Meno exekútora",
                "Pre koho exekútor vymáha dlh?",
                "Od kedy mám exekúciu?",
                "Aktuálna výška exekúcie?",
                "Akou sumou ju mesačne splácam?",
            ]
            # Ensure all columns exist in the correct order
            for col in cols_order:
                if col not in st.session_state.exekucie_df.columns:
                    if col in ["Meno exekútora", "Pre koho exekútor vymáha dlh?", "Od kedy mám exekúciu?", "ID"]:
                        st.session_state.exekucie_df[col] = ""
                    elif col == "Vybrať":
                        st.session_state.exekucie_df[col] = False
                    else:
                        st.session_state.exekucie_df[col] = 0
            
            # Configure columns for editing (only ID disabled)
            editable_column_config = {
                "Vybrať": st.column_config.CheckboxColumn("Vybrať"),
                "ID": st.column_config.TextColumn("ID", disabled=True, width="small"),
                "Meno exekútora": st.column_config.TextColumn("Meno exekútora", max_chars=200, required=True),
                "Pre koho exekútor vymáha dlh?": st.column_config.TextColumn("Pre koho exekútor vymáha dlh?", max_chars=200, required=True),
                "Od kedy mám exekúciu?": st.column_config.TextColumn("Od kedy mám exekúciu?", max_chars=100),
                "Aktuálna výška exekúcie?": st.column_config.NumberColumn("Aktuálna výška exekúcie?", min_value=0, step=1, format="%d €"),
                "Akou sumou ju mesačne splácam?": st.column_config.NumberColumn("Akou sumou ju mesačne splácam?", min_value=0, step=1, format="%d €"),
            }

            # Display executions in an editable table - following your example pattern
            exekucie_df = st.session_state.exekucie_df
            
            # Controls: add / delete selected (always visible)
            ctrl_ex1, ctrl_ex2 = st.columns([1, 1], vertical_alignment="bottom")
            
            # Add execution button (always visible)
            with ctrl_ex1:
                if st.button("➕ Pridať exekúciu", use_container_width=True, key="add_exekucia_btn"):
                    add_new_exekucia()
                    st.rerun()
            
            # Delete execution button (always visible)
            with ctrl_ex2:
                if st.button("🗑️ Zmazať vybranú", use_container_width=True, key="delete_exekucia_btn"):
                    # First, save any current edits from the data editor to prevent data loss
                    edited_data = None
                    if "exekucie_edited_data" in st.session_state:
                        edited_data = st.session_state["exekucie_edited_data"]
                    elif "_exekucie_data" in st.session_state:
                        edited_data = st.session_state["_exekucie_data"]
                    
                    if edited_data is not None and isinstance(edited_data, pd.DataFrame):
                        # Merge the edited data with the main dataframe, preserving IDs
                        if "ID" in st.session_state.exekucie_df.columns:
                            edited_data_with_id = edited_data.copy()
                            edited_data_with_id.insert(1, "ID", st.session_state.exekucie_df["ID"])
                            st.session_state.exekucie_df = edited_data_with_id
                        else:
                            st.session_state.exekucie_df = edited_data
                    
                    df = st.session_state.exekucie_df
                    # Find selected rows
                    if "Vybrať" in df.columns:
                        selected_idxs = df.index[df["Vybrať"] == True].tolist()
                        if len(selected_idxs) == 0:
                            st.warning("⚠️ Označte jeden riadok v tabuľke na zmazanie (stĺpec 'Vybrať').")
                        elif len(selected_idxs) > 1:
                            st.warning("⚠️ Označte iba jeden riadok na zmazanie.")
                        else:
                            # Get the ID of the row being deleted
                            deleted_id = df.iloc[selected_idxs[0]]["ID"] if "ID" in df.columns else "N/A"
                            # Delete the selected row
                            st.session_state.exekucie_df = df.drop(index=selected_idxs[0]).reset_index(drop=True)
                            #st.success(f"✅ Exekúcia {deleted_id} bola zmazaná")
                            st.rerun()
                    else:
                        st.error("❌ Chyba: Stĺpec 'Vybrať' nebol nájdený")
            
            if exekucie_df.empty:
                st.caption("Zatiaľ nie sú pridané žiadne exekúcie. Kliknite na '➕ Pridať exekúciu' pre pridanie nového.")
            else:
                # Create a copy without the ID column for display
                display_df = exekucie_df.drop(columns=["ID"], errors="ignore")
                
                # Create column config without ID column
                display_column_config = {k: v for k, v in editable_column_config.items() if k != "ID"}

                edited_exekucie_df = st.data_editor(
                    display_df,
                    column_config=display_column_config,
                    num_rows="fixed",
                    use_container_width=True,
                    hide_index=True,
                    key="_exekucie_data",
                    row_height=40,
                )
                
                # Store the edited data for persistence across reruns
                # Note: We don't update st.session_state.exekucie_df here as it causes
                # the data editor issue described in the Streamlit discussion
                st.session_state["exekucie_edited_data"] = edited_exekucie_df.copy()



            # Calculate totals for executions from the most up-to-date data
            # Clear cached edited data if main dataframe is empty
            if st.session_state.exekucie_df.empty and "exekucie_edited_data" in st.session_state:
                del st.session_state["exekucie_edited_data"]
            
            exekucie_data_for_totals = _get_exekucie_data_for_save()
            if exekucie_data_for_totals and len(exekucie_data_for_totals) > 0:
                df_ex = pd.DataFrame(exekucie_data_for_totals)
                for col in ["Aktuálna výška exekúcie?", "Akou sumou ju mesačne splácam?"]:
                    if col in df_ex.columns:
                        df_ex[col] = pd.to_numeric(df_ex[col], errors="coerce").fillna(0)
                execution_total_amount = int(df_ex["Aktuálna výška exekúcie?"].sum())
                execution_total_monthly = int(df_ex["Akou sumou ju mesačne splácam?"].sum())
            else:
                execution_total_amount = 0
                execution_total_monthly = 0

            ""
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Celkom exekúcie: {execution_total_amount} €**")
            with col2:
                st.markdown(f"**Splátky mesačne: {execution_total_monthly} €**")

            
            ###########################################################
            # Third table - NEDOPLATKY (Arrears)
            ###########################################################
            st.markdown("<hr style='border: 1px solid #2870ed'>", unsafe_allow_html=True)
            st.markdown("#### **Nedoplatky**")
            # Define nedoplatky columns
            nedoplatky_columns = {
                "kde_mam_nedoplatok": "Kde mám nedoplatok?",
                "od_kedy_mam_nedoplatok": "Od kedy mám nedoplatok?",
                "v_akej_vyske_mam_nedoplatok": "V akej výške mám nedoplatok?",
                "akou_sumou_ho_mesacne_splacam": "Akou sumou ho mesačne splácam?"
            }

            # Initialize nedoplatky storage in session state
            if "nedoplatky_data" not in st.session_state:
                # Check if we have existing data to load
                if default_nedoplatky_data:
                    # Load existing nedoplatky data from database
                    try:
                        loaded_df = pd.DataFrame(default_nedoplatky_data)
                        # Ensure all required columns exist
                        required_columns = {
                            "Vybrať": "bool",
                            "ID": "string",
                            nedoplatky_columns["kde_mam_nedoplatok"]: "string",
                            nedoplatky_columns["od_kedy_mam_nedoplatok"]: "string",
                            nedoplatky_columns["v_akej_vyske_mam_nedoplatok"]: "int",
                            nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]: "int",
                        }
                        
                        for col, dtype in required_columns.items():
                            if col not in loaded_df.columns:
                                if dtype == "bool":
                                    loaded_df[col] = False
                                elif dtype == "string":
                                    loaded_df[col] = ""
                                elif dtype == "int":
                                    loaded_df[col] = 0
                        
                        # Reorder columns to match expected order
                        column_order = ["Vybrať", "ID", nedoplatky_columns["kde_mam_nedoplatok"], 
                                      nedoplatky_columns["od_kedy_mam_nedoplatok"], nedoplatky_columns["v_akej_vyske_mam_nedoplatok"], 
                                      nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]]
                        st.session_state.nedoplatky_data = loaded_df.reindex(columns=column_order, fill_value="")
                    except Exception as e:
                        # If loading fails, create empty dataframe
                        st.session_state.nedoplatky_data = pd.DataFrame({
                            "Vybrať": pd.Series(dtype="bool"),
                            "ID": pd.Series(dtype="string"),
                            nedoplatky_columns["kde_mam_nedoplatok"]: pd.Series(dtype="string"),
                            nedoplatky_columns["od_kedy_mam_nedoplatok"]: pd.Series(dtype="string"),
                            nedoplatky_columns["v_akej_vyske_mam_nedoplatok"]: pd.Series(dtype="int"),
                            nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]: pd.Series(dtype="int"),
                        })
                else:
                    # Create empty dataframe for new records
                    st.session_state.nedoplatky_data = pd.DataFrame({
                        "Vybrať": pd.Series(dtype="bool"),
                        "ID": pd.Series(dtype="string"),
                        nedoplatky_columns["kde_mam_nedoplatok"]: pd.Series(dtype="string"),
                        nedoplatky_columns["od_kedy_mam_nedoplatok"]: pd.Series(dtype="string"),
                        nedoplatky_columns["v_akej_vyske_mam_nedoplatok"]: pd.Series(dtype="int"),
                        nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]: pd.Series(dtype="int"),
                    })

            # Ensure selection column exists for older sessions
            if "Vybrať" not in st.session_state.nedoplatky_data.columns:
                st.session_state.nedoplatky_data.insert(0, "Vybrať", False)

            # Migrate old data to include ID column
            if "ID" not in st.session_state.nedoplatky_data.columns:
                st.session_state.nedoplatky_data.insert(1, "ID", "")
                # Generate IDs for existing entries
                for i in range(len(st.session_state.nedoplatky_data)):
                    if pd.isna(st.session_state.nedoplatky_data.iloc[i]["ID"]) or st.session_state.nedoplatky_data.iloc[i]["ID"] == "":
                        st.session_state.nedoplatky_data.iloc[i, st.session_state.nedoplatky_data.columns.get_loc("ID")] = f"ND{int(time.time()*1000) + i}"

            # Initialize nedoplatky ID counter if not exists
            if "nedoplatky_id_counter" not in st.session_state:
                st.session_state.nedoplatky_id_counter = 1

            def _generate_nedoplatky_id() -> str:
                """Generate a unique ID for nedoplatky entries"""
                timestamp = int(time.time() * 1000)  # milliseconds since epoch
                counter = st.session_state.nedoplatky_id_counter
                st.session_state.nedoplatky_id_counter += 1
                return f"ND{timestamp}{counter:03d}"

            nedoplatky_categories = ["Bytosprávca", "Telefón", "Energie", "Zdravotná poisťovňa", "Soc. poisťovňa", "Pokuty, dane a pod."]

            def add_new_nedoplatok():
                """Add a new nedoplatok row to the dataframe"""
                # First, save any current edits from the data editor to prevent data loss
                # Use the stored edited data if available, otherwise use the current widget data
                edited_data = None
                if "nedoplatky_edited_data" in st.session_state:
                    edited_data = st.session_state["nedoplatky_edited_data"]
                elif "nedoplatky_editor" in st.session_state:
                    edited_data = st.session_state["nedoplatky_editor"]
                
                if edited_data is not None and isinstance(edited_data, pd.DataFrame):
                    # Merge the edited data with the main dataframe, preserving IDs
                    if "ID" in edited_data.columns:
                        # ID column already exists, just use the edited data
                        st.session_state.nedoplatky_data = edited_data
                    elif "ID" in st.session_state.nedoplatky_data.columns:
                        # Add the ID column back to the edited data
                        edited_data_with_id = edited_data.copy()
                        edited_data_with_id.insert(1, "ID", st.session_state.nedoplatky_data["ID"])
                        st.session_state.nedoplatky_data = edited_data_with_id
                    else:
                        st.session_state.nedoplatky_data = edited_data
                
                new_id = _generate_nedoplatky_id()
                new_row = {
                    "Vybrať": False,
                    "ID": new_id,
                    nedoplatky_columns["kde_mam_nedoplatok"]: "",
                    nedoplatky_columns["od_kedy_mam_nedoplatok"]: "",
                    nedoplatky_columns["v_akej_vyske_mam_nedoplatok"]: 0,
                    nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]: 0,
                }
                
                # Add to dataframe
                new_df = pd.DataFrame([new_row])
                st.session_state.nedoplatky_data = pd.concat([st.session_state.nedoplatky_data, new_df], ignore_index=True)


            # Display nedoplatky entries in an editable table
            nedoplatky_df = st.session_state.nedoplatky_data
            
            # Controls: add / delete selected (always visible)
            ctrl_nd1, ctrl_nd2 = st.columns(2, vertical_alignment="top")
            
            # Add nedoplatok button (always visible)
            with ctrl_nd1:
                if st.button("➕ Pridať nedoplatok", use_container_width=True, key="add_nedoplatky_btn"):
                    add_new_nedoplatok()
                    st.rerun()
            
            # Delete nedoplatok button (always visible)
            with ctrl_nd2:
                if st.button("🗑️ Zmazať vybraný", use_container_width=True, key="delete_nedoplatky_btn"):
                    # First, save any current edits from the data editor to prevent data loss
                    edited_data = None
                    if "nedoplatky_edited_data" in st.session_state:
                        edited_data = st.session_state["nedoplatky_edited_data"]
                    elif "nedoplatky_editor" in st.session_state:
                        edited_data = st.session_state["nedoplatky_editor"]
                    
                    if edited_data is not None and isinstance(edited_data, pd.DataFrame):
                        # Merge the edited data with the main dataframe, preserving IDs
                        if "ID" in edited_data.columns:
                            # ID column already exists, just use the edited data
                            st.session_state.nedoplatky_data = edited_data
                        elif "ID" in st.session_state.nedoplatky_data.columns:
                            # Add the ID column back to the edited data
                            edited_data_with_id = edited_data.copy()
                            edited_data_with_id.insert(1, "ID", st.session_state.nedoplatky_data["ID"])
                            st.session_state.nedoplatky_data = edited_data_with_id
                        else:
                            st.session_state.nedoplatky_data = edited_data
                    
                    df = st.session_state.nedoplatky_data
                    # Find selected rows
                    if "Vybrať" in df.columns:
                        selected_idxs = df.index[df["Vybrať"] == True].tolist()
                        if len(selected_idxs) == 0:
                            st.warning("⚠️ Označte jeden riadok v tabuľke na zmazanie (stĺpec 'Vybrať').")
                        elif len(selected_idxs) > 1:
                            st.warning("⚠️ Označte iba jeden riadok na zmazanie.")
                        else:
                            # Get the ID of the row being deleted
                            deleted_id = df.iloc[selected_idxs[0]]["ID"] if "ID" in df.columns else "N/A"
                            # Delete the selected row
                            st.session_state.nedoplatky_data = df.drop(index=selected_idxs[0]).reset_index(drop=True)
                            #st.success(f"✅ Nedoplatok {deleted_id} bol zmazaný")
                            st.rerun()
                    else:
                        st.error("❌ Chyba: Stĺpec 'Vybrať' nebol nájdený")
            
            if nedoplatky_df.empty:
                st.caption("Zatiaľ nie sú pridané žiadne nedoplatky. Kliknite na '➕ Pridať nedoplatok' pre pridanie nového.")
            else:
                # Create a display version without ID column
                display_df = nedoplatky_df.drop(columns=["ID"], errors="ignore")
                
                # Configure columns for editing
                editable_column_config = {
                    "Vybrať": st.column_config.CheckboxColumn("Vybrať"),
                    nedoplatky_columns["kde_mam_nedoplatok"]: st.column_config.SelectboxColumn(
                        "Kde mám nedoplatok?", 
                        options=nedoplatky_categories + ["Iné"],
                        required=True
                    ),
                    nedoplatky_columns["od_kedy_mam_nedoplatok"]: st.column_config.TextColumn("Od kedy mám nedoplatok?", max_chars=100),
                    nedoplatky_columns["v_akej_vyske_mam_nedoplatok"]: st.column_config.NumberColumn("V akej výške mám nedoplatok?", min_value=0, step=1, format="%d €"),
                    nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]: st.column_config.NumberColumn("Akou sumou ho mesačne splácam?", min_value=0, step=1, format="%d €"),
                }

                edited = st.data_editor(
                    display_df,
                    column_config=editable_column_config,
                    num_rows="fixed",
                    use_container_width=True,
                    hide_index=True,
                    key="nedoplatky_editor",
                    row_height=40,
                )
                
                # Store the edited data for persistence across reruns
                # Note: We don't update st.session_state.nedoplatky_data here as it causes
                # the data editor issue described in the Streamlit discussion
                st.session_state["nedoplatky_edited_data"] = edited.copy()

            # Calculate totals for nedoplatky from the most up-to-date data
            # Clear cached edited data if main dataframe is empty
            if st.session_state.nedoplatky_data.empty and "nedoplatky_edited_data" in st.session_state:
                del st.session_state["nedoplatky_edited_data"]
            
            nedoplatky_data_for_totals = _get_nedoplatky_data_for_save()
            if nedoplatky_data_for_totals and len(nedoplatky_data_for_totals) > 0:
                df_nedoplatky = pd.DataFrame(nedoplatky_data_for_totals)
                nedoplatok_columns_for_calc = [nedoplatky_columns["v_akej_vyske_mam_nedoplatok"], nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]]
                for col in nedoplatok_columns_for_calc:
                    if col in df_nedoplatky.columns:
                        df_nedoplatky[col] = pd.to_numeric(df_nedoplatky[col], errors="coerce").fillna(0)
                arrears_total_amount = int(df_nedoplatky[nedoplatky_columns["v_akej_vyske_mam_nedoplatok"]].sum())
                arrears_total_monthly = int(df_nedoplatky[nedoplatky_columns["akou_sumou_ho_mesacne_splacam"]].sum())
            else:
                arrears_total_amount = 0
                arrears_total_monthly = 0
            
            ""
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Celkom nedoplatky: {arrears_total_amount} €**")
            with col2:
                st.markdown(f"**Splátky mesačne: {arrears_total_monthly} €**")
            
            st.markdown("<hr style='border: 1px solid #2870ed'>", unsafe_allow_html=True)
            
            poznamky_dlhy = st.text_area(
                "Poznámky k dlhom:",
                height=75,
                value=default_poznamky_dlhy
            )

        background_color(
            background_color="#2870ed", 
            text_color="#ffffff", 
            header_text="Komentár pracovníka SLSP",
            text="Aké kroky boli s klientom realizované zo strany pobočky a s akým výsledkom (napr. žiadosť o ŤŽS, prehodnotenie US, predĺženie splatnosti úverov, žiadosť o refinančný úver, zapojenie ďalších rodinných príslušníkov a pod.)"
        )

        with st.container(border=True):
            komentar_pracovnika_slsp = st.text_area(
                "Komentár pracovníka SLSP",
                label_visibility="collapsed",
                value=default_komentar_pracovnika_slsp,
                height=150
            )

        
        # Simple function to remove quotes from text
        def clean_text(text):
            if isinstance(text, str):
                return text.replace('"', '').replace('"', '').replace('"', '')
            return text
        
        # Create the data to save
        data_to_save = {
            "meno_priezvisko": clean_text(meno_priezvisko),
            "datum_narodenia": datum_narodenia,
            "sap_id": sap_id,
            "email_zamestnanca": email_zamestnanca,
            "pribeh": clean_text(pribeh),
            "riesenie": clean_text(riesenie),
            "pocet_clenov_domacnosti": pocet_clenov_domacnosti,
            "typ_bydliska": typ_bydliska,
            "domacnost_poznamky": clean_text(domacnost_poznamky),
            "najom": najom,
            "tv_internet": tv_internet,
            "oblecenie_obuv": oblecenie_obuv,
            "sporenie": sporenie,
            "elektrina": elektrina,
            "lieky_zdravie": lieky_zdravie,
            "vydavky_na_deti": vydavky_na_deti,
            "vyzivne": vyzivne,
            "voda": voda,
            "hygiena_kozmetika_drogeria": hygiena_kozmetika_drogeria,
            "domace_zvierata": domace_zvierata,
            "podpora_rodicov": podpora_rodicov,
            "plyn": plyn,
            "strava_potraviny": strava_potraviny,
            "predplatne": predplatne,
            "odvody": odvody,
            "poistky": poistky,
            "splatky_uverov": splatky_uverov,
            "domacnost": domacnost,
            "kurenie": kurenie,
            "mhd_autobus_vlak": mhd_autobus_vlak,
            "cigarety": cigarety,
            "ine": ine,
            "ine_naklady_byvanie": ine_naklady_byvanie,
            "auto_pohonne_hmoty": auto_pohonne_hmoty,
            "alkohol_loteria_zreby": alkohol_loteria_zreby,
            "telefon": telefon,
            "auto_servis_pzp_dialnicne_poplatky": auto_servis_pzp_dialnicne_poplatky,
            "volny_cas": volny_cas,
            "poznamky_vydavky": clean_text(poznamky_vydavky),
            "poznamky_prijmy": clean_text(poznamky_prijmy),
            "prijmy_domacnosti": _get_prijmy_data_for_save(),
            "uvery_df": st.session_state.uvery_df.to_dict('records') if not st.session_state.uvery_df.empty else [],
            "exekucie_df": _get_exekucie_data_for_save(),
            "nedoplatky_data": _get_nedoplatky_data_for_save(),
            "komentar_pracovnika_slsp": clean_text(komentar_pracovnika_slsp),
            "poznamky_dlhy": clean_text(poznamky_dlhy),
            "ai_action_plan": st.session_state.get("ai_action_plan", ""),
            "ai_conversation_history": st.session_state.get("ai_conversation_history", [])
        }
        
        # Auto-save when data changes
        prijmy_data_for_check = _get_prijmy_data_for_save()
        uvery_data_for_check = st.session_state.uvery_df.to_dict('records') if not st.session_state.uvery_df.empty else []
        exekucie_data_for_check = _get_exekucie_data_for_save()
        nedoplatky_data_for_check = _get_nedoplatky_data_for_save()

        # ==============================
        # AI Action Plan Section
        # ==============================
        background_color(
            background_color="#2870ed", 
            text_color="#ffffff", 
            header_text="Akčný plán", 
            text="AI-generovaný návrh riešenia na základe vyplnených údajov"
        )

        with st.container(border=True):
            # Initialize session state for AI action plan
            if "ai_action_plan" not in st.session_state:
                st.session_state.ai_action_plan = st.session_state.existing_data.get("ai_action_plan", "")
            if "ai_conversation_history" not in st.session_state:
                st.session_state.ai_conversation_history = st.session_state.existing_data.get("ai_conversation_history", [])
            if "ai_analysis_completed" not in st.session_state:
                st.session_state.ai_analysis_completed = bool(st.session_state.existing_data.get("ai_action_plan", ""))

            # Check if we have enough data for AI analysis
            has_minimal_data = (
                pribeh.strip() or riesenie.strip() or 
                len(prijmy_data_for_check) > 0 or
                len(uvery_data_for_check) > 0 or
                len(exekucie_data_for_check) > 0 or
                len(nedoplatky_data_for_check) > 0 or
                total_expenses > 0 or total_income > 0
            )

            if has_minimal_data:
                col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
                
                with col1:
                    st.markdown("**Generovanie akčného plánu**")
                    st.markdown("AI analyzuje vyplnené údaje a navrhuje riešenie na mieru pre klienta.")
                
                with col2:
                    if st.button("Generovať akčný plán", type="primary", use_container_width=True):
                        if not OPENAI_API_KEY:
                            st.error("❌ OpenAI API key nie je nakonfigurovaný. Kontaktujte administrátora.")
                        else:
                            with st.spinner("AI analyzuje údaje a generuje akčný plán..."):
                                try:
                                    # Format data for AI analysis
                                    zivotny_pribeh, domacnost_info, prijmy_text, vydavky_text, dlhy_text = format_form_data_for_ai(data_to_save)
                                    
                                    # Combine all information for AI
                                    tzs_history = f"Komentár pracovníka SLSP: {komentar_pracovnika_slsp}\n{domacnost_info}"
                                    zivotne_naklady = f"{prijmy_text}\n\n{vydavky_text}"
                                    uverove_prods = dlhy_text
                                    
                                    # Extract TZS history first
                                    tzs_count, tzs_result = extract_tzs_history(zivotny_pribeh, tzs_history)
                                    
                                    if tzs_count >= 2:
                                        # Go directly to comprehensive analysis (Phase 2)
                                        result = generate_action_plan(
                                            zivotny_pribeh,
                                            tzs_history,
                                            zivotne_naklady,
                                            uverove_prods,
                                            history=st.session_state.ai_conversation_history
                                        )
                                        st.session_state.ai_action_plan = f"**História ŤŽS**:\n{tzs_result}\n\n**Komplexné riešenie (Fáza 2)**:\n{result}"
                                    else:
                                        # Check if deferral is sufficient (Phase 1)
                                        deferral_result = check_deferral_sufficiency(
                                            zivotny_pribeh,
                                            tzs_history,
                                            zivotne_naklady,
                                            uverove_prods
                                        )
                                        
                                        if "Stačí odklad: Áno" in deferral_result:
                                            st.session_state.ai_action_plan = (
                                                f"**História ŤŽS**:\n{tzs_result}\n\n"
                                                f"**Výsledok analýzy odkladu splátok (Fáza 1)**:\n{deferral_result}"
                                            )
                                        else:
                                            # Move to Phase 2
                                            result = generate_action_plan(
                                                zivotny_pribeh,
                                                tzs_history,
                                                zivotne_naklady,
                                                uverove_prods,
                                                history=st.session_state.ai_conversation_history
                                            )
                                            st.session_state.ai_action_plan = (
                                                f"**História ŤŽS**:\n{tzs_result}\n\n"
                                                f"**Výsledok analýzy odkladu splátok (Fáza 1)**:\n{deferral_result}\n\n"
                                                f"**Komplexné riešenie (Fáza 2)**:\n{result}"
                                            )
                                    
                                    st.session_state.ai_analysis_completed = True
                                    st.success("✅ Akčný plán bol úspešne vygenerovaný!")
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Chyba pri generovaní akčného plánu: {str(e)}")
                                    st.session_state.ai_analysis_completed = False

                # Display the generated action plan
                if st.session_state.ai_action_plan:
                    st.markdown("---")
                    st.markdown("### 📋 Vygenerovaný akčný plán")
                    st.text_area(
                        "Akčný plán",
                        value=st.session_state.ai_action_plan,
                        height=600,
                        key="ai_action_plan_display",
                        label_visibility="collapsed"
                    )
                    
                    # Follow-up conversation option
                    st.markdown("---")
                    st.markdown("### 💬 Pokračovať v konverzácii s AI")
                    follow_up_input = st.text_area(
                        "Zadajte doplňujúcu otázku alebo pokračovanie:",
                        key="ai_follow_up_input",
                        height=100,
                        placeholder="Napríklad: Môžete upresniť riešenie pre konkrétny úver?"
                    )
                    
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("📤 Odoslať pokračovanie", use_container_width=True):
                            if follow_up_input.strip():
                                try:
                                    # Add follow-up question to history
                                    st.session_state.ai_conversation_history.append({
                                        "role": "user", 
                                        "content": follow_up_input
                                    })
                                    
                                    # Generate response with current history
                                    zivotny_pribeh, domacnost_info, prijmy_text, vydavky_text, dlhy_text = format_form_data_for_ai(data_to_save)
                                    tzs_history = f"Komentár pracovníka SLSP: {komentar_pracovnika_slsp}\n{domacnost_info}"
                                    zivotne_naklady = f"{prijmy_text}\n\n{vydavky_text}"
                                    uverove_prods = dlhy_text
                                    
                                    result = generate_follow_up_response(
                                        follow_up_input,
                                        zivotny_pribeh,
                                        tzs_history,
                                        zivotne_naklady,
                                        uverove_prods,
                                        history=st.session_state.ai_conversation_history
                                    )
                                    
                                    # Add assistant response to history
                                    st.session_state.ai_conversation_history.append({
                                        "role": "assistant", 
                                        "content": result
                                    })
                                    
                                    # Update action plan with follow-up response
                                    st.session_state.ai_action_plan += f"\n\n---\n\n**Doplňujúca otázka**: {follow_up_input}\n\n**Odpoveď AI**:\n{result}"
                                    st.success("✅ Odpoveď bola pridaná do akčného plánu!")
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Chyba pri spracovaní otázky: {str(e)}")
                            else:
                                st.warning("⚠️ Zadajte otázku pred odoslaním.")
                    
                    with col2:
                        if st.button("🔄 Resetovať konverzáciu", use_container_width=True):
                            st.session_state.ai_conversation_history = []
                            st.session_state.ai_action_plan = ""
                            st.session_state.ai_analysis_completed = False
                            st.success("✅ Konverzácia bola resetovaná!")
                            st.rerun()
            else:
                st.info("💡 Vyplňte základné údaje (príbeh, príjmy, výdavky alebo dlhy) pre generovanie akčného plánu.")
        
        has_data = (sap_id or email_zamestnanca or meno_priezvisko or 
                pribeh or riesenie or 
                pocet_clenov_domacnosti != 0 or typ_bydliska or domacnost_poznamky or 
                poznamky_prijmy or komentar_pracovnika_slsp or
                len(prijmy_data_for_check) > 0 or
                len(uvery_data_for_check) > 0 or
                len(exekucie_data_for_check) > 0 or
                len(nedoplatky_data_for_check) > 0 or
                poznamky_dlhy != "" or
                # Check if any expense field has been modified from its default value
                najom != default_najom or tv_internet != default_tv_internet or oblecenie_obuv != default_oblecenie_obuv or
                sporenie != default_sporenie or elektrina != default_elektrina or lieky_zdravie != default_lieky_zdravie or
                vydavky_na_deti != default_vydavky_na_deti or vyzivne != default_vyzivne or voda != default_voda or
                hygiena_kozmetika_drogeria != default_hygiena_kozmetika_drogeria or domace_zvierata != default_domace_zvierata or
                podpora_rodicov != default_podpora_rodicov or plyn != default_plyn or strava_potraviny != default_strava_potraviny or
                predplatne != default_predplatne or odvody != default_odvody or poistky != default_poistky or
                splatky_uverov != default_splatky_uverov or domacnost != default_domacnost or kurenie != default_kurenie or
                mhd_autobus_vlak != default_mhd_autobus_vlak or cigarety != default_cigarety or ine != default_ine or
                ine_naklady_byvanie != default_ine_naklady_byvanie or auto_pohonne_hmoty != default_auto_pohonne_hmoty or
                alkohol_loteria_zreby != default_alkohol_loteria_zreby or telefon != default_telefon or
                auto_servis_pzp_dialnicne_poplatky != default_auto_servis_pzp_dialnicne_poplatky or volny_cas != default_volny_cas)
    
       #st.write(data_to_save)
        if has_data:
            # Auto-save functionality
            db_manager = st.session_state.get("db_manager")
            if db_manager:
                save_status, save_message = auto_save_data(db_manager, cid, data_to_save)
            else:
                save_status, save_message = "error", "Database not connected"

            # Show auto-save status
            st.markdown("---")
            if save_status == "updated":
                st.success(f"🔄 {save_message}")
            elif save_status == "created":
                st.info(f"✨ {save_message}")
            elif save_status == "error":
                st.error(f"❌ {save_message}")
        else:
            st.markdown("---")
            st.info("💡 Enter some data to enable auto-save")
    
    elif cid.strip():
        st.markdown("---")
        st.info("💡 Kliknite na 'Vyhľadať' pre prístup k formuláru")
    else:
        st.markdown("---")
        st.info("💡 Vložte CID a kliknite na 'Vyhľadať' pre prístup k formuláru")

if __name__ == "__main__":
    main()