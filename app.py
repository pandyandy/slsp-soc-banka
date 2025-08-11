import streamlit as st
import pandas as pd
import base64
import os
import time

from PIL import Image
from datetime import date


mini_logo_path = os.path.join(os.path.dirname(__file__), "static", "logo_mini.png")
logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")

mini_logo = Image.open(mini_logo_path)

st.set_page_config(
    page_title="Sociálna banka – Dotazník", 
    page_icon=mini_logo, 
    layout="wide")

# Create fake data for pre-filling
fake_data = {
    "CID001": {
        "meno_priezvisko": "Ján Novák",
        "datum_narodenia": date(1985, 3, 15),
        "pocet_clenov_domacnosti": 4,
        "typ_bydliska": ["Byt", "Nájom"],
        "domacnost_poznamky": "4-členná rodina s dvoma deťmi",
        "pribeh": "Prišiel som o prácu počas pandémie. Manželka je na materskej dovolenke. Finančné problémy trvajú už 8 mesiacov.",
        "riesenie": "Potrebujeme pomoc s refinancovaním dlhov a hľadaním novej práce. Vedeli by sme splácať max 300€ mesačne."
    },
    "CID002": {
        "meno_priezvisko": "Mária Svobodová", 
        "datum_narodenia": date(1978, 11, 22),
        "pocet_clenov_domacnosti": 2,
        "typ_bydliska": ["Rodinný dom", "Ve vlastníctve"],
        "domacnost_poznamky": "Žijem s dcérou (15 rokov)",
        "pribeh": "Po rozvode som zostala sama s dcérou. Bývalý manžel neplatí výživné. Mám problém splácať hypotéku.",
        "riesenie": "Potrebujem pomoc s vymáhaním výživného a reštrukturalizáciou hypotéky. Vedela by som platiť 250€ mesačne."
    },
    "CID003": {
        "meno_priezvisko": "Peter Kováč",
        "datum_narodenia": date(1992, 7, 8), 
        "pocet_clenov_domacnosti": 1,
        "typ_bydliska": ["Byt", "Nájom"],
        "domacnost_poznamky": "Žijem sám",
        "pribeh": "Študoval som na vysokej škole a nahromadil dlhy. Po ukončení štúdia nemôžem nájsť prácu v odbore.",
        "riesenie": "Hľadám pomoc s konsolidáciou študentských pôžičiek. Mohol by som splácať 150€ mesačne po nájdení práce."
    }
}

# Function to load fake data
def load_fake_data(cid):
    if cid in fake_data:
        data = fake_data[cid]
        # Set session state values
        for key, value in data.items():
            st.session_state[key] = value

