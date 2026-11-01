
"""
DataGuard: A data trust layer.

Start the app with:
    python -m streamlit run app.py

This file handles application configuration, sidebar navigation,
and shared user settings. Business logic lives in core/,
and individual pages live in views/.
"""

import streamlit as st

from core import config

# Must be called before any other Streamlit page content.
st.set_page_config(
    page_title="DataGuard | Data Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from views import (  # noqa: E402
    exceptions_page,
    health_page,
    overview_page,
    reconciliation_page,
    retail_page,
    rules_page,
)
from views.common import Context, get_workflow  # noqa: E402


# ---------------------------------------------------------
# PAGE REGISTRY
# ---------------------------------------------------------

PAGES = {
    "Overview": overview_page,
    "Reconciliation": reconciliation_page,
    "Exceptions": exceptions_page,
    "Quality Rules": rules_page,
    "Health & Alerts": health_page,
    "Retail Analytics": retail_page,
}


# ---------------------------------------------------------
# APPLICATION STYLING
# ---------------------------------------------------------


st.markdown(
    """
    <style>
    /* ==================================================
       DATAGUARD PREMIUM DESIGN SYSTEM
       Navy + Teal + Clean White
       ================================================== */

    :root {
        --dg-navy: #101B2D;
        --dg-navy-soft: #19283D;
        --dg-teal: #0D9488;
        --dg-teal-light: #CCFBF1;
        --dg-bg: #F3F6FA;
        --dg-card: #FFFFFF;
        --dg-text: #182438;
        --dg-muted: #64748B;
        --dg-border: #DCE4EE;
        --dg-radius: 16px;
        --dg-shadow: 0 5px 18px rgba(16, 27, 45, 0.055);
    }

    /* Main application background */
    .stApp {
        background: var(--dg-bg);
        color: var(--dg-text);
    }

    .block-container {
        max-width: 1600px;
        padding-top: 1.8rem;
        padding-bottom: 3rem;
    }

    /* Refined headings */
    h1, h2, h3 {
        color: var(--dg-navy) !important;
        letter-spacing: -0.035em;
        font-weight: 700 !important;
    }

    h1 {
        font-size: clamp(1.8rem, 3vw, 2.5rem) !important;
    }

    h2 {
        font-size: 1.55rem !important;
    }

    h3 {
        font-size: 1.2rem !important;
    }

    p, li, label {
        line-height: 1.6;
    }

    /* Premium dark sidebar */
    section[data-testid="stSidebar"] {
        background: var(--dg-navy);
        border-right: 1px solid #26364C;
    }

    section[data-testid="stSidebar"] > div {
        background: transparent;
        padding-top: 1.2rem;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #E7EDF5 !important;
    }

    section[data-testid="stSidebar"] hr {
        border-color: #34445A;
        margin: 1rem 0;
    }

    
/* Light-blue premium brand header */
section[data-testid="stSidebar"] h1 {
    background: linear-gradient(
        135deg,
        #DDF4FF 0%,
        #B9E5FA 55%,
        #A5DDF5 100%
    );
    color: #10243A !important;
    padding: 18px 14px;
    border-radius: 14px;
    border: 1px solid #D2EEFC;
    box-shadow: 0 5px 18px rgba(125, 211, 252, 0.16);
    margin-bottom: 12px;
}

/* Brand description */
section[data-testid="stSidebar"] h1 + div,
section[data-testid="stSidebar"] h1 + p {
    color: #D6E8F7 !important;
}

/* Soft blue highlight on hover */
section[data-testid="stSidebar"] h1:hover {
    box-shadow: 0 7px 22px rgba(125, 211, 252, 0.24);
    transition: box-shadow 180ms ease;
}


    /* Navigation radio items */
    section[data-testid="stSidebar"]
    div[role="radiogroup"] {
        gap: 0.35rem;
    }

    section[data-testid="stSidebar"]
    div[role="radiogroup"] > label {
        background: rgba(255, 255, 255, 0.035);
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 0.65rem 0.8rem;
        transition: background 180ms ease,
                    border-color 180ms ease,
                    transform 180ms ease;
    }

    section[data-testid="stSidebar"]
    div[role="radiogroup"] > label:hover {
        background: rgba(45, 212, 191, 0.10);
        border-color: rgba(45, 212, 191, 0.35);
        transform: translateX(2px);
    }

    /* Sidebar inputs remain easy to read */
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea {
        background: #FFFFFF !important;
        color: #182438 !important;
        border-radius: 9px !important;
    }

    section[data-testid="stSidebar"] [data-baseweb="select"] > div {
        border-radius: 9px;
    }

    /* KPI cards */
    [data-testid="stMetric"] {
        background: var(--dg-card);
        border: 1px solid var(--dg-border);
        border-radius: var(--dg-radius);
        padding: 1rem 1.1rem;
        box-shadow: var(--dg-shadow);
        transition: transform 180ms ease,
                    box-shadow 180ms ease,
                    border-color 180ms ease;
    }

    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: #A5DCD5;
        box-shadow: 0 9px 24px rgba(16, 27, 45, 0.09);
    }

    [data-testid="stMetricLabel"] {
        color: var(--dg-muted);
        font-size: 0.88rem;
        font-weight: 600;
    }

    [data-testid="stMetricValue"] {
        color: var(--dg-navy);
        font-weight: 750;
        letter-spacing: -0.035em;
    }

    /* White containers, expanders and tab content */
    [data-testid="stExpander"] {
        background: var(--dg-card);
        border: 1px solid var(--dg-border);
        border-radius: 12px;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: var(--dg-radius);
    }

    /* Buttons */
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 10px;
        font-weight: 650;
        min-height: 2.55rem;
        transition: transform 160ms ease,
                    box-shadow 160ms ease,
                    border-color 160ms ease;
    }

    .stButton > button[kind="primary"] {
        background: var(--dg-teal);
        border-color: var(--dg-teal);
        color: #FFFFFF;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 5px 14px rgba(13, 148, 136, 0.16);
        border-color: var(--dg-teal);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
        border-bottom: 1px solid var(--dg-border);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 9px 9px 0 0;
        padding: 0.65rem 1rem;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        color: var(--dg-teal) !important;
        border-bottom-color: var(--dg-teal) !important;
    }

    /* Tables */
    [data-testid="stDataFrame"],
    [data-testid="stTable"] {
        background: #FFFFFF;
        border: 1px solid var(--dg-border);
        border-radius: 12px;
        overflow: hidden;
    }

    /* Form controls */
    .stTextInput input,
    .stNumberInput input,
    .stTextArea textarea {
        border-radius: 9px;
    }

    [data-baseweb="select"] > div {
        border-radius: 9px;
    }

    /* Alerts and status messages */
    [data-testid="stAlert"] {
        border-radius: 12px;
        border-width: 1px;
    }

    /* Subtle entrance animation */
    @keyframes dg-fade-in {
        from {
            opacity: 0;
            transform: translateY(5px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .main .block-container {
        animation: dg-fade-in 320ms ease-out;
    }

    /* Responsive layout */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem 1rem 2rem;
        }

        [data-testid="stMetric"] {
            padding: 0.8rem;
        }
    }

    /* Respect reduced-motion accessibility settings */
    @media (prefers-reduced-motion: reduce) {
        *,
        *::before,
        *::after {
            animation-duration: 0.01ms !important;
            transition-duration: 0.01ms !important;
        }
    }

    
/* DataGuard premium KPI cards */
div[data-testid="stMetric"] {
    background: linear-gradient(
        145deg,
        #FFFFFF 0%,
        #F0F9FF 100%
    );
    border: 1px solid #D6EAF7;
    border-radius: 16px;
    padding: 18px 20px;
    box-shadow: 0 4px 14px rgba(31, 78, 121, 0.06);
    transition:
        transform 180ms ease,
        box-shadow 180ms ease,
        border-color 180ms ease;
}

/* Subtle hover animation */
div[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: #93CFEF;
    box-shadow: 0 9px 22px rgba(31, 78, 121, 0.12);
}

/* KPI labels */
div[data-testid="stMetricLabel"] {
    color: #52677D;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.045em;
}

/* KPI values */
div[data-testid="stMetricValue"] {
    color: #12304A;
    font-size: 1.8rem;
    font-weight: 800;
}

/* Respect reduced-motion preferences */
@media (prefers-reduced-motion: reduce) {
    div[data-testid="stMetric"] {
        transition: none;
    }

    div[data-testid="stMetric"]:hover {
        transform: none;
    }
}


/* DataGuard light-blue sidebar brand */
section[data-testid="stSidebar"] .dg-brand {
    background: linear-gradient(
        135deg,
        #DDF4FF 0%,
        #B9E5FA 55%,
        #A5DDF5 100%
    );
    border: 1px solid #C5E8F8;
    border-radius: 16px;
    padding: 18px 15px;
    margin-bottom: 20px;
    box-shadow: 0 5px 18px rgba(125, 211, 252, 0.16);
}

section[data-testid="stSidebar"] .dg-brand-title {
    color: #10243A;
    font-size: 1.55rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.3;
}

section[data-testid="stSidebar"] .dg-brand-subtitle {
    color: #20536C;
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    margin-top: 7px;
}

section[data-testid="stSidebar"] .dg-brand-description {
    color: #29475D;
    font-size: 0.84rem;
    line-height: 1.5;
    margin-top: 10px;
}

section[data-testid="stSidebar"] .dg-brand:hover {
    box-shadow: 0 8px 24px rgba(56, 139, 180, 0.22);
    transition: box-shadow 180ms ease;
}


    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# SIDEBAR AND SHARED SETTINGS
# ---------------------------------------------------------

def sidebar() -> tuple[str, Context]:
    """Render navigation and create the shared page context."""

    with st.sidebar:
        # Brand area
        
        st.markdown(
            """
            <div class="dg-brand">
                <div class="dg-brand-title">🛡️ DataGuard</div>
                <div class="dg-brand-subtitle">DATA INTELLIGENCE PLATFORM</div>
                <div class="dg-brand-description">
                    Monitor data quality, reconcile records, and investigate exceptions.
                </div>
            </div>
         """,
         unsafe_allow_html=True,
        )
 


        st.divider()

        # Application navigation
        st.markdown("### Workspace")

        page_name = st.radio(
            "Navigate to",
            options=list(PAGES.keys()),
            index=0,
            label_visibility="collapsed",
            key="dataguard_page_navigation",
        )

        st.divider()

        # Analyst settings
        st.markdown("### Analyst Settings")

        user = st.text_input(
            "Working as",
            value="analyst",
            max_chars=80,
            help=(
                "The analyst name is included in the audit log "
                "when you change a ticket."
            ),
            key="dataguard_analyst",
        )

        symbol = st.text_input(
            "Order currency symbol",
            value="₹",
            max_chars=3,
            help=(
                "Currency symbol used when displaying order amounts. "
                "This setting does not convert the underlying order data."
            ),
            key="dataguard_order_currency_symbol",
        )

        st.divider()

        # Retail currency settings
        st.markdown("### Retail Currency")

        currency_options = ["GBP", "INR"]
        default_currency = (
            "INR" if config.DISPLAY_CURRENCY == "INR" else "GBP"
        )

        currency = st.selectbox(
            "Display retail sales in",
            options=currency_options,
            index=currency_options.index(default_currency),
            help=(
                "Retail source data is in GBP. INR is a display conversion "
                "using the configured exchange rate; it does not change "
                "the original dataset."
            ),
            key="dataguard_retail_currency",
        )

        rate = st.number_input(
            "GBP to INR exchange rate",
            min_value=1.0,
            value=float(config.GBP_TO_INR),
            step=0.5,
            format="%.2f",
            disabled=(currency != "INR"),
            help=(
                "Enter the exchange rate to use for display conversion. "
                "This is a configurable rate, not a live market quote."
            ),
            key="dataguard_gbp_to_inr_rate",
        )

        st.divider()

        # Deployment notice
        st.markdown("### Deployment")
        st.caption(
            "Current mode: local application settings. "
            "This version does not provide user login or access control."
        )

        st.caption(
            "For shared company deployment, configure authentication, "
            "role-based permissions, and secure secrets management."
        )

        st.divider()
        st.caption("DataGuard · Data Quality & Reconciliation")

    # Validate and normalize shared settings.
    analyst_name = user.strip() or "analyst"
    currency_symbol = symbol.strip() or "₹"

    context = Context(
        user=analyst_name,
        symbol=currency_symbol,
        currency=currency,
        gbp_to_inr=float(rate),
        workflow=get_workflow(),
    )

    return page_name, context


# ---------------------------------------------------------
# APPLICATION ENTRY POINT
# ---------------------------------------------------------

page_name, ctx = sidebar()

# Each page continues to use its existing implementation.
PAGES[page_name].render(ctx)
