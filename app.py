import streamlit as st
import pandas as pd
import base64
import os
from PIL import Image
from pathlib import Path
from datetime import date


mini_logo_path = os.path.join(os.path.dirname(__file__), "static", "logo_mini.png")
logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")

mini_logo = Image.open(mini_logo_path)

st.set_page_config(
    page_title="Sociálna banka – Dotazník", 
    page_icon=mini_logo, 
    layout="wide")

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
    st.text_input(
        "Meno a priezvisko klienta:",
        key="meno_priezvisko"
    )
    st.text_input(
        "CID klienta:",
        key="cid"
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
    
    # Create predefined rows for different bank types
    bank_types = [
        "banka",
        "nebankovka", 
        "súkromné",
        "pôžička od rodiny/priateľov",
        "iné"
    ]
    
    uvery_data = pd.DataFrame({
        debts_columns["kde_som_si_pozical"]: bank_types,
        debts_columns["na_aky_ucel"]: [""] * 5,
        debts_columns["kedy_som_si_pozical"]: [""] * 5,
        debts_columns["urokova_sadzba"]: [0.0] * 5,
        debts_columns["kolko_som_si_pozical"]: [0.0] * 5,
        debts_columns["kolko_este_dlzim"]: [0.0] * 5,
        debts_columns["aku_mam_mesacnu_splatku"]: [0.0] * 5
    })
    
    # Configure column types for loans table
    uvery_column_config = {
        debts_columns["kde_som_si_pozical"]: st.column_config.SelectboxColumn(
            "Kde som si požičal?",
            help="Typ inštitúcie",
            options=bank_types,
            required=False
        ),
        debts_columns["na_aky_ucel"]: st.column_config.TextColumn(
            "Na aký účel?",
            help="Účel pôžičky",
            max_chars=200,
        ),
        debts_columns["kedy_som_si_pozical"]: st.column_config.TextColumn(
            "Kedy som si požičal?",
            help="Dátum alebo obdobie",
            max_chars=100,
        ),
        debts_columns["urokova_sadzba"]: st.column_config.NumberColumn(
            "Úroková sadzba?",
            help="Úroková sadzba v %",
            min_value=0,
            step=0.1,
            format="%.1f %%"
        ),
        debts_columns["kolko_som_si_pozical"]: st.column_config.NumberColumn(
            "Koľko som si požičal?",
            help="Pôvodná suma v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        ),
        debts_columns["kolko_este_dlzim"]: st.column_config.NumberColumn(
            "Koľko ešte dlžím?",
            help="Zostávajúca suma v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        ),
        debts_columns["aku_mam_mesacnu_splatku"]: st.column_config.NumberColumn(
            "Akú mám mesačnú splátku?",
            help="Mesačná splátka v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        )
    }
    
    edited_uvery = st.data_editor(
        uvery_data,
        column_config=uvery_column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="uvery_data",
        row_height=40
    )
    
    # Calculate totals for loans
    loan_total_borrowed = edited_uvery[debts_columns["kolko_som_si_pozical"]].sum()
    loan_total_remaining = edited_uvery[debts_columns["kolko_este_dlzim"]].sum()
    loan_total_monthly = edited_uvery[debts_columns["aku_mam_mesacnu_splatku"]].sum()
    
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
    
    execution_types = ["č.1", "č.2", "č.3", "č.4", "č.5"]
    
    exekucie_data = pd.DataFrame({
        "Číslo": execution_types,
        "Meno exekútora": [""] * 5,
        "Pre koho exekútor vymáha dlh?": [""] * 5,
        "Od kedy mám exekúciu?": [""] * 5,
        "Aktuálna výška exekúcie?": [0.0] * 5,
        "Akou sumou ju mesačne splácam?": [0.0] * 5
    })
    
    # Configure column types for executions table  
    exekucie_column_config = {
        "Číslo": st.column_config.TextColumn(
            "Číslo",
            help="Poradové číslo",
            disabled=True
        ),
        "Meno exekútora": st.column_config.TextColumn(
            "Meno exekútora",
            help="Meno exekútora",
            max_chars=200,
        ),
        "Pre koho exekútor vymáha dlh?": st.column_config.TextColumn(
            "Pre koho exekútor vymáha dlh?",
            help="Veriteľ",
            max_chars=200,
        ),
        "Od kedy mám exekúciu?": st.column_config.TextColumn(
            "Od kedy mám exekúciu?",
            help="Dátum začiatku exekúcie",
            max_chars=100,
        ),
        "Aktuálna výška exekúcie?": st.column_config.NumberColumn(
            "Aktuálna výška exekúcie?",
            help="Aktuálna suma v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        ),
        "Akou sumou ju mesačne splácam?": st.column_config.NumberColumn(
            "Akou sumou ju mesačne splácam?",
            help="Mesačná splátka v eurách",
            min_value=0,
            step=0.01,
            format="%.2f €"
        )
    }
    
    edited_exekucie = st.data_editor(
        exekucie_data,
        column_config=exekucie_column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="exekucie_data",
        row_height=40
    )
    
    # Calculate totals for executions
    execution_total_amount = edited_exekucie["Aktuálna výška exekúcie?"].sum()
    execution_total_monthly = edited_exekucie["Akou sumou ju mesačne splácam?"].sum()
    
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
    
    