# Function to clear form data
def clear_form_data():
    keys_to_clear = [
        "meno_priezvisko", "datum_narodenia", "pocet_clenov_domacnosti", 
        "typ_bydliska", "domacnost_poznamky", "pribeh", "riesenie"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

# Initialize previous CID tracking
if "previous_cid" not in st.session_state:
    st.session_state.previous_cid = ""


def background_color(background_color, text_color, header_text, text=None):
     content = f'<div style="font-size:20px;margin:0px 0;">{header_text}</div>'
     if text:
        content += f'<div style="font-size:16px;margin-top:5px;">{text}</div>'
     
     st.markdown(f'<div style="background-color:{background_color};color:{text_color};border-radius:0px;padding:10px;margin:0px 0;">{content}</div>', unsafe_allow_html=True)

# Load and encode logo
with open(logo_path, "rb") as f:
    logo_data = base64.b64encode(f.read()).decode()

# Header container with logo
st.markdown(f"""
<div style="
    background-color: #2870ed; 
    padding: 20px; 
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
">
    <div style="color: white; font-size: 32px; font-weight: bold;">
        Sociálna banka – Dotazník
    </div>
    <div>
        <img src="data:image/png;base64,{logo_data}" style="height: 60px;" />
    </div>
</div>
""", unsafe_allow_html=True)

# basic info 
col1, col2 = st.columns(2)
with col1: 

    # CID selectbox with automatic data loading
    selected_cid = st.selectbox(
        "CID klienta:",
        options=[""] + list(fake_data.keys()),
        key="cid",
        help="Údaje sa načítajú automaticky po výbere CID"
    )
    
    # Auto-load data when CID changes
    if selected_cid != st.session_state.previous_cid:
        if selected_cid and selected_cid != "":
            load_fake_data(selected_cid)
        else:
            # Clear data when empty CID is selected
            clear_form_data()
        st.session_state.previous_cid = selected_cid
    
    st.text_input(
        "Meno a priezvisko klienta:",
        key="meno_priezvisko"
    )
    st.date_input(
        "Dátum narodenia:",
        min_value=date(1900, 1, 1),
        max_value="today",
        format="DD.MM.YYYY",
        key="datum_narodenia"
    )
with col2: 
    st.text_input(
        "SAP ID zamestnanca:",
        key="sap_id"
    )
    st.date_input(
        "Dnešný dátum:", 
        value="today",
        format="DD.MM.YYYY",
        key="dnesny_datum"
    )
""
background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="1. Príbeh klienta", 
    text="Ako ste sa dostali do finančných problémov? Čo sa zmenilo vo vašom živote? Situácia stále trvá alebo už je vyriešená?"
)
with st.container(border=True):
    st.text_area(
        "Príbeh klienta",
        label_visibility="collapsed",
        height=150,
        key="pribeh"
    )

background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="2. Riešenie podľa klienta", 
    text="Ako by ste chceli riešiť Vašu finančnú situáciu? Ako Vám môžeme pomôcť my? Koľko by ste vedeli mesačne splácať?"
)
with st.container(border=True):
    st.text_area(
        "Riešenie podľa klienta",
        label_visibility="collapsed",
        height=150,
        key="riesenie"
    )

background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="3. Domácnost", 
)
with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        st.number_input(
            "Počet členov domácnosti:",
            min_value=1,
            step=1,
            key="pocet_clenov_domacnosti"
        )
    with col2:
        st.multiselect(
            "Typ bydliska:",
            options=["Byt", "Rodinný dom", "Dvojgeneračná domácnosť", "Nájom", "Ve vlastníctve"],
            placeholder="Vyberte typ bydliska",
            key="typ_bydliska"
        )

    st.text_area(
        "Poznámky:", 
        height=75,
        key="domacnost_poznamky"
    )


# Create initial dataframe with the specified columns
column_names = {
    "kto": "Kto:",
    "tpp_brigada": "Čistý mesačný príjem (TPP, brigáda)",
    "podnikanie": "Čistý mesačný príjem z podnikania", 
    "socialne_davky": "Sociálne dávky (PN, dôchodok, rodičovský príspevok)",
    "ine": "Iné (výživné, podpora od rodiny)"
}

initial_data = pd.DataFrame({
    column_names["kto"]: [""],
    column_names["tpp_brigada"]: [0.0], 
    column_names["podnikanie"]: [0.0],
    column_names["socialne_davky"]: [0.0],
    column_names["ine"]: [0.0]
})

# Configure column types
column_config = {
    column_names["kto"]: st.column_config.TextColumn(
        "Kto:",
        help="Zadajte meno osoby",
        max_chars=100,
    ),
    column_names["tpp_brigada"]: st.column_config.NumberColumn(
        "Čistý mesačný príjem (TPP, brigáda)",
        help="Zadajte sumu v eurách",
        min_value=0,
        step=0.01,
        format="%.2f €"
    ),
    column_names["podnikanie"]: st.column_config.NumberColumn(
        "Čistý mesačný príjem z podnikania",
        help="Zadajte sumu v eurách", 
        min_value=0,
        step=0.01,
        format="%.2f €"
    ),
    column_names["socialne_davky"]: st.column_config.NumberColumn(
        "Sociálne dávky (PN, dôchodok, rodičovský príspevok)",
        help="Zadajte sumu v eurách",
        min_value=0,
        step=0.01,
        format="%.2f €"
    ),
    column_names["ine"]: st.column_config.NumberColumn(
        "Iné (výživné, podpora od rodiny)",
        help="Zadajte sumu v eurách",
        min_value=0,
        step=0.01,
        format="%.2f €"
    )
}
background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="4. Príjmy domácnosti", 
)
with st.container(border=True):
    edited_data = st.data_editor(
        initial_data,
        column_config=column_config,
        num_rows="dynamic",  # This allows adding/removing rows
        use_container_width=True,
        hide_index=True,
        row_height=40,
        key="prijmy_domacnosti"
    )

    # Calculate and display total
    income_columns = [column_names["tpp_brigada"], column_names["podnikanie"], column_names["socialne_davky"], column_names["ine"]]
    total_income = edited_data[income_columns].sum().sum()

    st.markdown(f"##### **Príjmy celkom: {total_income:.2f} €**")
    
    st.text_area(
        "Poznámky:",
        height=75,
        key="poznamky_prijmy"
    )

background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="5. Výdavky domácnosti", 
)
with st.container(border=True):


    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Nájom (bytosprávca, prenajímateľ):",
            step=1,
            key="najom"
        )

    with col2:
        st.number_input(
            "TV + Internet:",
            step=1,
            key="tv_internet"
        )

    with col3:
        st.number_input(
            "Oblečenie a obuv:",
            step=1,
            key="oblecenie_obuv"
        )

    with col4:
        st.number_input(
            "Sporenie:",
            step=1,
            key="sporenie"
        )

    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Elektrina:",
            step=1,
            key="elektrina"
        )
    with col2:
        st.number_input(
            "Lieky, zdravie a zdravotnícko pomôcky:",
            step=1,
            key="lieky_zdravie"
        )
    with col3:
        st.number_input(
            "Škôlka, škola, krúžky, družina, vreckové a iné výdavky na deti:",
            step=1,
            key="vydaje_na_deti"
        )
    with col4:
        st.number_input(
            "Výživné:",
            step=1,
            key="vyzivne"
        )

    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Voda:",
            step=1,
            key="voda"
        )
    with col2:
        st.number_input(
            "Hygiena, kozmetika a drogéria:",
            step=1,
            key="hygiena_kozmetika_drogeria"
        )
    with col3:
        st.number_input(
            "Domáce zvieratá:",
            step=1,
            key="domace_zvierata"
        )
    with col4:
        st.number_input(
            "Podpora rodičov, rodiny alebo iných osôb:",
            step=1,
            key="podpora_rodicov"
        )
    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Plyn:",
            step=1,
            key="plyn"
        )
    with col2:
        st.number_input(
            "Strava a potraviny:",
            step=1,
            key="strava_potraviny"
        )
    with col3:
        st.number_input(
            "Predplatné  (Tlač, aplikácie, permanentky, fitko apod.):",
            step=1,
            key="predplatne"
        )
    with col4:
        st.number_input(
            "Odvody (ak si ich platím sám):",
            step=1,
            key="odvody"
        )

    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Kúrenie:",
            step=1,
            key="kurenie"
        )
    with col2:
        st.number_input(
            "MHD, autobus, vlak:",
            step=1,
            key="mhd_autobus_vlak"
        )
    with col3:
        st.number_input(
            "Cigarety:",
            step=1,
            key="cigarety"
        )
    with col4:
        st.number_input(
            "Iné:",
            step=1,
            key="ine"
        )

    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Iné náklady na bývanie:",
            step=1,
            key="ine_naklady_byvanie"
        )
    with col2:
        st.number_input(
            "Auto – pohonné hmoty:",
            step=1,
            key="auto_pohonne_hmoty"
        )
    with col3:
        st.number_input(
            "Alkohol, lotéria, žreby, tipovanie, stávkovanie a herné automaty:",
            step=1,
            key="alkohol_loteria_zreby"
        )

    col1, col2, col3, col4 = st.columns(4, vertical_alignment="bottom")
    with col1:
        st.number_input(
            "Telefón:",
            step=1,
            key="telefon"
        )
    with col2:
        st.number_input(
            "Auto – servis, PZP, diaľničné poplatky:",
            step=1,
            key="auto_servis_pzp_dialnicne_poplatky"
        )
    with col3:
        st.number_input(
            "Volný čas a dovolenka:",
            step=1,
            key="volny_cas"
        )

    # Calculate total expenses
    expense_keys = [
        "najom", "tv_internet", "oblecenie_obuv", "sporenie",
        "elektrina", "lieky_zdravie", "vydaje_na_deti", "vyzivne",
        "voda", "hygiena_kozmetika_drogeria", "domace_zvierata", "podpora_rodicov",
        "plyn", "strava_potraviny", "predplatne", "odvody",
        "kurenie", "mhd_autobus_vlak", "cigarety", "ine",
        "ine_naklady_byvanie", "auto_pohonne_hmoty", "alkohol_loteria_zreby",
        "telefon", "auto_servis_pzp_dialnicne_poplatky", "volny_cas"
    ]
    
    total_expenses = sum(st.session_state.get(key, 0) for key in expense_keys)
    
    st.markdown(f"##### **Výdavky celkom: {total_expenses:.2f} €**")

    st.text_area(
        "Poznámky:",
        height=75,
        key="poznamky_vydavky"
    )
    
background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="6. Dlhy", 
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
    st.markdown("**ÚVERY**")

    # Define columns mapping (reuse existing headers)
    bank_types = [
        "banka",
        "nebankovka",
        "súkromné",
        "pôžička od rodiny/priateľov",
        "iné"
    ]
    bank_type_options = ["— Vyberte —"] + bank_types

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
        st.session_state.uvery_df = pd.DataFrame({
            uvery_columns["kde_som_si_pozical"]: pd.Series(dtype="string"),
            uvery_columns["na_aky_ucel"]: pd.Series(dtype="string"),
            uvery_columns["kedy_som_si_pozical"]: pd.Series(dtype="object"),  # store date objects
            uvery_columns["urokova_sadzba"]: pd.Series(dtype="float"),
            uvery_columns["kolko_som_si_pozical"]: pd.Series(dtype="float"),
            uvery_columns["kolko_este_dlzim"]: pd.Series(dtype="float"),
            uvery_columns["aku_mam_mesacnu_splatku"]: pd.Series(dtype="float"),
        })

    uvery_df = st.session_state.uvery_df

    # Controls row: Add / Edit / Delete via popovers and buttons
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 1], vertical_alignment="bottom")

    # Add new loan via popover form
    with ctrl_col1:
        with st.popover("Pridať úver", use_container_width=True):
            with st.form("uver_add_form", clear_on_submit=True):
                add_kde = st.selectbox(uvery_columns["kde_som_si_pozical"], options=bank_type_options, index=0)
                add_ucel = st.text_input(uvery_columns["na_aky_ucel"], value="")
                add_kedy = st.date_input(uvery_columns["kedy_som_si_pozical"], value=date.today(), format="DD.MM.YYYY")
                col_a, col_b = st.columns(2)
                with col_a:
                    add_urok = st.number_input(uvery_columns["urokova_sadzba"], min_value=0.0, max_value=100.0, step=0.1, value=0.0, format="%.1f")
                    add_pozical = st.number_input(uvery_columns["kolko_som_si_pozical"], min_value=0.0, step=0.01, value=0.0, format="%.2f")
                with col_b:
                    add_dlzim = st.number_input(uvery_columns["kolko_este_dlzim"], min_value=0.0, step=0.01, value=0.0, format="%.2f")
                    add_splatka = st.number_input(uvery_columns["aku_mam_mesacnu_splatku"], min_value=0.0, step=0.01, value=0.0, format="%.2f")
                submitted_add = st.form_submit_button("Uložiť úver", type="primary")
            if submitted_add:
                new_row = {
                    uvery_columns["kde_som_si_pozical"]: (add_kde if add_kde in bank_types else ""),
                    uvery_columns["na_aky_ucel"]: add_ucel,
                    uvery_columns["kedy_som_si_pozical"]: add_kedy,
                    uvery_columns["urokova_sadzba"]: float(add_urok) if add_urok is not None else 0.0,
                    uvery_columns["kolko_som_si_pozical"]: float(add_pozical) if add_pozical is not None else 0.0,
                    uvery_columns["kolko_este_dlzim"]: float(add_dlzim) if add_dlzim is not None else 0.0,
                    uvery_columns["aku_mam_mesacnu_splatku"]: float(add_splatka) if add_splatka is not None else 0.0,
                }
                st.session_state.uvery_df = pd.concat([st.session_state.uvery_df, pd.DataFrame([new_row])], ignore_index=True)
                st.success("Úver pridaný")
                st.rerun()

    # Select a row to edit/delete
    selected_row_index = None
    if not uvery_df.empty:
        with ctrl_col2:
            options = list(range(len(uvery_df)))
            def _format_row(i: int) -> str:
                try:
                    typ = uvery_df.iloc[i][uvery_columns["kde_som_si_pozical"]] or ""
                    ucel = uvery_df.iloc[i][uvery_columns["na_aky_ucel"]] or ""
                    return f"{i+1}. {typ} – {ucel}"
                except Exception:
                    return f"{i+1}. záznam"
            selected_row_index = st.selectbox(
                "Vybrať úver",
                options=options,
                index=0,
                format_func=_format_row,
                key="uvery_edit_select",
            )

        # Edit selected via popover form
        with ctrl_col3:
            with st.popover("Upraviť vybraný", use_container_width=True):
                if selected_row_index is not None and 0 <= selected_row_index < len(uvery_df):
                    row = uvery_df.iloc[selected_row_index]
                    with st.form("uver_edit_form"):
                        current_typ = row[uvery_columns["kde_som_si_pozical"]]
                        default_index = bank_types.index(current_typ) + 1 if current_typ in bank_types else 0
                        edit_kde = st.selectbox(uvery_columns["kde_som_si_pozical"], options=bank_type_options, index=default_index, key=f"edit_kde_{selected_row_index}")
                        edit_ucel = st.text_input(uvery_columns["na_aky_ucel"], value=str(row[uvery_columns["na_aky_ucel"]] or ""), key=f"edit_ucel_{selected_row_index}")
                        # Default date
                        default_date = row[uvery_columns["kedy_som_si_pozical"]]
                        if pd.isna(default_date) or default_date is None or default_date == "":
                            default_date = date.today()
                        edit_kedy = st.date_input(uvery_columns["kedy_som_si_pozical"], value=default_date, format="DD.MM.YYYY", key=f"edit_kedy_{selected_row_index}")
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            edit_urok = st.number_input(uvery_columns["urokova_sadzba"], min_value=0.0, max_value=100.0, step=0.1, value=float(row[uvery_columns["urokova_sadzba"]] or 0.0), format="%.1f", key=f"edit_urok_{selected_row_index}")
                            edit_pozical = st.number_input(uvery_columns["kolko_som_si_pozical"], min_value=0.0, step=0.01, value=float(row[uvery_columns["kolko_som_si_pozical"]] or 0.0), format="%.2f", key=f"edit_pozical_{selected_row_index}")
                        with col_e2:
                            edit_dlzim = st.number_input(uvery_columns["kolko_este_dlzim"], min_value=0.0, step=0.01, value=float(row[uvery_columns["kolko_este_dlzim"]] or 0.0), format="%.2f", key=f"edit_dlzim_{selected_row_index}")
                            edit_splatka = st.number_input(uvery_columns["aku_mam_mesacnu_splatku"], min_value=0.0, step=0.01, value=float(row[uvery_columns["aku_mam_mesacnu_splatku"]] or 0.0), format="%.2f", key=f"edit_splatka_{selected_row_index}")
                        submitted_edit = st.form_submit_button("Uložiť zmeny", type="primary")
                    if submitted_edit:
                        st.session_state.uvery_df.loc[selected_row_index, [
                            uvery_columns["kde_som_si_pozical"],
                            uvery_columns["na_aky_ucel"],
                            uvery_columns["kedy_som_si_pozical"],
                            uvery_columns["urokova_sadzba"],
                            uvery_columns["kolko_som_si_pozical"],
                            uvery_columns["kolko_este_dlzim"],
                            uvery_columns["aku_mam_mesacnu_splatku"],
                        ]] = [
                            (edit_kde if edit_kde in bank_types else ""),
                            edit_ucel,
                            edit_kedy,
                            float(edit_urok) if edit_urok is not None else 0.0,
                            float(edit_pozical) if edit_pozical is not None else 0.0,
                            float(edit_dlzim) if edit_dlzim is not None else 0.0,
                            float(edit_splatka) if edit_splatka is not None else 0.0,
                        ]
                        st.success("Zmeny uložené")
                        st.rerun()

        # Delete selected
        ctrl_col4, _ = st.columns([1, 3])
        with ctrl_col3:
            if st.button("Zmazať vybraný", type="secondary", use_container_width=True) and selected_row_index is not None and 0 <= selected_row_index < len(st.session_state.uvery_df):
                st.session_state.uvery_df = st.session_state.uvery_df.drop(index=selected_row_index).reset_index(drop=True)
                st.warning("Úver zmazaný")
                st.rerun()

    # Display current loans as a read-only table
    if uvery_df.empty:
        st.info("Zatiaľ nie sú pridané žiadne úvery.")
    else:
        st.dataframe(uvery_df, use_container_width=True, hide_index=True)

    # Calculate totals for loans from state
    loan_total_borrowed = uvery_df[uvery_columns["kolko_som_si_pozical"]].fillna(0).sum() if not uvery_df.empty else 0.0
    loan_total_remaining = uvery_df[uvery_columns["kolko_este_dlzim"]].fillna(0).sum() if not uvery_df.empty else 0.0
    loan_total_monthly = uvery_df[uvery_columns["aku_mam_mesacnu_splatku"]].fillna(0).sum() if not uvery_df.empty else 0.0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Celkom požičky: {loan_total_borrowed:.2f} €**")
    with col2:
        st.markdown(f"**Celkom dlhy: {loan_total_remaining:.2f} €**")
    with col3:
        st.markdown(f"**Splátky mesačne: {loan_total_monthly:.2f} €**")

    st.markdown("---")
    
    # Second table - EXEKÚCIE (Executions)
    st.markdown("**EXEKÚCIE**")

    # Initialize executions storage in session state
    if "exekucie_df" not in st.session_state:
        st.session_state.exekucie_df = pd.DataFrame({
            "Vybrať": pd.Series(dtype="bool"),
            "Číslo": pd.Series(dtype="string"),
            "Meno exekútora": pd.Series(dtype="string"),
            "Pre koho exekútor vymáha dlh?": pd.Series(dtype="string"),
            "Od kedy mám exekúciu?": pd.Series(dtype="string"),
            "Aktuálna výška exekúcie?": pd.Series(dtype="float"),
            "Akou sumou ju mesačne splácam?": pd.Series(dtype="float"),
        })

    # Ensure selection column exists for older sessions
    if "Vybrať" not in st.session_state.exekucie_df.columns:
        st.session_state.exekucie_df.insert(0, "Vybrať", False)

    def _renumber_exekucie_rows() -> None:
        if not st.session_state.exekucie_df.empty:
            st.session_state.exekucie_df["Číslo"] = [f"č.{i+1}" for i in range(len(st.session_state.exekucie_df))]

    # Controls: add / delete selected
    ctrl_ex1, ctrl_ex2 = st.columns([1, 1], vertical_alignment="bottom")
    with ctrl_ex1:
        if st.button("Pridať exekúciu", use_container_width=True):
            new_row = {
                "Vybrať": False,
                "Číslo": "",
                "Meno exekútora": "",
                "Pre koho exekútor vymáha dlh?": "",
                "Od kedy mám exekúciu?": "",
                "Aktuálna výška exekúcie?": 0.0,
                "Akou sumou ju mesačne splácam?": 0.0,
            }
            st.session_state.exekucie_df = pd.concat([st.session_state.exekucie_df, pd.DataFrame([new_row])], ignore_index=True)
            _renumber_exekucie_rows()
            st.rerun()

    with ctrl_ex2:
        if st.button("Zmazať vybranú", use_container_width=True):
            df = st.session_state.exekucie_df
            selected_idxs = df.index[df.get("Vybrať", False) == True].tolist()
            if len(selected_idxs) == 0:
                st.warning("Označte jeden riadok v tabuľke na zmazanie (stĺpec 'Vybrať').")
            elif len(selected_idxs) > 1:
                st.warning("Označte iba jeden riadok na zmazanie.")
            else:
                st.session_state.exekucie_df = df.drop(index=selected_idxs[0]).reset_index(drop=True)
                _renumber_exekucie_rows()
                st.rerun()

    # Editor for executions
    exekucie_column_config = {
        "Vybrať": st.column_config.CheckboxColumn("Vybrať"),
        "Číslo": st.column_config.TextColumn("Číslo", disabled=True),
        "Meno exekútora": st.column_config.TextColumn("Meno exekútora", max_chars=200),
        "Pre koho exekútor vymáha dlh?": st.column_config.TextColumn("Pre koho exekútor vymáha dlh?", max_chars=200),
        "Od kedy mám exekúciu?": st.column_config.TextColumn("Od kedy mám exekúciu?", max_chars=100),
        "Aktuálna výška exekúcie?": st.column_config.NumberColumn("Aktuálna výška exekúcie?", min_value=0, step=0.01, format="%.2f €"),
        "Akou sumou ju mesačne splácam?": st.column_config.NumberColumn("Akou sumou ju mesačne splácam?", min_value=0, step=0.01, format="%.2f €"),
    }

    # Order columns in the editor
    cols_order = [
        "Vybrať",
        "Číslo",
        "Meno exekútora",
        "Pre koho exekútor vymáha dlh?",
        "Od kedy mám exekúciu?",
        "Aktuálna výška exekúcie?",
        "Akou sumou ju mesačne splácam?",
    ]
    df_for_edit = st.session_state.exekucie_df.reindex(columns=cols_order)

    edited = st.data_editor(
        df_for_edit,
        column_config=exekucie_column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="exekucie_data",
        row_height=40,
    )
    st.session_state.exekucie_df = edited
    _renumber_exekucie_rows()

    # Calculate totals for executions
    df_ex = st.session_state.exekucie_df.copy()
    if not df_ex.empty:
        for col in ["Aktuálna výška exekúcie?", "Akou sumou ju mesačne splácam?"]:
            df_ex[col] = pd.to_numeric(df_ex[col], errors="coerce").fillna(0.0)
        execution_total_amount = float(df_ex["Aktuálna výška exekúcie?"].sum())
        execution_total_monthly = float(df_ex["Akou sumou ju mesačne splácam?"].sum())
    else:
        execution_total_amount = 0.0
        execution_total_monthly = 0.0

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Celkom exekúcie: {execution_total_amount:.2f} €**")
    with col2:
        st.markdown(f"**Splátky mesačne: {execution_total_monthly:.2f} €**")

    st.markdown("---")
    
    # Third table - NEDOPLATKY (Arrears)
    st.markdown("**NEDOPLATKY**")
    
    nedoplatky_categories = ["Bytosprávca", "Telefón", "Energie", "Zdravotná poisťovňa", "Soc. poisťovňa", "Pokuty, dane a pod."]
    
    nedoplatky_data = pd.DataFrame({
        "Kde mám nedoplatok?": nedoplatky_categories,
        "Od kedy mám nedoplatok?": [""] * 6,
        "V akej výške mám nedoplatok?": [0.0] * 6,
        "Akou sumou ho mesačne splácam?": [0.0] * 6
    })
    
    # Configure column types for arrears table
    nedoplatky_column_config = {
        "Kde mám nedoplatok?": st.column_config.TextColumn(
            "Kde mám nedoplatok?",
            help="Konkrétna inštitúcia",
            max_chars=200,
        ),
        "Od kedy mám nedoplatok?": st.column_config.TextColumn(
            "Od kedy mám nedoplatok?",
            help="Dátum vzniku nedoplatku",
            max_chars=100,
        ),
        "V akej výške mám nedoplatok?": st.column_config.NumberColumn(
            "V akej výške mám nedoplatok?",
            help="Suma nedoplatku v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        ),
        "Akou sumou ho mesačne splácam?": st.column_config.NumberColumn(
            "Akou sumou ho mesačne splácam?",
            help="Mesačná splátka v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        )
    }
    
    edited_nedoplatky = st.data_editor(
        nedoplatky_data,
        column_config=nedoplatky_column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="nedoplatky_data",
        row_height=40
    )
    
    # Calculate totals for arrears
    arrears_total_amount = edited_nedoplatky["V akej výške mám nedoplatok?"].sum()
    arrears_total_monthly = edited_nedoplatky["Akou sumou ho mesačne splácam?"].sum()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Celkom nedoplatky: {arrears_total_amount:.2f} €**")
    with col2:
        st.markdown(f"**Splátky mesačne: {arrears_total_monthly:.2f} €**")

    st.text_area(
        "Poznámky:",
        height=75,
        key="poznamky_dlhy"
    )

background_color(
    background_color="#2870ed", 
    text_color="#ffffff", 
    header_text="7. Akčný plán", 
)

with st.container(border=True):
    st.markdown("**Akčný plán**")
    
    # Create action plan dataframe
    akcny_plan_data = pd.DataFrame({
        "Text": [""] * 5,
        "Termín": [date.today()] * 5,
        "Poznámka": [""] * 5
    })
    
    # Configure column types for action plan table
    akcny_plan_column_config = {
        "Text": st.column_config.TextColumn(
            "Text",
            help="Popis úlohy alebo akcie",
            max_chars=500,
            width="large"
        ),
        "Termín": st.column_config.DateColumn(
            "Termín",
            help="Dátum alebo termín splnenia",
            format="DD.MM.YYYY",
            width="small"
        ),
        "Poznámka": st.column_config.TextColumn(
            "Poznámka",
            help="Dodatočné poznámky",
            max_chars=300,
            width="medium"
        )
    }
    
    edited_akcny_plan = st.data_editor(
        akcny_plan_data,
        column_config=akcny_plan_column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="akcny_plan_data",
        row_height=40
    )
    
    
_, _, _, col = st.columns(4)
with col:
    save = st.button(
        "Uložiť", 
        type="primary",
        use_container_width=True, 
        key="uloz")
    if save:
        with st.spinner("Ukládám...", show_time=True):
            time.sleep(3)
        st.success("Data boli úspešne uložené!")

