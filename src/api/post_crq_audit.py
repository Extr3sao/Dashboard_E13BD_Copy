import datetime
import logging
import html
import copy
import io
import os
import re
import sys
import time
import traceback
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors as rl_colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from src.api.post_crq_check11_ai import analyze_check11_results, merge_check11_ai_results
from src.api.post_crq_pipeline import (
    apply_ownership_to_check_rows_v2 as apply_ownership_to_check_rows,
    build_execution_context,
    build_execution_plan,
    build_finding_envelopes,
    build_report_model_v2 as build_report_model,
)
from src.core.check_explanation_catalog import load_check_explanation_catalog
from src.api.post_crq_scheduler import (
    SchedulerTask,
    classify_check_category,
    resolve_scheduler_config,
    run_scheduled_tasks,
    timeout_for_category,
)
from src.core.db_manager import OracleDBManager
from src.core.sqlite_paths import resolve_sqlite_path

logger = logging.getLogger(__name__)


TIME_COLUMN_HINTS = (
    "data_modificacio",
    "data_invalidacio",
    "data_creacio",
    "data_snapshot",
    "last_ddl_time",
    "last_updated",
    "updated_on",
    "timestamp",
    "date",
    "fecha",
)

def _parse_iso_dt(val: str, end: bool = False) -> Optional[datetime.datetime]:
    if not val or not str(val).strip():
        return None
    
    # Normalització
    val_orig = str(val)
    val = val_orig.strip().replace(" ", "T").replace("Z", "+00:00")
    
    try:
        if "T" in val:
            # Reintentem formats comuns directament amb strptime per evitar problemes segons versió Python
            try:
                if len(val) >= 16:
                    # YYYY-MM-DDTHH:MM
                    return datetime.datetime.strptime(val[:16], "%Y-%m-%dT%H:%M")
            except ValueError:
                pass
                
            try:
                if len(val) >= 19:
                    # YYYY-MM-DDTHH:MM:SS
                    return datetime.datetime.strptime(val[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass
                
            # fallback fromisoformat
            cleaned = val[:19] if "+" not in val else val
            return datetime.datetime.fromisoformat(cleaned)
        
        # Format YYYY-MM-DD
        d = datetime.date.fromisoformat(val[:10])
        t = datetime.time.max.replace(second=59, microsecond=0) if end else datetime.time.min
        return datetime.datetime.combine(d, t)
        
    except Exception as e:
        # Debugging: si falla en un lloc inesperat
        print(f"DEBUG: Error parsing ISO date '{val_orig}': {e}")
        try:
            # Últim recurs: només els primers 10 caràcters
            d = datetime.date.fromisoformat(val_orig[:10])
            t = datetime.time.max.replace(second=59, microsecond=0) if end else datetime.time.min
            return datetime.datetime.combine(d, t)
        except:
            return None


def _format_display_datetime(value: datetime.datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M")


def _format_display_time_range(*, start_raw: Any, end_raw: Any) -> str:
    start_text = str(start_raw or "").strip()
    end_text = str(end_raw or "").strip()
    if not start_text or not end_text:
        return "-"

    start_dt = _parse_iso_dt(start_text)
    end_dt = _parse_iso_dt(end_text, end=True)
    if not start_dt or not end_dt:
        return "-"

    return f"{_format_display_datetime(start_dt)} - {_format_display_datetime(end_dt)}"

CRITICALITY_ORDER = ("CRITIC", "MITJA", "BAIX")
CRITICALITY_DISPLAY = {
    "CRITIC": "Crític",
    "MITJA": "Mitjà",
    "BAIX": "Baix",
}
CRITICALITY_ACTIONS = {
    "CRITIC": "Acció bloquejadora: Cal resoldre aquesta incidència de forma immediata abans d'autoritzar qualsevol pas a producció, ja que compromet el rendiment o la integritat de la base de dades.",
    "MITJA": "Avís preventiu: S'exigeix la correcció d'aquesta anomalia en el proper cicle de desplegament o, com a màxim, en 15 dies per evitar la degradació progressiva del servei.",
    "BAIX": "Deute tècnic: S'ha de planificar la resolució d'aquest defecte menor durant els propers 30 dies per complir amb els estàndards òptims d'arquitectura Oracle.",
}

ENVIRONMENT_MESSAGES = {
    "E13BDA": "No es pot pujar aquest canvi a PRO.",
    "E13BDI": "No es pot pujar aquest canvi a PRO.",
    "E13BD": "Corregir urgentment!!!",
    "E13DBA": "No es pot pujar aquest canvi a PRO.",
    "E13DBI": "No es pot pujar aquest canvi a PRO.",
    "E13DB": "Corregir urgentment!!!",
}

DEFAULT_CHECK_CRITICALITY = {
    "CHECK_01": "MITJA",
    "CHECK_02": "BAIX",
    "CHECK_03": "CRITIC",
    "CHECK_04": "CRITIC",
    "CHECK_05": "MITJA",
    "CHECK_06": "MITJA",
    "CHECK_07": "CRITIC",
    "CHECK_08": "BAIX",
    "CHECK_09": "MITJA",
    "CHECK_10": "CRITIC",
    "CHECK_11": "MITJA",
}

ANNEX_CARD_BORDER = rl_colors.HexColor("#d7e2f3")
ANNEX_CARD_FILL = rl_colors.HexColor("#f7faff")


ANNEX_CHECK_GUIDANCE: Dict[str, Dict[str, str]] = {
    "CHECK_01": {
        "objectiu": "Verificar la presència de Primary Key en taules de nova creació per assegurar la integritat referencial i unicitat del model.",
        "impacte": "L'absència d'una PK impedeix garantir la unicitat, inhabilita l'optimitzador i trenca els fonaments del modelatge relacional. Condueix a duplicitat de registres i pèrdua de consistència de dades.",
        "possible_millora": "Avaluar l'exclusió de taules temporals globals (GTT) o taules de staging, on la unicitat no aporta valor funcional.",
        "limitacions": "El motor pot assenyalar falsos positius en mecanismes de càrrega massiva on s'omet temporalment la PK per operacions d'inserció ràpida.",
        "remediacio": "S'exigeix la creació d'una PRIMARY KEY robusta per a l'entitat o la justificació tècnica explícita documentada per l'omissió temporal.",
    },
    "CHECK_02": {
        "objectiu": "Supervisar taules sense cap índex per prevenir que accessos directes executin escanejos ineficients (Full Table Scans).",
        "impacte": "Consultes contra la taula buidaran excessivament el Buffer Cache de memòria i asfixiaran la I/O general de la base de dades a mesura que la taula creixi.",
        "possible_millora": "Incorporar dimensions de la taula (blocks) per ignorar alertes en taules catàleg o variables minúscules.",
        "limitacions": "Taules absolutament temporals d'us d'un sol pas poden considerar un defecte afegir un índex que ofegui les escriptures transaccionals.",
        "remediacio": "Avaluar els accessos comuns cap a la nova taula i dissenyar els índex corresponents per clàusules de discriminació de recerca i unions SQL.",
    },
    "CHECK_03": {
        "objectiu": "Controlar el dimensionament de la memòria cau (cache) a les seqüències del sistema per evitar problemes de contenció al diccionari de dades oracle.",
        "impacte": "Una seqüència NOCACHE utilitzada en ambients de gran volum bloqueja processos interns de control disparant els anclatges de memòria crònics ('row cache lock').",
        "possible_millora": "Creuar mètriques (AWR) per detectar el volum de col·lisions de crides abans de marcar un fals positiu administratiu.",
        "limitacions": "Pot alertar falsament en les sèries numerades de facturació legal inviolable on NOCACHE s'obliga governamentalment sobre la celeritat de la informàtica.",
        "remediacio": "Ajustar alter_sequence d'immediat pujant el CACHE entre 20 i extrems depenent l'accés. Mantenir fora de la visibilitat només aquelles que comprometen continuitat legislativa exacta.",
    },
    "CHECK_04": {
        "objectiu": "Garantir estructures segures en referències esclaves que bloquegen taules parentals de canvi.",
        "impacte": "Si el model parent actualitza registres o els destrueix i les Foreign Keys no tenen índex fill de suport Oracle executarà un temible Table Lock impedint operar completament tots els processos operatius amb concurrència desatesa.",
        "possible_millora": "Reconèixer compostos múltiples amb variables amagades si s'assumeix funcionalitat 'skip scan' de les cadenes laterals.",
        "limitacions": "Si les taules vinculades únicament admeten escriptures cap a dins sota històrics sense cap update de dades, la situació es tolera a fons.",
        "remediacio": "Acció de bloqueig absolut de pas a producció que precisa intervenció immediata resolent el problema mitjançant creació preventiva d'índex B-TREE dedicat per clau relacional.",
    },
    "CHECK_05": {
        "objectiu": "Verificar mecanismes i controls de bases dades vulnerats internament amb les restriccions desactivades.",
        "impacte": "Subverteix dramàticament l'esquema dissenyat deixant via lliure a que una aplicació introdueixi inconsistències a l'ecosistema sense previ avís.",
        "possible_millora": "Ignorar la crida només si forma part conscient per una fase estabilitzada d'ETL d'operació i que es troba a l'instant restautada correctament.",
        "limitacions": "Captura instàncies de procediments on càrregues ràpides directes 'APPEND' fan ús obligat de tancar regles de relació momentànies durant les importacions netes.",
        "remediacio": "Forçar restauració completa obligant un estatus 'VALIDATE' complet d'integritat o el descens auditat documentant per risc assumit en registres corromputs ocults.",
    },
    "CHECK_06": {
        "objectiu": "Manteniment òptim d'una economia d'emmagatzematge eficient minimitzant duplicats i encavalcaments del model analític i de cerca.",
        "impacte": "Un arbre indexat redundant destrueix de manera passiva qualsevol velocitat funcional de DML amb escriptures lentes de manera directa.",
        "possible_millora": "Incorporar observabilitat analitzant l'històric d'anells actius lligant plans concrets vinculants al nucli.",
        "limitacions": "Falsos reportats sota requeriments molt específics o particionats diferenciats amb optimitzacions localitzades per indexatges concrets sota sistemes separats paral·lels abstractes.",
        "remediacio": "Estudiar fons els índexs per avaluar un refactor integral i esborrament valent de cadascuna de les configuracions englobades més inofensives per simplificació relacional neta.",
    },
    "CHECK_07": {
        "objectiu": "Identificar procediments operacionals bloquejats i cadenes lògiques sense possibilitat d'interactuació funcional post pas a real.",
        "impacte": "Incapacitat crítica que provocarà de forma sobtada un missatge mort i errors d'execució als operadors finals, com ara excepcions 'ORA-04068' del pacot lògic principal.",
        "possible_millora": "Aplicar regles automàtiques de resolució i discriminació en memòria creuat per deutes tècnic amagats intocats ja avariats des del pas original.",
        "limitacions": "La situació provinent d'arquitectura caduca del client pot embrutar les anàlisis i demanar una depuració constant a brosses sense impacte immediat al producte actual canviat.",
        "remediacio": "Ajust forçós amb la resolució de de rutes i complir reajust automàtic compilat a través dels scripts rutinaris com l'eina utilitaria recompiladora 'UTL_RECOMP'.",
    },
    "CHECK_08": {
        "objectiu": "Auditar l'ús professional per declaració numèrica restringida com a bona pràctica tancada per garantir una homogeneïtat dels valors econòmics o analítics coneguts.",
        "impacte": "Absència d'escales pot ser el forat natural de trencaments fatals futurs pel sobre-amuntegament perillosíssim sobre dominis limitats no previstos d'espai desprotegit d'errors desmesuradament il·limitats.",
        "possible_millora": "Filtrat de metadades booleanitzades per discriminar o corregir dominis naturals amb xifres úniques on les variables ja s'haurien d'avaluar a CHAR(1) abans d'ocupar processadors.",
        "limitacions": "Càlculs oberts dinàmics tècnics poden no deixar mai ser quantificats formalment de forma prèvia impedint que això aporti certeses resolutives exactes de tall limitant tancat realment útil definit.",
        "remediacio": "Revisar totes les variables numèriques i atorgar per fixació prèvia domini exactes previstos de tancaments i valors econòmics esperats (Ex: NUMBER(15,2)).",
    },
    "CHECK_09": {
        "objectiu": "Validar traduccions funcionals captius virtualitzant per resolució que les dependència als destinataris finals reals vinculats compleixin funcions sense problemes a la crida remota properament referida.",
        "impacte": "Trencaments per errors d'autenticació ocult de components inestables i per errors mortals opacs que ataquen els processos cap als destinataris perduts per desfasaments operatius sense rastre aparent al client origen d'excepcions immediates (Translation is no longer valid).",
        "possible_millora": "Vigilar remotament en cadenes esteses multi entorns amb el control extra actiu als DBLINKS sobre distribucions allunyades d'arquitectura.",
        "limitacions": "La falsa interpretació dels controls pel pas virtual i problemes accessibilitats tancades i tallafocs que s'aïllen limitant totalment qualsevol evidència oberta a visió remota d'una situació natural corrent en el moment auditat post desplegat inicial de canvi.",
        "remediacio": "Reacondicionament i prova de resolució dels nodes cap als que crida la passarel·la verificant que destí i referència encara continuï vius de manera natural de connectivitat activa localment lligades o pel descart lliure l'abandonament final eliminat-ne i esborrant-ho d'inmediat de brossa sobrant sense sentit de connexió final cap lloc a de ser evitat i resolut de forma finalitzada.",
    },
    "CHECK_10": {
        "objectiu": "Revisar pràctiques anti-patró on una declarativa total i massiva absorbeix totes les fallides pel tancament a NULL en qualsevol circumstància d'execució d'interrogacions complexes.",
        "impacte": "Extremadament considerat negligència greu des del desenvolupament que aniquila silenciosa, cruelment i perillosament elements com alteracions o corrupcions i sense produir i deixar absolutament cap senyal operatiu on deuria avisar-a en cap moment trencant l'alerta vital a les traces de la pròpia resolució d'error transaccional d'integritat massiu globalitzat per a un silenci mortal de l'enginy Oracle de processament i registre auditiu a tota traça possible existent que faria caure fatalment la identificació post mortal loggica o investigacions i depuracions post desastre.",
        "possible_millora": "Control amb exempció selectives on ja inclòs logging global registratiu del mateix error tot redirigint flux cap un diposit i aixecant nou rastre propi del tractat per tal de no demanar alces extres i repetits pel check auditat de control originalment marcat l'event amb justificada base.",
        "limitacions": "Captura instàncies de procediments on esquemes d'utilitats de l'estacionari de seleccions de variable que per excepció requereixen de manera purista una devolució buida en controls menuts que de fet control per funcionalitat obligatoris concrets definits així prèviament o codis morts o sobrants residuals inofensius antics històrics però presents heretats.",
        "remediacio": "Avançar la reescriptura lliurant a controls l'avís necessari i registrar adequat als registres funcionals de incidències la captura general delegant així amunt el cas fora d'aïllar pel tractaments del rebot amunt i finalitzar RAISE puristes generals tractats i validats no buits sempre i en qualsevol moment que el marc requereix evidenciar els possibles problematitzades i trencades i desastre derivatiu sense cap encobriment l'estabilitat i seguretat general del tractaments codificats amb dades importants del cicle transaccional operatiu del dia.",
    },
    "CHECK_11": {
        "objectiu": "Detectar de forma contundent i precoç l'anti-patró extremadament perillós referent als loops transaccionals on les escriptures transcorren de cicle manual a fila a fila massius evitant les tècniques òptimes oracles de processos d'alta freqüència.",
        "impacte": "La iteració pura i senzilla sobre volum perillós produeix per conseqüència el salt recurrent continu de motor context entre les passes de control procedural cap el SQL i el PLSQL el que dispara exponencial els pics extrems CPU innecessari asfixiant la memòria pel tractat general i saturant bloquejant el manteniment normal col·lapsant altes càrregues i ofegants els tractaments ordinaris en grans problemàtiques.",
        "possible_millora": "Engegar filtres intel·ligents per excloure els tractaments petits per aïllament on l'entitat mai preveu volumetries fortes evitant generar crides innecessaris on dades no passin les desena d'unitats sent llavors acceptable per senzilles o d'us esporàdic i estacials concrets puntual del moment limitats poc important cap incidència real.",
        "limitacions": "Alertes generalistes produïdes freqüents que marquen codi heretat complex pel processat paral·lel on el bucle i aïllament lògic de dades particulars fa més difícil agafar agrupaments tancats fàcil forçant per excepcions funcinals de cada cicle del la llista processos altament manuals únics sense capacitat agrupar al tractat transaccional homogeni i continu ràpid globalitzants del paquet grupal sencer del procediment de la matèria dels registres de l'oracle de codi per talls individuals molt aïllats per entitats o per validacions molt especifiques heterogènies i que es fan amb lògiques creuades que s'escapen de la llista forall regular en bloc senzill d'agrupades clares globals que facilitaria a priori l'eina.",
        "remediacio": "Convertir per mètodes bulk en tractament sencer la rutina transaccional lenta transformant a mecanisme BULK COLLECT pel processat o per utilitats FORALL quan s'injecten les instruccions de manera totalment contundent i per agilitzar milers cicles per unitats grupals massives de rendiment multiplicadors sota estructures professionals.",
    },
}


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_post_crq_cover_path() -> Path | None:
    candidates = [
        Path(_project_root()) / "logo" / "portada.png",
        Path(_project_root()) / "portada.png",
        Path(_project_root()) / "assets" / "portada.png",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def resolve_post_crq_markdown_path() -> str:
    root = _project_root()
    candidates = [
        "Auditoria_post_crq.md",
        "auditoria_post_crq.md",
        "AUDITORIA_POST_CRQ.md",
    ]
    for candidate in candidates:
        path = os.path.join(root, candidate)
        if os.path.isfile(path):
            return path

    for name in os.listdir(root):
        lower_name = name.casefold()
        if lower_name.endswith(".md") and "post" in lower_name and "crq" in lower_name:
            path = os.path.join(root, name)
            if os.path.isfile(path):
                return path

    raise FileNotFoundError("No s'ha trobat el fitxer Auditoria_post_crq.md")


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_key(value: str) -> str:
    text = _normalize_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    replacements = {
        "ÃƒÂ ": "a",
        "ÃƒÂ¡": "a",
        "ÃƒÂ¨": "e",
        "ÃƒÂ©": "e",
        "ÃƒÂ­": "i",
        "ÃƒÂ¯": "i",
        "ÃƒÂ²": "o",
        "ÃƒÂ³": "o",
        "ÃƒÂº": "u",
        "ÃƒÂ¼": "u",
        "ÃƒÂ§": "c",
    }
    for source, target in replacements.items():
        text = text.replace(source, target).replace(source.upper(), target.upper())
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")
def _safe_xml(value: Any) -> str:
    if not value and value != 0:
        return "-"
    text = _fix_encoding(value) if isinstance(value, str) else str(value)
    escaped = html.escape(text, quote=True)

    result = []
    for c in escaped:
        o = ord(c)
        if o < 32:
            if o in (10, 13):
                result.append(c)
            elif o == 9:
                result.append("    ")
            else:
                continue
        else:
            result.append(c)

    final_text = "".join(result)
    return final_text.replace("\n", "<br/>").replace("\r", "")
CRITICALITY_ACTIONS = {
    "CRITIC": "Acció bloquejadora: Cal resoldre aquesta incidència de forma immediata abans d'autoritzar qualsevol pas a producció, ja que compromet el rendiment o la integritat de la base de dades.",
    "MITJA": "Avís preventiu: S'exigeix la correcció d'aquesta anomalia en el proper cicle de desplegament o, com a màxim, en 15 dies per evitar la degradació progressiva del servei.",
    "BAIX": "Deute tècnic: S'ha de planificar la resolució d'aquest defecte menor durant els propers 30 dies per complir amb els estàndards òptims d'arquitectura Oracle.",
}
ENVIRONMENT_MESSAGES = {
    "E13BDA": "No es pot pujar aquest canvi a PRO.",
    "E13BDI": "No es pot pujar aquest canvi a PRO.",
    "E13BD": "Corregir urgentment!!!",
    "E13DBA": "No es pot pujar aquest canvi a PRO.",
    "E13DBI": "No es pot pujar aquest canvi a PRO.",
    "E13DB": "Corregir urgentment!!!",
}

DEFAULT_CHECK_CRITICALITY = {
    "CHECK_01": "MITJA",
    "CHECK_02": "BAIX",
    "CHECK_03": "CRITIC",
    "CHECK_04": "CRITIC",
    "CHECK_05": "MITJA",
    "CHECK_06": "MITJA",
    "CHECK_07": "CRITIC",
    "CHECK_08": "BAIX",
    "CHECK_09": "MITJA",
    "CHECK_10": "CRITIC",
    "CHECK_11": "MITJA",
}

ANNEX_CARD_BORDER = rl_colors.HexColor("#d7e2f3")
ANNEX_CARD_FILL = rl_colors.HexColor("#f7faff")
PDF_BRAND_NAVY = rl_colors.HexColor("#0f2745")
PDF_BRAND_BLUE = rl_colors.HexColor("#1e4f91")
PDF_BRAND_SKY = rl_colors.HexColor("#d9e8f7")
PDF_BRAND_LINE = rl_colors.HexColor("#c9d7e8")
PDF_SOFT_FILL = rl_colors.HexColor("#f7fafc")
PDF_SOFT_ALT = rl_colors.HexColor("#edf4fb")
PDF_MUTED_TEXT = rl_colors.HexColor("#5f6f82")
PDF_CRITICAL_FILL = rl_colors.HexColor("#fee2e2")
PDF_MEDIUM_FILL = rl_colors.HexColor("#fef3c7")
PDF_LOW_FILL = rl_colors.HexColor("#dcfce7")


ANNEX_CHECK_GUIDANCE: Dict[str, Dict[str, str]] = {
    "CHECK_01": {
        "objectiu": "Verificar la presència de Primary Key en taules de nova creació per assegurar la integritat referencial i unicitat del model.",
        "impacte": "L'absència d'una PK impedeix garantir la unicitat, inhabilita l'optimitzador i trenca els fonaments del modelatge relacional. Condueix a duplicitat de registres i pèrdua de consistència de dades.",
        "possible_millora": "Avaluar l'exclusió de taules temporals globals (GTT) o taules de staging, on la unicitat no aporta valor funcional.",
        "limitacions": "El motor pot assenyalar falsos positius en mecanismes de càrrega massiva on s'omet temporalment la PK per operacions d'inserció ràpida.",
        "remediacio": "S'exigeix la creació d'una PRIMARY KEY robusta per a l'entitat o la justificació tècnica explícita documentada per l'omissió temporal.",
    },
    "CHECK_02": {
        "objectiu": "Supervisar taules sense cap índex per prevenir que accessos directes executin escanejos ineficients (Full Table Scans).",
        "impacte": "Consultes contra la taula buidaran excessivament el Buffer Cache de memòria i asfixiaran la I/O general de la base de dades a mesura que la taula creixi.",
        "possible_millora": "Incorporar dimensions de la taula (blocks) per ignorar alertes en taules catàleg o variables minúscules.",
        "limitacions": "Taules absolutament temporals d'us d'un sol pas poden considerar un defecte afegir un índex que ofegui les escriptures transaccionals.",
        "remediacio": "Avaluar els accessos comuns cap a la nova taula i dissenyar els índex corresponents per clàusules de discriminació de recerca i unions SQL.",
    },
    "CHECK_03": {
        "objectiu": "Controlar el dimensionament de la memòria cau (cache) a les seqüències del sistema per evitar problemes de contenció al diccionari de dades oracle.",
        "impacte": "Una seqüència NOCACHE utilitzada en ambients de gran volum bloqueja processos interns de control disparant els anclatges de memòria crònics ('row cache lock').",
        "possible_millora": "Creuar mètriques (AWR) per detectar el volum de col·lisions de crides abans de marcar un fals positiu administratiu.",
        "limitacions": "Pot alertar falsament en les sèries numerades de facturació legal inviolable on NOCACHE s'obliga governamentalment sobre la celeritat de la informàtica.",
        "remediacio": "Ajustar alter_sequence d'immediat pujant el CACHE entre 20 i extrems depenent l'accés. Mantenir fora de la visibilitat només aquelles que comprometen continuitat legislativa exacta.",
    },
    "CHECK_04": {
        "objectiu": "Garantir estructures segures en referències esclaves que bloquegen taules parentals de canvi.",
        "impacte": "Si el model parent actualitza registres o els destrueix i les Foreign Keys no tenen índex fill de suport Oracle executarà un temible Table Lock impedint operar completament tots els processos operatius amb concurrència desatesa.",
        "possible_millora": "Reconèixer compostos múltiples amb variables amagades si s'assumeix funcionalitat 'skip scan' de les cadenes laterals.",
        "limitacions": "Si les taules vinculades únicament admeten escriptures cap a dins sota històrics sense cap update de dades, la situació es tolera a fons.",
        "remediacio": "Acció de bloqueig absolut de pas a producció que precisa intervenció immediata resolent el problema mitjançant creació preventiva d'índex B-TREE dedicat per clau relacional.",
    },
    "CHECK_05": {
        "objectiu": "Verificar mecanismes i controls de bases dades vulnerats internament amb les restriccions desactivades.",
        "impacte": "Subverteix dramàticament l'esquema dissenyat deixant via lliure a que una aplicació introdueixi inconsistències a l'ecosistema sense previ avís.",
        "possible_millora": "Ignorar la crida només si forma part conscient per una fase estabilitzada d'ETL d'operació i que es troba a l'instant restautada correctament.",
        "limitacions": "Captura instàncies de procediments on càrregues ràpides directes 'APPEND' fan ús obligat de tancar regles de relació momentànies durant les importacions netes.",
        "remediacio": "Forçar restauració completa obligant un estatus 'VALIDATE' complet d'integritat o el descens auditat documentant per risc assumit en registres corromputs ocults.",
    },
    "CHECK_06": {
        "objectiu": "Manteniment òptim d'una economia d'emmagatzematge eficient minimitzant duplicats i encavalcaments del model analític i de cerca.",
        "impacte": "Un arbre indexat redundant destrueix de manera passiva qualsevol velocitat funcional de DML amb escriptures lentes de manera directa.",
        "possible_millora": "Incorporar observabilitat analitzant l'històric d'anells actius lligant plans concrets vinculants al nucli.",
        "limitacions": "Falsos reportats sota requeriments molt específics o particionats diferenciats amb optimitzacions localitzades per indexatges concrets sota sistemes separats paral·lels abstractes.",
        "remediacio": "Estudiar fons els índexs per avaluar un refactor integral i esborrament valent de cadascuna de les configuracions englobades més inofensives per simplificació relacional neta.",
    },
    "CHECK_07": {
        "objectiu": "Identificar procediments operacionals bloquejats i cadenes lògiques sense possibilitat d'interactuació funcional post pas a real.",
        "impacte": "Incapacitat crítica que provocarà de forma sobtada un missatge mort i errors d'execució als operadors finals, com ara excepcions 'ORA-04068' del pacot lògic principal.",
        "possible_millora": "Aplicar regles automàtiques de resolució i discriminació en memòria creuat per deutes tècnic amagats intocats ja avariats des del pas original.",
        "limitacions": "La situació provinent d'arquitectura caduca del client pot embrutar les anàlisis i demanar una depuració constant a brosses sense impacte immediat al producte actual canviat.",
        "remediacio": "Ajust forçós amb la resolució de de rutes i complir reajust automàtic compilat a través dels scripts rutinaris com l'eina utilitaria recompiladora 'UTL_RECOMP'.",
    },
    "CHECK_08": {
        "objectiu": "Auditar l'ús professional per declaració numèrica restringida com a bona pràctica tancada per garantir una homogeneïtat dels valors econòmics o analítics coneguts.",
        "impacte": "Absència d'escales pot ser el forat natural de trencaments fatals futurs pel sobre-amuntegament perillosíssim sobre dominis limitats no previstos d'espai desprotegit d'errors desmesuradament il·limitats.",
        "possible_millora": "Filtrat de metadades booleanitzades per discriminar o corregir dominis naturals amb xifres úniques on les variables ja s'haurien d'avaluar a CHAR(1) abans d'ocupar processadors.",
        "limitacions": "Càlculs oberts dinàmics tècnics poden no deixar mai ser quantificats formalment de forma prèvia impedint que això aporti certeses resolutives exactes de tall limitant tancat realment útil definit.",
        "remediacio": "Revisar totes les variables numèriques i atorgar per fixació prèvia domini exactes previstos de tancaments i valors econòmics esperats (Ex: NUMBER(15,2)).",
    },
    "CHECK_09": {
        "objectiu": "Validar traduccions funcionals captius virtualitzant per resolució que les dependència als destinataris finals reals vinculats compleixin funcions sense problemes a la crida remota properament referida.",
        "impacte": "Trencaments per errors d'autenticació ocult de components inestables i per errors mortals opacs que ataquen els processos cap als destinataris perduts per desfasaments operatius sense rastre aparent al client origen d'excepcions immediates (Translation is no longer valid).",
        "possible_millora": "Vigilar remotament en cadenes esteses multi entorns amb el control extra actiu als DBLINKS sobre distribucions allunyades d'arquitectura.",
        "limitacions": "La falsa interpretació dels controls pel pas virtual i problemes accessibilitats tancades i tallafocs que s'aïllen limitant totalment qualsevol evidència oberta a visió remota d'una situació natural corrent en el moment auditat post desplegat inicial de canvi.",
        "remediacio": "Reacondicionament i prova de resolució dels nodes cap als que crida la passarel·la verificant que destí i referència encara continuï vius de manera natural de connectivitat activa localment lligades o pel descart lliure l'abandonament final eliminat-ne i esborrant-ho d'inmediat de brossa sobrant sense sentit de connexió final cap lloc a de ser evitat i resolut de forma finalitzada.",
    },
    "CHECK_10": {
        "objectiu": "Revisar pràctiques anti-patró on una declarativa total i massiva absorbeix totes les fallides pel tancament a NULL en qualsevol circumstància d'execució d'interrogacions complexes.",
        "impacte": "Extremadament considerat negligència greu des del desenvolupament que aniquila silenciosa, cruelment i perillosament elements com alteracions o corrupcions i sense produir i deixar absolutament cap senyal operatiu on deuria avisar-a en cap moment trencant l'alerta vital a les traces de la pròpia resolució d'error transaccional d'integritat massiu globalitzat per a un silenci mortal de l'enginy Oracle de processament i registre auditiu a tota traça possible existent que faria caure fatalment la identificació post mortal loggica o investigacions i depuracions post desastre.",
        "possible_millora": "Control amb exempció selectives on ja inclòs logging global registratiu del mateix error tot redirigint flux cap un diposit i aixecant nou rastre propi del tractat per tal de no demanar alces extres i repetits pel check auditat de control originalment marcat l'event amb justificada base.",
        "limitacions": "Captura instàncies de procediments on esquemes d'utilitats de l'estacionari de seleccions de variable que per excepció requereixen de manera purista una devolució buida en controls menuts que de fet control per funcionalitat obligatoris concrets definits així prèviament o codis morts o sobrants residuals inofensius antics històrics però presents heretats.",
        "remediacio": "Avançar la reescriptura lliurant a controls l'avís necessari i registrar adequat als registres funcionals de incidències la captura general delegant així amunt el cas fora d'aïllar pel tractaments del rebot amunt i finalitzar RAISE puristes generals tractats i validats no buits sempre i en qualsevol moment que el marc requereix evidenciar els possibles problematitzades i trencades i desastre derivatiu sense cap encobriment l'estabilitat i seguretat general del tractaments codificats amb dades importants del cicle transaccional operatiu del dia.",
    },
    "CHECK_11": {
        "objectiu": "Detectar de forma contundent i precoç l'anti-patró extremadament perillós referent als loops transaccionals on les escriptures transcorren de cicle manual a fila a fila massius evitant les tècniques òptimes oracles de processos d'alta freqüència.",
        "impacte": "La iteració pura i senzilla sobre volum perillós produeix per conseqüència el salt recurrent continu de motor context entre les passes de control procedural cap el SQL i el PLSQL el que dispara exponencial els pics extrems CPU innecessari asfixiant la memòria pel tractat general i saturant bloquejant el manteniment normal col·lapsant altes càrregues i ofegants els tractaments ordinaris en grans problemàtiques.",
        "possible_millora": "Engegar filtres intel·ligents per excloure els tractaments petits per aïllament on l'entitat mai preveu volumetries fortes evitant generar crides innecessaris on dades no passin les desena d'unitats sent llavors acceptable per senzilles o d'us esporàdic i estacials concrets puntual del moment limitats poc important cap incidència real.",
        "limitacions": "Alertes generalistes produïdes freqüents que marquen codi heretat complex pel processat paral·lel on el bucle i aïllament lògic de dades particulars fa més difícil agafar agrupaments tancats fàcil forçant per excepcions funcinals de cada cicle del la llista processos altament manuals únics sense capacitat agrupar al tractat transaccional homogeni i continu ràpid globalitzants del paquet grupal sencer del procediment de la matèria dels registres de l'oracle de codi per talls individuals molt aïllats per entitats o per validacions molt especifiques heterogènies i que es fan amb lògiques creuades que s'escapen de la llista forall regular en bloc senzill d'agrupades clares globals que facilitaria a priori l'eina.",
        "remediacio": "Convertir per mètodes bulk en tractament sencer la rutina transaccional lenta transformant a mecanisme BULK COLLECT pel processat o per utilitats FORALL quan s'injecten les instruccions de manera totalment contundent i per agilitzar milers cicles per unitats grupals massives de rendiment multiplicadors sota estructures professionals.",
    },
}


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_post_crq_cover_path() -> Path | None:
    candidates = [
        Path(_project_root()) / "logo" / "portada.png",
        Path(_project_root()) / "portada.png",
        Path(_project_root()) / "assets" / "portada.png",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def resolve_post_crq_markdown_path() -> str:
    root = _project_root()
    candidates = [
        "Auditoria_post_crq.md",
        "auditoria_post_crq.md",
        "AUDITORIA_POST_CRQ.md",
    ]
    for candidate in candidates:
        path = os.path.join(root, candidate)
        if os.path.isfile(path):
            return path

    for name in os.listdir(root):
        lower_name = name.casefold()
        if lower_name.endswith(".md") and "post" in lower_name and "crq" in lower_name:
            path = os.path.join(root, name)
            if os.path.isfile(path):
                return path

    raise FileNotFoundError("No s'ha trobat el fitxer Auditoria_post_crq.md")


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_key(value: str) -> str:
    text = _normalize_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    replacements = {
        "ÃƒÂ ": "a",
        "ÃƒÂ¡": "a",
        "ÃƒÂ¨": "e",
        "ÃƒÂ©": "e",
        "ÃƒÂ­": "i",
        "ÃƒÂ¯": "i",
        "ÃƒÂ²": "o",
        "ÃƒÂ³": "o",
        "ÃƒÂº": "u",
        "ÃƒÂ¼": "u",
        "ÃƒÂ§": "c",
    }
    for source, target in replacements.items():
        text = text.replace(source, target).replace(source.upper(), target.upper())
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")
def _safe_xml(value: Any) -> str:
    if not value and value != 0:
        return "-"
    text = _fix_encoding(value) if isinstance(value, str) else str(value)
    # Escapem HTML reservats primer
    escaped = html.escape(text, quote=True)
    
    # Netegem caràcters de control invisibles (<32) exceptant tab/newline
    # i convertim tildes/accents a entitats numèriques per seguretat total
    result = []
    for c in escaped:
        o = ord(c)
        if o < 32:
            if o in (10, 13): # newline / carriage return
                result.append(c)
            elif o == 9: # tab
                result.append("    ")
            else:
                continue # ometem altres caràcters de control
        else:
            result.append(c)
    
    final_text = "".join(result)
    # Substituïm salts de línia per <br/> perquè Paragraph els interpreti correctament
    return final_text.replace("\n", "<br/>").replace("\r", "")

def _md_to_pdf_tags(text: str) -> str:
    """Converteix markdown bàsic (**bold**) a tags ReportLab (<b>)."""
    if not isinstance(text, str):
        return str(text)
    # Reemplacem **text** per <b>text</b>
    # Usement regex per no trencar-ho si hi ha molts asteriscs
    import re
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return text


def _sanitize_reportlab_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_reportlab_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_reportlab_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_reportlab_payload(item) for item in value)
    if isinstance(value, str):
        return _safe_xml(value)
    return value


def safe_pdf_text(value: Any) -> str:
    return _safe_xml(value)


def safe_pdf_inline(label: Any, value: Any) -> str:
    return f"<b>{safe_pdf_text(label)}:</b> {safe_pdf_text(value)}"


def safe_pdf_paragraph(value: Any, style) -> Paragraph:
    return Paragraph(safe_pdf_text(value), style)


def safe_pdf_label_value_paragraph(label: Any, value: Any, style) -> Paragraph:
    label_text = _fix_encoding(label) if isinstance(label, str) else str(label or "")
    value_text = _fix_encoding(value) if isinstance(value, str) else str(value or "")
    markup = f"<b>{safe_pdf_text(label_text)}:</b> {safe_pdf_text(value_text)}"
    fallback = f"{label_text}: {_plain_text_from_markup(value_text)}"
    return safe_pdf_markup_paragraph(markup, style, fallback_text=fallback)


def safe_pdf_bullet_paragraph(value: Any, style) -> Paragraph:
    text = _fix_encoding(value) if isinstance(value, str) else str(value or "")
    return safe_pdf_markup_paragraph(f"• {safe_pdf_text(text)}", style, fallback_text=f"• {_plain_text_from_markup(text)}")


def _plain_text_from_markup(value: Any) -> str:
    text = _fix_encoding(value) if isinstance(value, str) else str(value or "")
    text = re.sub(r"\[([^\]]+)\]\((#[^)]+)\)", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _install_reportlab_paragraph_drawon_guard() -> None:
    if getattr(Paragraph, "_oracleaudit_drawon_guard", False):
        return

    original_draw_on = Paragraph.drawOn

    def _guarded_draw_on(self, canvas, x, y, _sW=0):
        try:
            return original_draw_on(self, canvas, x, y, _sW=_sW)
        except TypeError as exc:
            if "FragLine" not in str(exc) or getattr(self, "_oracleaudit_plain_retry", False):
                raise
            plain_text = ""
            try:
                plain_text = self.getPlainText() or ""
            except Exception:
                plain_text = _plain_text_from_markup(getattr(self, "text", "") or "")
            print(
                f"[post_crq_pdf] Paragraph FragLine fallback; style={getattr(getattr(self, 'style', None), 'name', '?')}; text={plain_text[:180]!r}",
                file=sys.stderr,
            )
            fallback_style = copy.copy(self.style)
            fallback_style.name = f"{getattr(self.style, 'name', 'Paragraph')}PlainFallback"
            fallback_style.alignment = TA_LEFT
            fallback = Paragraph(safe_pdf_text(plain_text or "-"), fallback_style)
            setattr(fallback, "_oracleaudit_plain_retry", True)
            fallback_width = max(float(getattr(self, "width", 0) or 0), 1.0)
            fallback_height = max(float(getattr(self, "height", 0) or 0), 1.0)
            fallback.wrap(fallback_width, fallback_height)
            try:
                return original_draw_on(fallback, canvas, x, y, _sW=_sW)
            except Exception as fallback_exc:
                print(
                    f"[post_crq_pdf] Canvas text fallback; style={getattr(fallback_style, 'name', '?')}; error={fallback_exc}",
                    file=sys.stderr,
                )
                canvas.saveState()
                if getattr(fallback_style, "textColor", None) is not None:
                    canvas.setFillColor(fallback_style.textColor)
                canvas.setFont(
                    getattr(fallback_style, "fontName", "Helvetica"),
                    float(getattr(fallback_style, "fontSize", 10.0) or 10.0),
                )
                leading = float(getattr(fallback_style, "leading", 12.0) or 12.0)
                max_width = max(fallback_width, 1.0)
                words = [word for word in re.split(r"\s+", plain_text or "-") if word]
                lines: List[str] = []
                current = ""
                font_name = getattr(fallback_style, "fontName", "Helvetica")
                font_size = float(getattr(fallback_style, "fontSize", 10.0) or 10.0)
                for word in words or ["-"]:
                    candidate = f"{current} {word}".strip()
                    if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
                        lines.append(current)
                        current = word
                    else:
                        current = candidate
                if current:
                    lines.append(current)
                text_object = canvas.beginText()
                text_object.setTextOrigin(x, y)
                for line in lines:
                    text_object.textLine(line)
                canvas.drawText(text_object)
                canvas.restoreState()
                return

    Paragraph.drawOn = _guarded_draw_on
    Paragraph._oracleaudit_drawon_guard = True


_install_reportlab_paragraph_drawon_guard()


def safe_pdf_markup_paragraph(markup: Any, style, *, fallback_text: Any = None) -> Paragraph:
    raw_markup = _fix_encoding(markup) if isinstance(markup, str) else str(markup or "")
    try:
        return Paragraph(raw_markup, style)
    except Exception:
        plain_text = fallback_text if fallback_text is not None else _plain_text_from_markup(raw_markup)
        return Paragraph(safe_pdf_text(plain_text), style)


def _draw_canvas_wrapped_text(
    canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str,
    font_size: float,
    leading: float,
    fill_color=None,
) -> float:
    if fill_color is not None:
        canvas.setFillColor(fill_color)
    canvas.setFont(font_name, font_size)
    normalized_text = _fix_encoding(text or "-")
    words = normalized_text.split()
    current_line = ""
    current_y = y
    for word in words:
        candidate = f"{current_line} {word}".strip()
        if current_line and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
            canvas.drawString(x, current_y, current_line)
            current_line = word
            current_y -= leading
        else:
            current_line = candidate
    if current_line:
        canvas.drawString(x, current_y, current_line)
        current_y -= leading
    return current_y


def _compact_text(value: Any, *, max_length: int = 220) -> str:
    text = _normalize_text(value)
    if not text or text == "-":
        return "-"
    if len(text) <= max_length:
        return _safe_xml(text)
    # Intentem tallar per la primera oració
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    if sentences and len(sentences[0]) > 10 and len(sentences[0]) <= max_length:
        return _safe_xml(f"{sentences[0]}.")
    return _safe_xml(f"{text[:max_length-3]}...")



def _fix_encoding(text: Any) -> Any:
    if not isinstance(text, str):
        return text

    if "Ã" in text or "Â" in text:
        for source_encoding in ("latin1", "cp1252"):
            try:
                repaired = text.encode(source_encoding).decode("utf-8")
                if repaired:
                    return repaired
            except Exception:
                continue

        replacements = {
            "Ã ": "à",
            "Ã¡": "á",
            "Ã¨": "è",
            "Ã©": "é",
            "Ã­": "í",
            "Ã¯": "ï",
            "Ã²": "ò",
            "Ã³": "ó",
            "Ãº": "ú",
            "Ã¼": "ü",
            "Ã§": "ç",
            "Â·": "·",
        }
        repaired = text
        for source, target in replacements.items():
            repaired = repaired.replace(source, target)
        return repaired
    return text


def _criticality_rank(value: Any) -> int:
    normalized = _normalize_key(value)
    if normalized in {"critic", "critical"}:
        return 3
    if normalized == "mitja":
        return 2
    if normalized == "baix":
        return 1
    return 0


def _criticality_key(value: Any) -> str:
    normalized = _normalize_key(value)
    if normalized in {"critic", "critical"} or "crit" in normalized or normalized.startswith("cr"):
        return "CRITIC"
    if normalized == "mitja" or "mitj" in normalized or "med" in normalized:
        return "MITJA"
    if normalized == "baix" or "low" in normalized:
        return "BAIX"
    return "BAIX"


def _criticality_label(value: Any) -> str:
    return {
    "CRITIC": "Crític",
    "MITJA": "Mitjà",
        "BAIX": "Baix",
    }.get(_criticality_key(value), "Baix")


def _criticality_plural_label(value: Any) -> str:
    key = _criticality_key(value)
    mapping = {
        "CRITIC": "crítiques",
        "MITJA": "mitjanes",
        "BAIX": "baixes",
    }
    return mapping.get(key, "baixes")


def _default_check_criticality(check_id: str) -> str:
    return DEFAULT_CHECK_CRITICALITY.get(str(check_id or "").strip().upper(), "BAIX")


def _resolve_check_criticality(check_id: str, overrides: Optional[Dict[str, Any]] = None, default_severity: Optional[str] = None) -> str:
    override_value = (overrides or {}).get(check_id)
    if override_value:
        return _criticality_key(override_value)
    if default_severity:
        return _criticality_key(default_severity)
    return _criticality_key(_default_check_criticality(check_id))


def _criticality_action_text(value: Any) -> str:
    return CRITICALITY_ACTIONS.get(_criticality_key(value), CRITICALITY_ACTIONS["BAIX"])


def _environment_message(profile: Any) -> Optional[str]:
    return ENVIRONMENT_MESSAGES.get(str(profile or "").strip().upper())


def _filter_window_bounds(normalized_filter: Dict[str, Any]) -> Tuple[Optional[datetime.datetime], Optional[datetime.datetime]]:
    mode = (normalized_filter.get("mode") or "preset").strip().lower()
    if mode == "range":
        start_raw = str(normalized_filter.get("start_date") or "").strip()
        end_raw = str(normalized_filter.get("end_date") or "").strip()
        if not start_raw or not end_raw:
            return None, None
        return _parse_iso_dt(start_raw), _parse_iso_dt(end_raw, True)


    anchor_raw = str(normalized_filter.get("resolved_at") or "").strip()
    anchor_dt = _parse_iso_dt(anchor_raw)
    if anchor_dt is None:
        anchor_date_raw = str(normalized_filter.get("resolved_on") or normalized_filter.get("end_date") or "").strip()
        if not anchor_date_raw:
            return None, None
        anchor_dt = _parse_iso_dt(anchor_date_raw)

    days_back = max(1, int(normalized_filter.get("days_back") or 1))
    return anchor_dt - datetime.timedelta(days=days_back), anchor_dt


def _timestamp_within_window(value: Optional[datetime.datetime], normalized_filter: Dict[str, Any]) -> bool:
    if not value:
        return False
    start_dt, end_dt = _filter_window_bounds(normalized_filter)
    if start_dt and value < start_dt:
        return False
    if end_dt and value > end_dt:
        return False
    return True


def parse_post_crq_checks(markdown_path: Optional[str] = None) -> List[Dict[str, Any]]:
    path = markdown_path or resolve_post_crq_markdown_path()
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()

    sql_blocks = re.findall(r"```sql\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
    checks: List[Dict[str, Any]] = []
    seen_check_ids: set[str] = set()

    for block in sql_blocks:
        raw_sql = block.strip()
        match = re.search(r"--\s*CHECK\s+(\d+)\s*:\s*(.+)", raw_sql, flags=re.IGNORECASE)
        if not match:
            continue

        check_number = int(match.group(1))
        title = _normalize_text(match.group(2))
        severity_match = re.search(r"--\s*Severitat\s*:\s*(.+)", raw_sql, flags=re.IGNORECASE)
        criteria_match = re.search(
            r"--\s*Criteri\s*:\s*(.*?)(?:\n--\s*=+\s*$|\nWITH\s|\nSELECT\s)",
            raw_sql,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        severitat = _normalize_text(severity_match.group(1)) if severity_match else "N/A"
        criteri = ""
        if criteria_match:
            criteri = _normalize_text(criteria_match.group(1).replace("--", " "))

        sql = re.sub(r"^\s*DEFINE\s+.+?$", "", raw_sql, flags=re.IGNORECASE | re.MULTILINE).strip()
        check_id = f"CHECK_{check_number:02d}"
        if check_id in seen_check_ids:
            continue
        seen_check_ids.add(check_id)
        checks.append(
            {
                "check_id": check_id,
                "id": check_id,
                "check_number": check_number,
                "name": title,
                "nombre": title,
                "title": title,
                "description": criteri or title,
                "descripcio": criteri or title,
                "severitat": severitat,
                "severitat_base": severitat,
                "criteri": criteri,
                "parametres_admesos": ["days_back"],
                "sql": sql,
                "source_file": os.path.basename(path),
            }
        )

    checks.sort(key=lambda item: item["check_number"])
    return checks


def _days_back_from_filter(
    time_filter: Optional[Dict[str, Any]],
    reference_dt: Optional[datetime.datetime] = None,
) -> Tuple[int, Dict[str, Any]]:
    time_filter = time_filter or {}
    mode = (time_filter.get("mode") or "preset").strip().lower()
    preset = (time_filter.get("preset") or "weekly").strip().lower()
    reference_dt = reference_dt or datetime.datetime.now()
    today = reference_dt.date()

    if mode == "range":
        start_raw = (time_filter.get("start_date") or "").strip()
        end_raw = (time_filter.get("end_date") or "").strip()
        if not start_raw or not end_raw:
            raise ValueError("El rang temporal requereix start_date i end_date.")
        start_dt = _parse_iso_dt(start_raw)
        end_dt = _parse_iso_dt(end_raw, True)
        if not start_dt or not end_dt:
            raise ValueError(f"Format de data no vàlid: {start_raw} / {end_raw}")
        
        start_date = start_dt.date()
        end_date = end_dt.date()
        if end_date < start_date:
            raise ValueError("end_date no pot ser anterior a start_date.")
        days_back = max(1, (end_date - start_date).days + 1)
        return days_back, {
            "mode": "range",
            "preset": None,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "range_start_at": start_dt.isoformat(timespec="minutes"),
            "range_end_at": end_dt.isoformat(timespec="minutes"),
            "days_back": days_back,
            "resolved_on": today.isoformat(),
            "resolved_at": reference_dt.isoformat(timespec="seconds"),
        }

    preset_days = {
        "daily": 1,
        "weekly": 7,
        "monthly": 30,
    }
    days_back = preset_days.get(preset, 7)
    # Per assegurar que cobrim les darreres 24h reals, START_DATE bind ha d'incloure ahir
    start_date = today - datetime.timedelta(days=days_back)
    
    return days_back, {
        "mode": "preset",
        "preset": preset,
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "range_start_at": (reference_dt - datetime.timedelta(days=days_back)).isoformat(timespec="minutes"),
        "range_end_at": reference_dt.isoformat(timespec="minutes"),
        "days_back": days_back,
        "resolved_on": today.isoformat(),
        "resolved_at": reference_dt.isoformat(timespec="seconds"),
    }


def _sql_with_binds(raw_sql: str) -> str:
    sql = re.sub(r"^\s*DEFINE\s+.+?$", "", raw_sql or "", flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r"'&DAYS_BACK\b'", ":days_back", sql, flags=re.IGNORECASE)
    sql = re.sub(r"'&START_DATE\b'", ":start_date", sql, flags=re.IGNORECASE)
    sql = re.sub(r"'&END_DATE\b'", ":end_date", sql, flags=re.IGNORECASE)
    sql = re.sub(r"'&START_AT\b'", ":start_at", sql, flags=re.IGNORECASE)
    sql = re.sub(r"'&END_AT\b'", ":end_at", sql, flags=re.IGNORECASE)
    sql = re.sub(r"&DAYS_BACK\b", ":days_back", sql, flags=re.IGNORECASE)
    sql = re.sub(r"&START_DATE\b", ":start_date", sql, flags=re.IGNORECASE)
    sql = re.sub(r"&END_DATE\b", ":end_date", sql, flags=re.IGNORECASE)
    sql = re.sub(r"&START_AT\b", ":start_at", sql, flags=re.IGNORECASE)
    sql = re.sub(r"&END_AT\b", ":end_at", sql, flags=re.IGNORECASE)
    return sql.strip().rstrip(";")


def _has_explicit_time_component(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(re.search(r"[T\s]\d{2}:\d{2}", text))


def _build_time_bind_values(normalized_filter: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], bool]:
    start_raw = normalized_filter.get("range_start_at") or normalized_filter.get("start_date")
    end_raw = normalized_filter.get("range_end_at") or normalized_filter.get("end_date")
    start_dt = _parse_iso_dt(start_raw)
    end_dt = _parse_iso_dt(end_raw, True)
    if not start_dt or not end_dt:
        return None, None, False
    explicit_time = _has_explicit_time_component(start_raw) or _has_explicit_time_component(end_raw)
    return (
        start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        explicit_time,
    )


def _strip_sql_comments(sql: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", sql or "", flags=re.DOTALL)
    return re.sub(r"--.*?$", "", text, flags=re.MULTILINE)


def _extract_top_level_select_projection(sql: str) -> str:
    text = _strip_sql_comments(sql or "")
    upper = text.upper()
    in_single_quote = False
    depth = 0
    select_pos = None
    from_pos = None
    idx = 0

    while idx < len(text):
        char = text[idx]
        if in_single_quote:
            if char == "'" and idx + 1 < len(text) and text[idx + 1] == "'":
                idx += 2
                continue
            if char == "'":
                in_single_quote = False
            idx += 1
            continue

        if char == "'":
            in_single_quote = True
            idx += 1
            continue
        if char == "(":
            depth += 1
            idx += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            idx += 1
            continue

        if depth == 0:
            if upper.startswith("SELECT", idx) and (idx == 0 or not (upper[idx - 1].isalnum() or upper[idx - 1] == "_")):
                select_pos = idx + len("SELECT")
                from_pos = None
                idx += len("SELECT")
                continue
            if select_pos is not None and upper.startswith("FROM", idx) and (idx == 0 or not (upper[idx - 1].isalnum() or upper[idx - 1] == "_")):
                from_pos = idx
                break

        idx += 1

    if select_pos is None or from_pos is None or from_pos <= select_pos:
        return text
    return text[select_pos:from_pos]


def _extract_output_aliases(sql: str) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    projection = _extract_top_level_select_projection(sql)
    for match in re.finditer(r"\bAS\s+\"?([A-Za-z_][A-Za-z0-9_$#]*)\"?", projection or "", flags=re.IGNORECASE):
        alias = match.group(1).strip()
        aliases[_normalize_key(alias)] = alias.upper()
    return aliases


def _quote_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _render_sql_for_export(sql: str, binds: Dict[str, Any]) -> str:
    rendered = sql or ""
    for bind_name, bind_value in sorted((binds or {}).items(), key=lambda item: len(item[0]), reverse=True):
        rendered = re.sub(
            rf":{re.escape(bind_name)}\b",
            _quote_sql_literal(bind_value),
            rendered,
            flags=re.IGNORECASE,
        )
    return rendered


def _time_hint_score(normalized_key: str) -> Optional[int]:
    for index, hint in enumerate(TIME_COLUMN_HINTS):
        if hint in normalized_key:
            return index
    return None


def _can_push_time_filter_to_sql(sql: str, alias: Optional[str]) -> bool:
    if not alias:
        return False
    alias_pattern = re.escape(alias)
    stringified_patterns = (
        rf"\bTO_CHAR\s*\(.*?\)\s+AS\s+\"?{alias_pattern}\"?\b",
        rf"\bCAST\s*\(.*?\bAS\s+(?:N?CHAR|N?VARCHAR2?)\s*(?:\([^)]*\))?\s*\)\s+AS\s+\"?{alias_pattern}\"?\b",
    )
    for pattern in stringified_patterns:
        if re.search(pattern, sql or "", flags=re.IGNORECASE | re.DOTALL):
            return False
    return True


def _build_wrapped_sql(
    sql: str,
    normalized_filter: Dict[str, Any],
    schemas: List[str],
    base_binds: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], Optional[str], Optional[str], bool, bool]:
    aliases = _extract_output_aliases(sql)
    schema_alias_candidates = [
        (normalized, alias)
        for normalized, alias in aliases.items()
        if normalized in {"esquema", "schema", "schema_name", "owner", "username"}
    ]
    schema_alias_priority = {
        "esquema": 0,
        "schema": 1,
        "schema_name": 2,
        "owner": 3,
        "username": 4,
    }
    schema_alias = (
        sorted(
            schema_alias_candidates,
            key=lambda item: schema_alias_priority.get(item[0], 99),
        )[0][1]
        if schema_alias_candidates
        else None
    )
    temporal_candidates = [
        (score, alias)
        for normalized, alias in aliases.items()
        for score in [_time_hint_score(normalized)]
        if score is not None
    ]
    temporal_alias = sorted(temporal_candidates, key=lambda item: item[0])[0][1] if temporal_candidates else None

    wrapped_conditions: List[str] = []
    binds = dict(base_binds or {})
    schema_pushed = False
    time_pushed = False

    if schemas and schema_alias:
        schema_bind_names = []
        for index, schema in enumerate(schemas):
            bind_name = f"schema_{index}"
            binds[bind_name] = schema
            schema_bind_names.append(f":{bind_name}")
        wrapped_conditions.append(f'UPPER(post_crq_result."{schema_alias}") IN ({", ".join(schema_bind_names)})')
        schema_pushed = True

    if normalized_filter.get("mode") == "range" and temporal_alias and _can_push_time_filter_to_sql(sql, temporal_alias):
        start_at, end_at, explicit_time = _build_time_bind_values(normalized_filter)
        if explicit_time and start_at and end_at:
            binds["start_at"] = start_at
            binds["end_at"] = end_at
            wrapped_conditions.append(
                f'post_crq_result."{temporal_alias}" BETWEEN TO_DATE(:start_at, \'YYYY-MM-DD HH24:MI:SS\') AND TO_DATE(:end_at, \'YYYY-MM-DD HH24:MI:SS\')'
            )
            time_pushed = True
        else:
            binds["start_date"] = (normalized_filter.get("start_date") or "")[:10]
            binds["end_date"] = (normalized_filter.get("end_date") or "")[:10]
            wrapped_conditions.append(
                f'TRUNC(post_crq_result."{temporal_alias}") BETWEEN TO_DATE(:start_date, \'YYYY-MM-DD\') AND TO_DATE(:end_date, \'YYYY-MM-DD\')'
            )
            time_pushed = True

    if not wrapped_conditions:
        return sql, binds, schema_alias, temporal_alias, False, False

    wrapped_sql = (
        "SELECT * FROM ("
        + sql
        + ") post_crq_result WHERE "
        + " AND ".join(wrapped_conditions)
    )
    return wrapped_sql, binds, schema_alias, temporal_alias, schema_pushed, time_pushed


def _pick_schema_key(row: Dict[str, Any]) -> Optional[str]:
    for key in row.keys():
        normalized = _normalize_key(key)
        if normalized in {"esquema", "schema", "schema_name", "owner", "username"}:
            return key
    return None


def _pick_time_key(row: Dict[str, Any]) -> Optional[str]:
    candidates: List[Tuple[int, str]] = []
    for key in row.keys():
        normalized = _normalize_key(key)
        score = _time_hint_score(normalized)
        if score is not None:
            candidates.append((score, key))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _parse_datetime(value: Any) -> Optional[datetime.datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time.min)

    text = _normalize_text(value)
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return _parse_iso_dt(text)


def _filter_rows_by_schema(rows: List[Dict[str, Any]], schemas: List[str]) -> List[Dict[str, Any]]:
    normalized_schemas = {str(schema).strip().upper() for schema in schemas if str(schema).strip()}
    if not normalized_schemas or not rows:
        return rows

    schema_key = _pick_schema_key(rows[0])
    if not schema_key:
        return rows

    return [row for row in rows if str(row.get(schema_key, "")).strip().upper() in normalized_schemas]


def _filter_rows_by_range(rows: List[Dict[str, Any]], normalized_filter: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not rows:
        return rows, None

    # Intentem timestamps de precisió (rang_start_at) per a qualsevol mode
    start_dt = _parse_iso_dt(normalized_filter.get("range_start_at") or normalized_filter.get("start_date"))
    end_dt = _parse_iso_dt(normalized_filter.get("range_end_at") or normalized_filter.get("end_date"), True)
    
    if not start_dt or not end_dt:
        return rows, None
    
    time_key = _pick_time_key(rows[0])
    if not time_key:
        return rows, None

    filtered_rows = []
    for row in rows:
        dt = _parse_datetime(row.get(time_key))
        if not dt:
            continue
        # Comparem timestamps de precisió completa (no només data)
        if start_dt <= dt <= end_dt:
            filtered_rows.append(row)
    return filtered_rows, time_key


def _severity_rank(value: str) -> int:
    return _criticality_rank(value)


def _format_datetime(dt_value: Optional[datetime.datetime]) -> Optional[str]:
    if not dt_value:
        return None
    return dt_value.strftime("%Y-%m-%d %H:%M")


def _build_schema_last_modifications(
    executed_checks: List[Dict[str, Any]],
    normalized_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    latest_by_schema: Dict[str, Dict[str, Any]] = {}
    normalized_filter = normalized_filter or {}

    for item in executed_checks:
        rows = item.get("rows") or []
        if not rows:
            continue

        schema_key = _pick_schema_key(rows[0])
        temporal_key = item.get("temporal_column") or _pick_time_key(rows[0])
        if not schema_key or not temporal_key:
            continue

        for row in rows:
            schema = str(row.get(schema_key, "")).strip().upper()
            if not schema:
                continue
            parsed = _parse_datetime(row.get(temporal_key))
            if not parsed or not _timestamp_within_window(parsed, normalized_filter):
                continue

            current = latest_by_schema.get(schema)
            if not current or parsed > current["last_modified_dt"]:
                latest_by_schema[schema] = {
                    "schema": schema,
                    "last_modified_dt": parsed,
                    "last_modified_at": _format_datetime(parsed),
                    "source_check": item.get("check_id"),
                }

    items = list(latest_by_schema.values())
    items.sort(key=lambda item: item["last_modified_dt"], reverse=True)
    for item in items:
        item.pop("last_modified_dt", None)
    return items


def _build_detected_time_range(
    executed_checks: List[Dict[str, Any]],
    normalized_filter: Dict[str, Any],
) -> Dict[str, Optional[str]]:
    detected_values: List[datetime.datetime] = []
    for item in executed_checks:
        rows = item.get("rows") or []
        if not rows:
            continue
        time_key = item.get("temporal_column") or _pick_time_key(rows[0])
        if not time_key:
            continue
        for row in rows:
            parsed = _parse_datetime(row.get(time_key))
            if parsed and _timestamp_within_window(parsed, normalized_filter):
                detected_values.append(parsed)

    if not detected_values:
        return {"start_at": None, "end_at": None}
    return {
        "start_at": _format_datetime(min(detected_values)),
        "end_at": _format_datetime(max(detected_values)),
    }


def _extract_summary_subjects(item: Dict[str, Any]) -> Dict[str, Any]:
    rows = item.get("rows") or []
    if not rows:
        return {"schemas": [], "objects": []}

    schema_key = _pick_schema_key(rows[0])
    object_candidates = [
        "TAULA",
        "TABLE",
        "SEQUENCIA",
        "SEQUENCE",
        "OBJECTE",
        "SINONIM",
        "CONSTRAINT_FK",
        "CONSTRAINT_NAME",
    ]
    object_key = next((candidate for candidate in object_candidates if candidate in rows[0]), None)

    schemas = sorted(
        {
            str(row.get(schema_key, "")).strip().upper()
            for row in rows
            if schema_key and str(row.get(schema_key, "")).strip()
        }
    )
    objects = []
    if object_key:
        objects = [
            str(row.get(object_key, "")).strip()
            for row in rows
            if str(row.get(object_key, "")).strip()
        ][:5]
    return {"schemas": schemas, "objects": objects}


def _check_summary_sentence(item: Dict[str, Any]) -> str:
    check_id = str(item.get("check_id") or "").strip().upper()
    row_count = int(item.get("row_count", 0))
    subjects = _extract_summary_subjects(item)
    schemas = ", ".join(subjects["schemas"]) if subjects["schemas"] else "diversos esquemes"
    examples = ""
    if subjects["objects"]:
        examples = f" Exemples: {', '.join(subjects['objects'])}."

    templates = {
        "CHECK_01": f"Alerta Crítica d'Integritat: {row_count} taules als esquemes {schemas} s'han desplegat sense Primary Key. L'absència de clau primària fa inviable garantir la unicitat de les dades i degrada qualsevol procés de replicació o particionament.{examples}",
        "CHECK_02": f"Av?s d'acc?s seq?encial: S'han identificat {row_count} taules als esquemes {schemas} sense cap ?ndex visible sobre la c?rrega operativa. Aix? pot for?ar full table scans i degradar les consultes freq?ents. Si la consulta ha incl?s objectes interns o temporals, ha estat perqu? el check els detecta expl?citament.{examples}",
        "CHECK_03": f"Rendiment DML Penalitzat: S'han trobat {row_count} seqüències als esquemes {schemas} amb una memòria cau (cache) inexistent o insuficient, provocant un accés excessiu al diccionari de dades (esperes 'row cache lock').{examples}",
        "CHECK_04": f"Risc de Bloqueig (Locking): Existeixen {row_count} Foreign Keys als esquemes {schemas} que no compten amb un índex de suport a la taula filla. Qualsevol esborrat a la taula pare bloquejarà tota la taula filla (Table Lock).{examples}",
        "CHECK_05": f"Risc de dades ?rfenes o inv?lides: S'han trobat {row_count} restriccions deshabilitades als esquemes {schemas}. Cal validar si l'estat esperat ?s ENABLED VALIDATED o si la desactivaci? forma part d'un canvi del CRQ amb justificaci? expl?cita.{examples}",
        "CHECK_06": f"Desaprofitament d'Emmagatzematge i DML Lents: S'han detectat {row_count} índexs solapats o redundants als esquemes {schemas}, fet que penalitza innecessàriament les operacions d'escriptura i consumeix espai de blocs.{examples}",
        "CHECK_07": f"Dependències Trencades (Invalid Objects): Existeixen {row_count} objectes en estat invàlid als esquemes {schemas}. Això pot provocar errades en temps d'execució (ORA-04068) la propera vegada que siguin invocats.{examples}",
        "CHECK_08": f"Declaració de Tipus Ambigua: S'observen {row_count} columnes NUMBER sense declarar la precisió o l'escala als esquemes {schemas}, la qual cosa pot derivar en desbordaments numèrics imprevistos en emmagatzemar valors no controlats.{examples}",
        "CHECK_09": f"Punters Orfes (Broken Synonyms): S'han localitzat {row_count} sinònims, els destinataris dels quals no existeixen, als esquemes {schemas}. Això causarà excepcions (ORA-00980 Translation is no longer valid) immediates a nivell d'aplicació.{examples}",
        "CHECK_10": f"Anul·lació d'Errors Silenciosa: S'han detectat {row_count} blocs de codi amb l'anti-patró 'WHEN OTHERS THEN NULL' als esquemes {schemas}. Aquesta pràctica oculta excepcions i impossibilita el diagnòstic d'errades greus.{examples}",
        "CHECK_11": f"Qualitat de Codi en Risc: S'han detectat {row_count} objectes PL/SQL als esquemes {schemas} amb patrons problemàtics com DBMS_OUTPUT en producció, COMMIT en bucle o EXECUTE IMMEDIATE concatenat.{examples}",
        "CHECK_12": f"Risc de coll d'ampolla (fila a fila): S'han detectat {row_count} objectes PL/SQL que processen dades sense evid?ncia de BULK COLLECT ni FORALL als esquemes {schemas}. Si el resultat visible inclou TE_BULK, aquest indicador s'ha de revisar juntament amb el codi i no de manera a?llada.{examples}",
    }
    return templates.get(
        check_id,
        f"Alerta d'Auditoria ({check_id}): S'han detectat {row_count} ocurrències que no compleixen amb l'estàndard d'arquitectura Oracle als esquemes {schemas}. Cal revisar-ho immediatament.{examples}",
    )


def _build_criticality_sections(
    executed_checks: List[Dict[str, Any]],
    profile: str,
) -> List[Dict[str, Any]]:
    environment_message = _environment_message(profile)
    grouped: List[Dict[str, Any]] = []
    for criticality in CRITICALITY_ORDER:
        items = []
        for current in executed_checks:
            if current.get("criticitat_key") != criticality:
                continue
            if int(current.get("row_count", 0)) <= 0 and current.get("status") == "ok":
                continue
            item_summary = {
                "check_id": current.get("check_id"),
                "title": _display_title(current.get("title")),
                "criticitat": _criticality_label(current.get("criticitat_key")),
                "criticitat_key": criticality,
                "status": current.get("status"),
                "row_count": current.get("row_count", 0),
                "summary_text": _check_summary_sentence(current) if current.get("status") == "ok" else f"El check {current.get('check_id')} ha fallat i s'ha de revisar abans de validar el canvi.",
                "action_text": _criticality_action_text(criticality),
            }
            if current.get("error"):
                item_summary["error"] = current.get("error")
            items.append(item_summary)

        items.sort(
            key=lambda current: (current.get("status") == "error", int(current.get("row_count", 0))),
            reverse=True,
        )
        grouped.append(
            {
                "criticality_key": criticality,
                "criticality_label": _criticality_label(criticality),
                "action_text": _criticality_action_text(criticality),
                "environment_message": environment_message if criticality == "CRITIC" else None,
                "items": items,
                "total_findings": sum(int(item.get("row_count", 0)) for item in items),
            }
        )
    return grouped


def _build_summary(
    executed_checks: List[Dict[str, Any]],
    profile: str,
    normalized_filter: Dict[str, Any],
) -> Dict[str, Any]:
    criticality_counts: Dict[str, int] = {
        CRITICALITY_DISPLAY["CRITIC"]: 0,
        CRITICALITY_DISPLAY["MITJA"]: 0,
        CRITICALITY_DISPLAY["BAIX"]: 0,
    }
    total_findings = 0
    checks_with_findings = 0
    errors = 0

    for item in executed_checks:
        criticality_label = _criticality_label(item.get("criticitat_key"))
        criticality_counts[criticality_label] = criticality_counts.get(criticality_label, 0) + int(item.get("row_count", 0))
        total_findings += int(item.get("row_count", 0))
        if int(item.get("row_count", 0)) > 0:
            checks_with_findings += 1
        if item.get("status") != "ok":
            errors += 1

    criticality_sections = _build_criticality_sections(executed_checks, profile)
    top_findings = sorted(
        executed_checks,
        key=lambda item: (int(item.get("row_count", 0)), _criticality_rank(item.get("criticitat_key", ""))),
        reverse=True,
    )[:5]
    detected_time_range = _build_detected_time_range(executed_checks, normalized_filter)

    return {
        "selected_checks": len(executed_checks),
        "executed_checks": len(executed_checks),
        "checks_with_findings": checks_with_findings,
        "total_findings": total_findings,
        "critical_findings": criticality_counts.get("Crític", 0),
        "medium_findings": criticality_counts.get("Mitjà", 0),
        "low_findings": criticality_counts.get("Baix", 0),
        "error_count": errors,
        "checks_with_errors": errors,
        "findings_by_criticality": criticality_counts,
        "criticality_sections": criticality_sections,
        "environment_message": _environment_message(profile),
        "detected_time_range": detected_time_range,
        "top_findings": [
            {
                "check_id": item.get("check_id"),
                "title": item.get("title"),
                "row_count": item.get("row_count", 0),
                "criticitat": _criticality_label(item.get("criticitat_key")),
            }
            for item in top_findings
        ],
    }



def _resolve_report_time_window_label_v2(time_filter: Dict[str, Any]) -> str:
    mode = str((time_filter or {}).get("mode") or "preset").strip().lower()
    if mode == "range":
        start_at = (time_filter or {}).get("start_date") or "-"
        end_at = (time_filter or {}).get("end_date") or "-"
        return f"{start_at} -> {end_at}"
    resolved_at = str((time_filter or {}).get("resolved_at") or "").strip()
    days_back = int((time_filter or {}).get("days_back") or 1)
    if not resolved_at:
        return "-"
    end_dt = _parse_iso_dt(resolved_at, end=True)
    if not end_dt:
        return resolved_at
    start_dt = end_dt - datetime.timedelta(days=days_back)
    return f"{start_dt.isoformat(timespec='minutes')} -> {end_dt.isoformat(timespec='minutes')}"


def _build_summary_v2(
    executed_checks: List[Dict[str, Any]],
    profile: str,
    normalized_filter: Dict[str, Any],
) -> Dict[str, Any]:
    criticality_counts: Dict[str, int] = {
        CRITICALITY_DISPLAY["CRITIC"]: 0,
        CRITICALITY_DISPLAY["MITJA"]: 0,
        CRITICALITY_DISPLAY["BAIX"]: 0,
    }
    total_findings = 0
    checks_with_findings = 0
    errors = 0

    for item in executed_checks:
        row_count = int(item.get("row_count", 0) or 0)
        key = _criticality_key(item.get("criticitat_key"))
        label = _criticality_label(key)
        
        criticality_counts[label] = criticality_counts.get(label, 0) + row_count
        # TambÃ© afegim per clau per robustesa del frontend
        criticality_counts[key] = criticality_counts.get(key, 0) + row_count
        
        total_findings += row_count
        if row_count > 0:
            checks_with_findings += 1
        if item.get("status") != "ok":
            errors += 1

    criticality_sections = _build_criticality_sections(executed_checks, profile)
    top_findings = sorted(
        executed_checks,
        key=lambda item: (int(item.get("row_count", 0) or 0), _criticality_rank(item.get("criticitat_key", ""))),
        reverse=True,
    )[:5]
    detected_time_range = _build_detected_time_range(executed_checks, normalized_filter)

    return {
        "selected_checks": len(executed_checks),
        "executed_checks": len(executed_checks),
        "checks_with_findings": checks_with_findings,
        "total_findings": total_findings,
        "critical_findings": criticality_counts.get("CRITIC", 0),
        "medium_findings": criticality_counts.get("MITJA", 0),
        "low_findings": criticality_counts.get("BAIX", 0),
        "error_count": errors,
        "checks_with_errors": errors,
        "findings_by_criticality": criticality_counts,
        "criticality_sections": criticality_sections,
        "environment_message": _environment_message(profile),
        "detected_time_range": detected_time_range,
        "top_findings": [
            {
                "check_id": item.get("check_id"),
                "title": item.get("title"),
                "row_count": item.get("row_count", 0),
                "criticitat": _criticality_label(item.get("criticitat_key")),
            }
            for item in top_findings
        ],
    }


def _humanize_duration_ms_v2(value: Any) -> str:
    try:
        duration_ms = int(value or 0)
    except (TypeError, ValueError):
        return "-"
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    if duration_ms < 60000:
        return f"{duration_ms / 1000:.2f} s".replace(".", ",")
    minutes, seconds = divmod(duration_ms // 1000, 60)
    return f"{minutes} min {seconds} s"


def _report_model_index_entries_v2(include_annex: bool) -> List[str]:
    entries = [
        "1. Portada",
        "2. Índex",
        "3. Paràmetres d'execució",
        "4. Resum executiu per lots",
        "5. Incidències prioritzades per lot",
        "6. Resultat detallat per check",
        "7. Observacions finals",
    ]
    if include_annex:
        entries.append("8. Annex funcional dels checks")
    return entries


def _report_model_parameters_rows_v2(report: Dict[str, Any]) -> List[tuple[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    time_window = execution_parameters.get("time_window") or {}
    schemas = execution_parameters.get("schemas") or context.get("schemas") or []
    time_window_label = _format_display_time_range(
        start_raw=time_window.get("start_at") or time_window.get("range_start_at") or time_window.get("start_date"),
        end_raw=time_window.get("end_at") or time_window.get("range_end_at") or time_window.get("end_date"),
    )
    return [
        ("Perfil", _fix_encoding(execution_parameters.get("profile") or context.get("profile") or "-")),
        ("Data i hora", _fix_encoding(execution_parameters.get("generated_at") or "-")),
        ("Mode temporal", _fix_encoding(_display_time_mode(context.get("time_filter") or {}))),
        ("Període aplicat", _fix_encoding(_display_period_label(context.get("time_filter") or {}))),
        ("Finestra consultada", time_window_label),
        ("Idioma", "Català"),
        ("Codificació", "UTF-8"),
        ("Fitxer de checks", _fix_encoding(execution_parameters.get("source_file") or context.get("source_file") or "-")),
        ("Lots o esquemes filtrats", ", ".join(schemas) if schemas else "Tots"),
    ]


def _build_enabled_checks_text_v2(report_model: Dict[str, Any]) -> str:
    enabled_checks = report_model.get("enabled_checks") or []
    if not enabled_checks:
        return "Sense checks activats."
    return ", ".join(
        f"{item.get('check_id')} ({_fix_encoding(item.get('criticality') or '-')})"
        for item in enabled_checks
    )


def _build_lot_summary_rows_v2(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in report_model.get("lot_summary") or []:
        check_descriptions = item.get("check_descriptions") or []
        rows.append(
            {
                "Lot": item.get("lot") or "SENSE LOT",
                "Crítiques": item.get("critical") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
                "Check afectat": ", ".join(entry.get("check_id") or "-" for entry in check_descriptions[:3]) or "-",
                "Descripció del check": " | ".join(
                    _fix_encoding(_display_title(entry.get("title") or entry.get("check_id") or "-"))
                    for entry in check_descriptions[:2]
                )
                or "-",
                "Prioritat": item.get("priority") or "Baix",
                "Acció inicial": _fix_encoding(item.get("first_action") or "-"),
            }
        )
    return rows


def _markdown_lot_incident_group_lines_v2(group: Dict[str, Any]) -> List[str]:
    lines = [
        f"### Lot {group.get('lot') or 'SENSE LOT'} — {group.get('check') or '-'}",
        "",
        f"- **Descripció del check:** {_fix_encoding(_display_title(group.get('title') or group.get('check') or '-'))}",
        f"- **Severitat:** {_fix_encoding(group.get('severity') or '-')}",
        f"- **Termini orientatiu:** {group.get('termini_dies') if group.get('termini_dies') is not None else '-'} dies",
        "",
        f"**Impacte sobre el lot:** {_fix_encoding(group.get('impacte') or '-')}",
        "",
        f"**Acció recomanada:** {_fix_encoding(group.get('accio_recomanada') or '-')}",
        "",
        f"**Validació posterior:** {_fix_encoding(group.get('validacio_posterior') or '-')}",
        "",
        "**Esquemes afectats:**",
    ]
    for schema_group in group.get("schemas") or []:
        lines.append(f"- **{_fix_encoding(schema_group.get('nom') or '-')}** ({schema_group.get('object_count') or 0} objectes)")
        object_rows = [
            {key: _fix_encoding(value) for key, value in _incident_object_table_row_v7(schema_group, objecte).items()}
            for objecte in (schema_group.get("objectes") or [])
        ]
        if object_rows:
            lines.append("")
            lines.append(_rows_to_markdown_table(["OBJECTE", "TIPUS", "DADA TÈCNICA"], object_rows, limit=None))
            lines.append("")
    return lines





def _report_operational_index_entries_v7(include_annex: bool) -> List[str]:
    return [entry for entry, _ in _build_post_crq_toc_entries(include_annex)]


def _post_crq_section_anchor_map_v7(include_annex: bool = True) -> Dict[str, str]:
    return {entry: anchor for entry, anchor in _build_post_crq_toc_entries(include_annex)}


def _build_post_crq_toc_entries(include_annex: bool) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = [
        ("1. Context de l'auditoria", "context"),
        ("2. Resum executiu post-CRQ", "resum"),
        ("3. Incidències prioritzades per criticitat i lot", "incidencies"),
        ("4. Resultat detallat per check", "detall"),
        ("5. Observacions finals", "observacions"),
    ]
    if include_annex:
        entries.append(("6. Annex A — anàlisi funcional de cada check", "annex"))
    return entries


def _check_number_from_id(value: Any) -> int:
    text = str(value or "").strip().upper()
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 9999


def _sort_check_dicts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items or [], key=lambda item: (_check_number_from_id((item or {}).get("check_id")), str((item or {}).get("check_id") or "")))


def _detail_anchor_name(check_id: Any) -> str:
    return f"detail_{_normalize_key(check_id or 'check')}"


def _linked_heading(label: str, anchor: str, styles: Dict[str, ParagraphStyle], *, style_key: str = "section_heading") -> Paragraph:
    return safe_pdf_markup_paragraph(f'<a name="{anchor}"/>{safe_pdf_text(label)}', styles[style_key], fallback_text=label)


def _centered_heading_block(label: str, anchor: str, styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    table = Table(
        [[safe_pdf_markup_paragraph(f'<a name="{anchor}"/>{safe_pdf_text(label)}', styles["section_heading"], fallback_text=label)]],
        colWidths=[total_width],
    )
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _lot_anchor_name(lot_index: int) -> str:
    return f"lot_{lot_index}"


def _lot_severity_anchor_name(lot_index: int, severity_index: int) -> str:
    return f"lot_{lot_index}_severity_{severity_index}"


def _lot_incident_anchor_name(lot_index: int, severity_index: int, incident_index: int) -> str:
    return f"lot_{lot_index}_severity_{severity_index}_incident_{incident_index}"


def _lot_incident_section_anchor_name(lot_index: int, severity_index: int, incident_index: int, section_code: str) -> str:
    return f"lot_{lot_index}_severity_{severity_index}_incident_{incident_index}_section_{_normalize_key(section_code)}"


def _build_post_crq_dynamic_toc_entries(report_model: Dict[str, Any], include_annex: bool) -> List[Tuple[str, str, int]]:
    entries: List[Tuple[str, str, int]] = [
        ("1. Context de l'auditoria", "context", 0),
        ("2. Resum executiu post-CRQ", "resum", 0),
        ("3. Incidències prioritzades per criticitat i lot", "incidencies", 0),
    ]
    severity_titles = {
        "CRITIC": "Incidències crítiques",
        "MITJA": "Incidències mitjanes",
        "BAIX": "Incidències baixes",
    }
    for lot_index, (lot_name, severity_blocks) in enumerate(_group_lot_incidents_by_lot_v7(report_model), start=1):
        entries.append((f"3.{lot_index} LOT {_fix_encoding(lot_name)}", _lot_anchor_name(lot_index), 1))
        ordered_severity_blocks = sorted(severity_blocks, key=lambda item: _criticality_rank(item[0]), reverse=True)
        for severity_index, (severity_key, _severity_label, groups) in enumerate(ordered_severity_blocks, start=1):
            section_title = severity_titles.get(severity_key, "Incidències")
            entries.append((f"3.{lot_index}.{severity_index} {section_title}", _lot_severity_anchor_name(lot_index, severity_index), 2))
            for incident_index, group in enumerate(groups, start=1):
                incident_title = _fix_encoding(_display_title(group.get("title") or group.get("check") or "-"))
                entries.append(
                    (
                        f"3.{lot_index}.{severity_index}.{_lettered_index(incident_index)}.- {incident_title}",
                        _lot_incident_anchor_name(lot_index, severity_index, incident_index),
                        3,
                    )
                )
                incident_sections: List[Tuple[str, str]] = [
                    ("a) Què s'ha detectat", "a"),
                    ("b) Impacte", "b"),
                    ("c) Esquemes afectats", "c"),
                ]
                if _build_incident_objects_table_rows_v6(group):
                    incident_sections.append(("d) Objectes afectats", "d"))
                incident_sections.extend(
                    [
                        ("e) Acció requerida", "e"),
                        ("f) Validació posterior", "f"),
                    ]
                )
                for section_label, section_code in incident_sections:
                    entries.append(
                        (
                            section_label,
                            _lot_incident_section_anchor_name(lot_index, severity_index, incident_index, section_code),
                            4,
                        )
                    )
    entries.extend(
        [
            ("4. Resultat detallat per check", "detall", 0),
            ("5. Observacions finals", "observacions", 0),
        ]
    )
    if include_annex:
        entries.append(("6. Annex A - anàlisi funcional de cada check", "annex", 0))
    return entries


def _build_post_crq_toc_block(entries: List[Tuple[str, str]], styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    rows: List[List[Any]] = [[Paragraph("Mapa de contingut", styles["toc_title"])]]
    row_levels: List[int] = []
    for entry in entries:
        if len(entry) >= 3:
            label, anchor, level = entry[0], entry[1], int(entry[2])
        else:
            label, anchor, level = entry[0], entry[1], 0
        row_levels.append(level)
        style_key = {
            0: "toc",
            1: "toc_lot",
            2: "toc_sub",
            3: "toc_micro",
            4: "toc_detail",
        }.get(level, "toc")
        rows.append(
            [
                safe_pdf_markup_paragraph(
                    f'<a href="#{anchor}">{safe_pdf_text(label)}</a>',
                    styles[style_key],
                    fallback_text=label,
                )
            ]
        )
    toc_table = Table(rows, colWidths=[total_width], repeatRows=0)
    table_style_commands: List[Tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), PDF_SOFT_ALT),
        ("BACKGROUND", (0, 1), (-1, -1), rl_colors.white),
        ("BOX", (0, 0), (-1, -1), 0.55, PDF_BRAND_LINE),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, PDF_BRAND_LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]
    for row_number, level in enumerate(row_levels, start=1):
        if level == 0:
            top_padding, bottom_padding = 6.2, 6.2
        elif level == 1:
            top_padding, bottom_padding = 4.6, 4.6
        elif level == 2:
            top_padding, bottom_padding = 3.4, 3.4
        elif level == 3:
            top_padding, bottom_padding = 2.8, 2.8
        else:
            top_padding, bottom_padding = 2.1, 2.1
        table_style_commands.extend(
            [
                ("TOPPADDING", (0, row_number), (-1, row_number), top_padding),
                ("BOTTOMPADDING", (0, row_number), (-1, row_number), bottom_padding),
            ]
        )
    toc_table.setStyle(TableStyle(table_style_commands))
    return toc_table


def _build_check_index_block(
    checks: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
    total_width: float,
    *,
    title: str = "Checks inclosos en l'informe",
    anchor_builder=None,
    min_body_rows: int = 0,
) -> Table:
    ordered_checks = _sort_check_dicts(checks)
    rows: List[List[Any]] = [[Paragraph(title, styles["toc_title"]), ""]]
    midpoint = (len(ordered_checks) + 1) // 2
    left_col = ordered_checks[:midpoint]
    right_col = ordered_checks[midpoint:]

    for index in range(max(len(left_col), len(right_col))):
        row: List[Any] = []
        for column in (left_col, right_col):
            if index >= len(column):
                row.append(Paragraph("", styles["check_index"]))
                continue

            item = column[index]
            check_id = str(item.get("check_id") or "-").strip()
            title_text = _fix_encoding(_display_title(item.get("title") or check_id))
            severity = item.get("criticality") or item.get("criticitat") or item.get("severitat") or "Baix"
            severity_label = _severity_badge_text(severity)
            severity_color = _severity_badge_hex(severity)
            anchor = anchor_builder(check_id) if anchor_builder else None
            link_start = f'<a href="#{anchor}">' if anchor else ""
            link_end = "</a>" if anchor else ""
            markup = (
                f"{link_start}<b>{safe_pdf_text(check_id)}</b>{link_end}"
                f" — {safe_pdf_text(title_text)} "
                f"<font color='{severity_color}'><b>({safe_pdf_text(severity_label)})</b></font>"
            )
            fallback = f"{check_id} - {title_text} ({severity_label})"
            row.append(safe_pdf_markup_paragraph(markup, styles["check_index"], fallback_text=fallback))
        rows.append(row)

    current_body_rows = max(0, len(rows) - 1)
    for _ in range(current_body_rows, max(min_body_rows, current_body_rows)):
        rows.append([Paragraph("", styles["check_index"]), Paragraph("", styles["check_index"])])

    column_width = (total_width - 10) / 2
    table = Table(rows, colWidths=[column_width, column_width], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), PDF_SOFT_ALT),
                ("BACKGROUND", (0, 1), (-1, -1), rl_colors.white),
                ("BOX", (0, 0), (-1, -1), 0.55, PDF_BRAND_LINE),
                ("INNERGRID", (0, 1), (-1, -1), 0.25, PDF_BRAND_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _group_lot_incidents_by_criticality_v7(report_model: Dict[str, Any]) -> List[tuple[str, str, List[Dict[str, Any]]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {"CRITIC": [], "MITJA": [], "BAIX": []}
    for item in report_model.get("lot_incident_groups") or []:
        grouped[_criticality_key(item.get("severity"))].append(item)
    return [
        ("5.1", "Incidències crítiques", grouped["CRITIC"]),
        ("5.2", "Incidències mitjanes", grouped["MITJA"]),
        ("5.3", "Incidències baixes", grouped["BAIX"]),
    ]


def _group_lot_incidents_by_lot_v7(report_model: Dict[str, Any]) -> List[Tuple[str, List[Tuple[str, str, List[Dict[str, Any]]]]]]:
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for item in report_model.get("lot_incident_groups") or []:
        lot = str(item.get("lot") or "SENSE LOT").strip() or "SENSE LOT"
        criticality_key = _criticality_key(item.get("severity"))
        current_lot = grouped.setdefault(lot, {"CRITIC": [], "MITJA": [], "BAIX": []})
        current_lot.setdefault(criticality_key, []).append(item)

    ordered_lots: List[Tuple[str, List[Tuple[str, str, List[Dict[str, Any]]]]]] = []
    for lot_name, blocks in sorted(grouped.items(), key=lambda item: (item[0] == "SENSE LOT", item[0])):
        severity_blocks: List[Tuple[str, str, List[Dict[str, Any]]]] = []
        for criticality_key, label in (
            ("CRITIC", "Incidències crítiques"),
            ("MITJA", "Incidències mitjanes"),
            ("BAIX", "Incidències baixes"),
        ):
            incidents = _sort_check_dicts(blocks.get(criticality_key) or [])
            if incidents:
                severity_blocks.append((criticality_key, label, incidents))
        if severity_blocks:
            ordered_lots.append((lot_name, severity_blocks))
    return ordered_lots


def _lettered_index(value: int) -> str:
    current = max(1, int(value))
    result = ""
    while current > 0:
        current -= 1
        result = chr(ord("a") + (current % 26)) + result
        current //= 26
    return result


def _orientative_deadline_text(days: Any, severity: Any) -> str:
    if _criticality_key(severity) == "CRITIC":
        return "Urgent"
    if days in (None, "", "-"):
        return "-"
    return f"{days} dies"


def _report_operational_cover_metrics_v7(report_model: Dict[str, Any]) -> List[Tuple[str, str]]:
    lot_summary = report_model.get("lot_summary") or []
    detail_sections = report_model.get("detail_sections") or []
    enabled_checks = report_model.get("enabled_checks") or []
    total_checks = len(enabled_checks) or len(detail_sections)
    total_findings = sum(int(section.get("finding_count") or len(section.get("rows") or [])) for section in detail_sections)
    return [
        ("Lots afectats", str(len(lot_summary))),
        ("Lots crítics", str(sum(1 for item in lot_summary if int(item.get("critical") or 0) > 0))),
        ("Checks inclosos", str(total_checks)),
        ("Troballes", str(total_findings)),
    ]


def _post_crq_pdf_cover_final_v7(canvas, profile: str, generated_at: str, cover_path: Path | None, report_model: Dict[str, Any], time_filter: Dict[str, Any]) -> None:
    width, height = A4
    canvas.saveState()
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFillColor(rl_colors.white)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.rect(0, height - (7.8 * cm), width, 7.8 * cm, fill=1, stroke=0)
    canvas.setFillColor(PDF_BRAND_BLUE)
    canvas.rect(0, height - (7.8 * cm), width, 0.42 * cm, fill=1, stroke=0)

    if cover_path and cover_path.exists():
        canvas.saveState()
        canvas.setFillAlpha(0.12)
        canvas.drawImage(
            str(cover_path),
            width - (8.0 * cm),
            height - (6.6 * cm),
            width=6.6 * cm,
            height=4.9 * cm,
            preserveAspectRatio=True,
            anchor="n",
            mask="auto",
        )
        canvas.restoreState()

    panel_x = 1.35 * cm
    panel_y = 6.95 * cm
    panel_width = width - (2.7 * cm)
    panel_height = 10.35 * cm
    canvas.setFillColor(rl_colors.white)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 16, fill=1, stroke=0)
    canvas.setStrokeColor(PDF_BRAND_LINE)
    canvas.setLineWidth(0.9)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 16, fill=0, stroke=1)

    canvas.setFillColor(PDF_BRAND_BLUE)
    canvas.setFont(title_font, 10.2)
    canvas.drawString(panel_x + 0.9 * cm, panel_y + panel_height - 1.15 * cm, "AUDITORIA ORACLE · VALIDACIÓ POST-CRQ")
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.setFont(title_font, 23)
    canvas.drawString(panel_x + 0.9 * cm, panel_y + panel_height - 2.1 * cm, "Informe d'auditoria post-CRQ")
    _draw_canvas_wrapped_text(
        canvas,
        "Informe institucional de validació tècnica per lots, amb incidències prioritzades i detall operatiu dels checks executats.",
        panel_x + 0.9 * cm,
        panel_y + panel_height - 2.9 * cm,
        panel_width - (1.8 * cm),
        body_font,
        11.0,
        0.52 * cm,
        PDF_MUTED_TEXT,
    )

    meta_y = panel_y + 5.3 * cm
    left_x = panel_x + 0.9 * cm
    right_x = panel_x + (panel_width / 2) + 0.15 * cm
    meta_width = (panel_width / 2) - 1.05 * cm
    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, meta_y, "Perfil")
    canvas.drawString(right_x, meta_y, "Data de generació")
    canvas.setFont(body_font, 10.2)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(left_x, meta_y - 0.38 * cm, _fix_encoding(profile or "-"))
    canvas.drawString(right_x, meta_y - 0.38 * cm, _fix_encoding(generated_at or "-"))

    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, meta_y - 0.95 * cm, "Finestra auditada")
    canvas.drawString(right_x, meta_y - 0.95 * cm, "Període aplicat")
    _draw_canvas_wrapped_text(
        canvas,
        _resolve_report_time_window_label_final_v3(time_filter),
        left_x,
        meta_y - 1.33 * cm,
        meta_width,
        body_font,
        10.0,
        0.47 * cm,
        PDF_MUTED_TEXT,
    )
    _draw_canvas_wrapped_text(
        canvas,
        _fix_encoding(_display_period_label(time_filter)),
        right_x,
        meta_y - 1.33 * cm,
        meta_width,
        body_font,
        10.0,
        0.47 * cm,
        PDF_MUTED_TEXT,
    )

    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, panel_y + 3.15 * cm, "Resum global")
    _draw_canvas_wrapped_text(
        canvas,
        _report_operational_cover_summary_v4(report_model),
        left_x,
        panel_y + 2.78 * cm,
        panel_width - (1.8 * cm),
        body_font,
        10.2,
        0.5 * cm,
        PDF_MUTED_TEXT,
    )

    metric_y = panel_y + 0.92 * cm
    metric_width = (panel_width - (1.8 * cm) - (3 * 0.34 * cm)) / 4
    for index, (label, value) in enumerate(_report_operational_cover_metrics_v7(report_model)):
        current_x = left_x + index * (metric_width + 0.34 * cm)
        canvas.setFillColor(PDF_SOFT_ALT if index % 2 == 0 else PDF_SOFT_FILL)
        canvas.roundRect(current_x, metric_y, metric_width, 1.72 * cm, 10, fill=1, stroke=0)
        canvas.setStrokeColor(PDF_BRAND_LINE)
        canvas.setLineWidth(0.45)
        canvas.roundRect(current_x, metric_y, metric_width, 1.72 * cm, 10, fill=0, stroke=1)
        canvas.setFillColor(PDF_BRAND_NAVY)
        canvas.setFont(title_font, 16)
        canvas.drawString(current_x + 0.22 * cm, metric_y + 1.0 * cm, value)
        _draw_canvas_wrapped_text(
            canvas,
            label,
            current_x + 0.22 * cm,
            metric_y + 0.48 * cm,
            metric_width - 0.38 * cm,
            body_font,
            8.4,
            0.3 * cm,
            PDF_MUTED_TEXT,
        )

    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.rect(0, 0.84 * cm, width, 0.18 * cm, fill=1, stroke=0)
    canvas.setFont(body_font, 8.2)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(1.35 * cm, 0.38 * cm, "Departament d'Educació i Formació Professional · Informe generat automàticament")
    canvas.restoreState()


def _build_pdf_lot_incident_block_v7(
    group: Dict[str, Any],
    report_model: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
    total_width: float,
    *,
    lot_index: int,
    severity_index: int,
    incident_index: int,
) -> List[Any]:
    severity_text = _fix_encoding(group.get("severity") or "-")
    deadline_text = _orientative_deadline_text(group.get("termini_dies"), group.get("severity"))

    def _section_heading(label: str, code: str) -> Paragraph:
        return safe_pdf_markup_paragraph(
            f'<a name="{_lot_incident_section_anchor_name(lot_index, severity_index, incident_index, code)}"/>{safe_pdf_text(label)}',
            styles["subsection_heading"],
            fallback_text=label,
        )

    def _section_block(label: str, code: str, body_value: Any, body_style_key: str = "body") -> KeepTogether:
        return KeepTogether(
            [
                _section_heading(label, code),
                safe_pdf_paragraph(body_value or "-", styles[body_style_key]),
            ]
        )

    blocks: List[Any] = [
        safe_pdf_markup_paragraph(
            (
                f"<b>Check:</b> {safe_pdf_text(group.get('check') or '-')} | "
                f"<b>Severitat:</b> {safe_pdf_text(severity_text)} | "
                f"<b>Termini orientatiu:</b> {safe_pdf_text(deadline_text)}"
            ),
            styles["meta"],
            fallback_text=f"Check: {group.get('check') or '-'} | Severitat: {severity_text} | Termini orientatiu: {deadline_text}",
        ),
        Spacer(1, 0.08 * cm),
        _section_block("a) Què s'ha detectat", "a", group.get("description") or "-"),
        Spacer(1, 0.05 * cm),
        _section_block("b) Impacte", "b", group.get("impacte") or "-"),
        Spacer(1, 0.05 * cm),
        _section_heading("c) Esquemes afectats", "c"),
    ]
    for schema_group in group.get("schemas") or []:
        blocks.append(safe_pdf_bullet_paragraph(f"{_fix_encoding(schema_group.get('nom') or '-')} ({schema_group.get('object_count') or 0} objectes)", styles["body"]))
    rows = _build_incident_objects_table_rows_v6(group)
    if rows:
        blocks.extend([
            Spacer(1, 0.12 * cm),
            _section_heading("d) Objectes afectats", "d"),
            _build_post_crq_table(list(rows[0].keys()), rows, total_width, styles, table_kind="object_table"),
        ])
    blocks.extend([
        Spacer(1, 0.14 * cm),
        _section_block("e) Acció requerida", "e", group.get("accio_recomanada") or "-"),
        Spacer(1, 0.05 * cm),
        _section_block("f) Validació posterior", "f", group.get("validacio_posterior") or "-"),
        Spacer(1, 0.2 * cm),
    ])
    return blocks


def _build_post_crq_markdown_from_report_model_final_v7(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [
        f"# Informe d'auditoria post-CRQ — {_fix_encoding(profile)}",
        "",
        f"Data de generació: {_fix_encoding((report_model.get('execution_parameters') or {}).get('generated_at') or '-')}",
        f"Finestra auditada: {_resolve_report_time_window_label_final_v3((report.get('context') or {}).get('time_filter') or {})}",
        f"Resum global: {_report_operational_cover_summary_v4(report_model)}",
        "",
        "## 1. Índex",
    ]
    anchor_map = _post_crq_section_anchor_map_v7(bool(annex_entries))
    for entry in _report_operational_index_entries_v7(bool(annex_entries)):
        anchor = anchor_map.get(entry)
        if anchor:
            lines.append(f"- [{entry}](#{anchor})")
        else:
            lines.append(f"- {entry}")
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        lines.extend(["", "## Checks inclosos en l'informe"])
        for line in enabled_checks.split(", "):
            lines.append(f"- {_fix_encoding(line)}")
    lines.extend(["", "## 2. Context de l'auditoria"])
    for label, value in _report_parameter_rows_v5(report):
        if label == "Checks activats":
            continue
        lines.append(f"- **{label}:** {_fix_encoding(value)}")
    lines.extend(["", "## 3. Resum executiu post-CRQ", "Aquest apartat resumeix, per a cada lot, el volum d'incidències detectades i la seva prioritat per iniciar la correcció.", ""])
    lot_rows = _report_lot_counts_rows_v5(report_model)
    if lot_rows:
        lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes"], lot_rows, limit=None))
    else:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    lines.extend(["", "## 4. Incidències prioritzades per criticitat i lot", ""])
    for section_id, section_title, groups in _group_lot_incidents_by_criticality_v7(report_model):
        lines.append(f"### {section_id} {section_title}")
        if groups:
            for group in groups:
                lines.extend(_markdown_lot_incident_group_lines_v2(group))
        else:
            lines.append(f"No hi ha {section_title.lower()} en aquesta execució.")
        lines.append("")
    lines.extend(["## 5. Resultat detallat per check", ""])
    for section in report_model.get("detail_sections") or []:
        detail_check_id = str(section.get("check_id") or "").strip()
        lines.append(f"### {detail_check_id} — {_fix_encoding(_display_title(section.get('title')))}")
        # S'elimina la severitat (Criticitat) segons la petició de l'usuari
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        
        active_cols = section.get("columns") or []
        active_rows = section.get("rows") or []

        # Filtrat de columnes IA per al CHECK_11 en el detall (Markdown)
        if detail_check_id.upper() == "CHECK_11":
            exclude_keywords = [
                "IA", "EXPLICACIO", "RECOMANACIO", "CLASSIFICACIO", 
                "CONFIANCA", "ESTAT_ANALISI", "SEVERITAT", "CRITICITAT"
            ]
            keep_indices = []
            for i, col in enumerate(active_cols):
                col_upper = str(col).upper()
                if not any(k in col_upper for k in exclude_keywords):
                    keep_indices.append(i)
            
            active_cols = [active_cols[i] for i in keep_indices]
            new_rows = []
            for row in active_rows:
                if isinstance(row, (list, tuple)):
                    new_rows.append([row[i] for i in keep_indices if i < len(row)])
                else:
                    new_rows.append(row)
            active_rows = new_rows

        if active_rows:
            lines.append(_rows_to_markdown_table(active_cols, active_rows, limit=None))
        lines.append("")
    lines.extend(["## 6. Observacions finals", ""])
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- {item.get('check_id') or '-'}: {_fix_encoding(item.get('error') or 'Error no detallat')}")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
    if annex_entries:
        lines.extend(["", "## 7. Annex A — anàlisi funcional de cada check", ""])
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} — {_fix_encoding(entry['title'])}")
            lines.extend([
                f"- **Què detecta:** {_fix_encoding(entry['que_detecta'])}",
                "",
                f"- **Per què és important:** {_fix_encoding(entry['per_que_es_important'])}",
                "",
                f"- **Impacte sobre el lot:** {_fix_encoding(entry['impacte_sobre_lot'])}",
                "",
                f"- **Com revisar:** {_fix_encoding(entry['com_revisar'])}",
                "",
                f"- **Com corregir:** {_fix_encoding(entry['com_corregir'])}",
                "",
                f"- **Validació posterior:** {_fix_encoding(entry['validacio_posterior'])}",
            ])
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _build_post_crq_pdf_from_report_model_final_v7(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = _resolve_post_crq_cover_path()
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover_final_v7(canvas, profile, generated_at, cover_path, report_model, context.get("time_filter") or {})),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer_final_v5(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer_final_v5(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
    ])
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    # Calculate usable width once
    usable_width = doc.width if hasattr(doc, 'width') else (A4[0] - doc.leftMargin - doc.rightMargin)

    toc_entries = _build_post_crq_dynamic_toc_entries(report_model, bool(annex_entries))
    story.append(_centered_heading_block("Índex", "index", styles, usable_width))
    story.append(_build_post_crq_toc_block(toc_entries, styles, usable_width))

    enabled_checks = _sort_check_dicts(report_model.get("enabled_checks") or [])
    detail_anchorable_checks = {
        str(section.get("check_id") or "").strip()
        for section in (report_model.get("detail_sections") or [])
        if str(section.get("check_id") or "").strip()
    }
    if enabled_checks:
        story.append(Spacer(1, 0.55 * cm))
        story.append(
            _build_check_index_block(
                enabled_checks,
                styles,
                usable_width,
                anchor_builder=lambda check_id: _detail_anchor_name(check_id) if str(check_id or "").strip() in detail_anchorable_checks else None,
            )
        )

    story.append(PageBreak())
    story.append(_linked_heading("1. Context de l'auditoria", "context", styles))
    parameter_rows = [(label, value) for label, value in _report_parameter_rows_v5(report) if label != "Checks activats"]
    story.append(_build_labeled_pdf_table_v2([(safe_pdf_text(label), safe_pdf_text(value)) for label, value in parameter_rows], usable_width, styles, table_kind="label_table_large"))

    story.append(Spacer(1, 0.28 * cm))
    story.append(_linked_heading("2. Resum executiu post-CRQ", "resum", styles))
    story.append(safe_pdf_paragraph("Aquest apartat resumeix, per a cada lot, el volum d'incidències detectades i la seva prioritat per iniciar la correcció.", styles["lead"]))
    lot_rows = _report_lot_counts_rows_v5(report_model)
    if lot_rows:
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes"], lot_rows, usable_width, styles, table_kind="summary_table"))
    else:
        story.append(safe_pdf_paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))

    story.append(PageBreak())
    story.append(_linked_heading("3. Incidències prioritzades per criticitat i lot", "incidencies", styles))
    lot_blocks = _group_lot_incidents_by_lot_v7(report_model)
    if not lot_blocks:
        story.append(safe_pdf_paragraph("No hi ha incidències prioritzades per lots en aquesta execució.", styles["body"]))
    for lot_index, (lot_name, severity_blocks) in enumerate(lot_blocks, start=1):
        if lot_index > 1:
            story.append(PageBreak())
        lot_heading = f"3.{lot_index} LOT {_fix_encoding(lot_name)}"
        story.append(
            safe_pdf_markup_paragraph(
                f'<a name="{_lot_anchor_name(lot_index)}"/>{safe_pdf_text(lot_heading)}',
                styles["check_heading"],
                fallback_text=lot_heading,
            )
        )
        story.append(Spacer(1, 0.08 * cm))
        story.append(safe_pdf_paragraph(_build_lot_headline_v6({"lot": lot_name}, report_model), styles["lead"]))
        story.append(Spacer(1, 0.12 * cm))
        ordered_severity_blocks = sorted(severity_blocks, key=lambda item: _criticality_rank(item[0]), reverse=True)
        for severity_index, (severity_key, _, groups) in enumerate(ordered_severity_blocks, start=1):
            section_title = {
                "CRITIC": "Incidències crítiques",
                "MITJA": "Incidències mitjanes",
                "BAIX": "Incidències baixes",
            }.get(severity_key, "Incidències")
            severity_heading = f"3.{lot_index}.{severity_index} {section_title}"
            severity_color = _severity_badge_hex(severity_key)
            story.append(
                safe_pdf_markup_paragraph(
                    f'<a name="{_lot_severity_anchor_name(lot_index, severity_index)}"/><font color="{severity_color}">{safe_pdf_text(severity_heading)}</font>',
                    styles["severity_heading"],
                    fallback_text=severity_heading,
                )
            )
            story.append(Spacer(1, 0.06 * cm))
            for incident_index, group in enumerate(groups, start=1):
                incident_heading = (
                    f"3.{lot_index}.{severity_index}.{_lettered_index(incident_index)}.- "
                    f"{_fix_encoding(_display_title(group.get('title') or group.get('check') or '-'))}"
                )
                story.append(
                    safe_pdf_markup_paragraph(
                        f'<a name="{_lot_incident_anchor_name(lot_index, severity_index, incident_index)}"/>{safe_pdf_text(incident_heading)}',
                        styles["incident_heading"],
                        fallback_text=incident_heading,
                    )
                )
                story.extend(
                    _build_pdf_lot_incident_block_v7(
                        group,
                        report_model,
                        styles,
                        usable_width,
                        lot_index=lot_index,
                        severity_index=severity_index,
                        incident_index=incident_index,
                    )
                )
            story.append(Spacer(1, 0.1 * cm))

    story.append(Spacer(1, 0.26 * cm))
    story.append(_linked_heading("4. Resultat detallat per check", "detall", styles))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        detail_check_id = str(section.get("check_id") or "").strip()
        detail_title = _fix_encoding(_display_title(section.get("title") or detail_check_id))
        story.append(
            safe_pdf_markup_paragraph(
                f'<a name="{_detail_anchor_name(detail_check_id)}"/><b>{safe_pdf_text(detail_check_id)}</b> — {safe_pdf_text(detail_title)}',
                styles["check_heading"],
                fallback_text=f"{detail_check_id} - {detail_title}",
            )
        )
        # S'elimina la severitat (Criticitat) segons la petició de l'usuari
        story.append(safe_pdf_label_value_paragraph("Temps d'execució", _humanize_duration_ms_v2(section.get("duration_ms") or 0), styles["body"]))
        
        active_cols = section.get("columns") or []
        active_rows = section.get("rows") or []

        # Filtrat de columnes IA per al CHECK_11 en el detall
        if detail_check_id.upper() == "CHECK_11":
            exclude_keywords = [
                "IA", "EXPLICACIO", "RECOMANACIO", "CLASSIFICACIO", 
                "CONFIANCA", "ESTAT_ANALISI", "SEVERITAT", "CRITICITAT"
            ]
            keep_indices = []
            for i, col in enumerate(active_cols):
                col_upper = str(col).upper()
                if not any(k in col_upper for k in exclude_keywords):
                    keep_indices.append(i)
            
            active_cols = [active_cols[i] for i in keep_indices]
            new_rows = []
            for row in active_rows:
                if isinstance(row, (list, tuple)):
                    new_rows.append([row[i] for i in keep_indices if i < len(row)])
                else:
                    new_rows.append(row)
            active_rows = new_rows

        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(active_cols, active_rows, current_width, styles, table_kind="detail_table"))
        story.append(NextPageTemplate("portrait"))

    story.append(PageBreak())
    story.append(_linked_heading("5. Observacions finals", "observacions", styles))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["subsection_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(safe_pdf_paragraph(f"{item.get('check_id') or '-'}: {item.get('error') or 'Error no detallat'}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["subsection_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(safe_pdf_bullet_paragraph(item, styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["subsection_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(safe_pdf_bullet_paragraph(item, styles["body"]))

    if annex_entries:
        story.append(PageBreak())
        story.append(_linked_heading("6. Annex A — anàlisi funcional de cada check", "annex", styles))
        story.append(Spacer(1, 0.2 * cm))
        for entry_index, entry in enumerate(annex_entries, start=1):
            if entry_index > 1:
                story.append(PageBreak())
            table_fields = ", ".join(entry.get("columnes_taula_recomanades") or [])
            story.append(
                safe_pdf_markup_paragraph(
                    _md_to_pdf_tags(f"<b>{_safe_xml(entry['check_id'])} — {_safe_xml(entry['title'])}</b>"),
                    styles["card_title"],
                    fallback_text=f"{entry['check_id']} — {entry['title']}",
                )
            )
            annex_items = [
                ("Què detecta", entry.get("que_detecta") or "-"),
                ("Per què és important", entry.get("per_que_es_important") or "-"),
                ("Impacte sobre el lot", entry.get("impacte_sobre_lot") or "-"),
                ("Com revisar", entry.get("com_revisar") or "-"),
                ("Com corregir", entry.get("com_corregir") or "-"),
                ("Validació posterior", entry.get("validacio_posterior") or "-"),
            ]

            for label, value in annex_items:
                story.append(
                    safe_pdf_markup_paragraph(
                        _md_to_pdf_tags(
                            f"<font color='{PDF_BRAND_NAVY.hexval()}'><b>{_safe_xml(label)}:</b></font> {_safe_xml(value)}"
                        ),
                        styles["annex_body"],
                        fallback_text=f"{label}: {value}",
                    )
                )

    doc.build(story)
    return buffer.getvalue()


def _build_post_crq_pdf_from_report_model_safe_fallback(profile: str, report: Dict[str, Any]) -> bytes:
    _register_post_crq_pdf_fonts()
    styles = _build_post_crq_paragraph_styles()
    markdown = _build_post_crq_markdown_from_report_model_final_v7(profile, report)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    def _fallback_anchor_for_heading(text: str) -> Optional[str]:
        normalized = _fix_encoding(text).strip()
        mapping = {"1. Índex": "index"}
        mapping.update(_post_crq_section_anchor_map_v7(True))
        return mapping.get(normalized)

    def _fallback_inline_markup(text: str) -> str:
        raw = _fix_encoding(text or "")
        tokens: Dict[str, str] = {}
        token_index = 0

        def _reserve(rendered: str) -> str:
            nonlocal token_index
            key = f"__PDFTOKEN_{token_index}__"
            token_index += 1
            tokens[key] = rendered
            return key

        raw = re.sub(
            r"\[([^\]]+)\]\((#[^)]+)\)",
            lambda match: _reserve(_safe_xml(match.group(1))),
            raw,
        )
        raw = re.sub(
            r"\*\*(.+?)\*\*",
            lambda match: _reserve(f"<b>{_safe_xml(match.group(1))}</b>"),
            raw,
        )

        escaped = _safe_xml(raw)
        for key, rendered in tokens.items():
            escaped = escaped.replace(key, rendered)
        return escaped

    def _fallback_markdown_table(block_lines: List[str]) -> Optional[Any]:
        parsed_rows: List[List[str]] = []
        for block_line in block_lines:
            parts = [part.strip() for part in block_line.strip().strip("|").split("|")]
            if parts:
                parsed_rows.append(parts)
        if len(parsed_rows) < 2:
            return None

        headers = parsed_rows[0]
        body_rows = [
            row for row in parsed_rows[1:]
            if not all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in row)
        ]
        if not headers or not body_rows:
            return None

        row_dicts = [
            {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
            for row in body_rows
        ]
        return _build_post_crq_table(headers, row_dicts, doc.width, styles)

    story: List[Any] = []
    markdown_lines = str(markdown).splitlines()
    index = 0
    while index < len(markdown_lines):
        raw_line = markdown_lines[index]
        line = raw_line.strip()

        if not line:
            story.append(Spacer(1, 0.14 * cm))
            index += 1
            continue

        if line.startswith("|"):
            table_block: List[str] = []
            while index < len(markdown_lines) and markdown_lines[index].strip().startswith("|"):
                table_block.append(markdown_lines[index].strip())
                index += 1
            table = _fallback_markdown_table(table_block)
            if table is not None:
                story.append(table)
                story.append(Spacer(1, 0.12 * cm))
            continue

        if line.startswith("# "):
            title = line[2:]
            anchor = _fallback_anchor_for_heading(title)
            prefix = f'<a name="{anchor}"/>' if anchor else ""
            story.append(safe_pdf_markup_paragraph(f"{prefix}{_fallback_inline_markup(title)}", styles["heading"], fallback_text=title))
        elif line.startswith("## "):
            title = line[3:]
            anchor = _fallback_anchor_for_heading(title)
            prefix = f'<a name="{anchor}"/>' if anchor else ""
            story.append(safe_pdf_markup_paragraph(f"{prefix}{_fallback_inline_markup(title)}", styles["heading"], fallback_text=title))
        elif line.startswith("### "):
            story.append(safe_pdf_markup_paragraph(_fallback_inline_markup(line[4:]), styles["check_heading"], fallback_text=line[4:]))
        elif line.startswith("- "):
            story.append(safe_pdf_markup_paragraph(f"• {_fallback_inline_markup(line[2:])}", styles["body"], fallback_text=f"• {line[2:]}"))
        else:
            story.append(safe_pdf_markup_paragraph(_fallback_inline_markup(line), styles["body"], fallback_text=line))
        index += 1
    try:
        doc.build(story)
        return buffer.getvalue()
    except Exception:
        plain_buffer = io.BytesIO()
        plain_doc = SimpleDocTemplate(
            plain_buffer,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )
        plain_base_styles = getSampleStyleSheet()
        plain_styles = {
            "heading": ParagraphStyle("FallbackHeading", parent=plain_base_styles["Heading2"], fontSize=12, leading=14, spaceAfter=8, spaceBefore=8),
            "check_heading": ParagraphStyle("FallbackCheckHeading", parent=plain_base_styles["Heading3"], fontSize=10.5, leading=12.5, spaceAfter=6, spaceBefore=4),
            "body": ParagraphStyle("FallbackBody", parent=plain_base_styles["Normal"], fontSize=8.5, leading=10.8),
            "table_header": ParagraphStyle("FallbackTableHeader", parent=plain_base_styles["Normal"], fontSize=6.2, leading=7.0, alignment=TA_CENTER, textColor=rl_colors.white),
            "table_header_tight": ParagraphStyle("FallbackTableHeaderTight", parent=plain_base_styles["Normal"], fontSize=6.0, leading=6.8, alignment=TA_CENTER, textColor=rl_colors.white),
            "table_cell": ParagraphStyle("FallbackTableCell", parent=plain_base_styles["Normal"], fontSize=6.0, leading=7.0),
            "table_cell_tight": ParagraphStyle("FallbackTableCellTight", parent=plain_base_styles["Normal"], fontSize=5.8, leading=6.6),
            "table_cell_center": ParagraphStyle("FallbackTableCellCenter", parent=plain_base_styles["Normal"], fontSize=6.0, leading=7.0, alignment=TA_CENTER),
            "table_cell_center_tight": ParagraphStyle("FallbackTableCellCenterTight", parent=plain_base_styles["Normal"], fontSize=5.8, leading=6.6, alignment=TA_CENTER),
        }

        def _plain_markdown_table(block_lines: List[str]) -> Optional[Any]:
            parsed_rows: List[List[str]] = []
            for block_line in block_lines:
                parts = [part.strip() for part in block_line.strip().strip("|").split("|")]
                if parts:
                    parsed_rows.append(parts)
            if len(parsed_rows) < 2:
                return None

            headers = parsed_rows[0]
            body_rows = [
                row for row in parsed_rows[1:]
                if not all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in row)
            ]
            if not headers or not body_rows:
                return None

            row_dicts = [
                {header: row[idx] if idx < len(row) else "" for idx, header in enumerate(headers)}
                for row in body_rows
            ]
            return _build_post_crq_table(headers, row_dicts, plain_doc.width, plain_styles)

        plain_story: List[Any] = []
        index = 0
        while index < len(markdown_lines):
            raw_line = markdown_lines[index]
            line = raw_line.strip()

            if not line:
                plain_story.append(Spacer(1, 0.14 * cm))
                index += 1
                continue

            if line.startswith("|"):
                table_block: List[str] = []
                while index < len(markdown_lines) and markdown_lines[index].strip().startswith("|"):
                    table_block.append(markdown_lines[index].strip())
                    index += 1
                table = _plain_markdown_table(table_block)
                if table is not None:
                    plain_story.append(table)
                    plain_story.append(Spacer(1, 0.12 * cm))
                continue

            if line.startswith("# "):
                plain_story.append(safe_pdf_paragraph(line[2:], plain_styles["heading"]))
            elif line.startswith("## "):
                plain_story.append(safe_pdf_paragraph(line[3:], plain_styles["heading"]))
            elif line.startswith("### "):
                plain_story.append(safe_pdf_paragraph(line[4:], plain_styles["check_heading"]))
            elif line.startswith("- "):
                plain_story.append(safe_pdf_paragraph(f"• {_plain_text_from_markup(line[2:])}", plain_styles["body"]))
            else:
                plain_story.append(safe_pdf_paragraph(_plain_text_from_markup(line), plain_styles["body"]))
            index += 1

        plain_doc.build(plain_story)
        return plain_buffer.getvalue()


# === Final runtime renderer overrides ===
def _resolve_report_time_window_label_v2(time_filter: Dict[str, Any]) -> str:
    return _fix_encoding(_display_period_window(time_filter or {}))


def _build_post_crq_markdown_from_report_model_v2(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [f"# Informe d'auditoria post-CRQ — {_fix_encoding(profile)}", "", "## 1. Índex"]
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        lines.append(f"- {entry}")
    lines.extend(["", "## 2. Paràmetres d'execució", ""])
    for label, value in _report_model_parameters_rows_v2(report):
        lines.append(f"- **{label}:** {value}")
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        lines.extend(["", "### Checks activats"])
        if isinstance(enabled_checks, str):
            lines.append(enabled_checks)
        else:
            lines.extend(enabled_checks)
    lines.extend(["", "## 3. Resum executiu per lots", "", "Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", ""])
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, limit=None))
    else:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    lines.extend(["", "## 4. Incidències prioritzades per lot", ""])
    for group in report_model.get("lot_incident_groups") or []:
        lines.extend(_markdown_lot_incident_group_lines_v2(group))
        lines.append("")
    if not (report_model.get("lot_incident_groups") or []):
        lines.append("No hi ha incidències prioritzades per lot en aquesta execució.")
    lines.extend(["", "## 5. Resultat detallat per check", ""])
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {_fix_encoding(section.get('criticality') or 'Baix')}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")
    lines.extend(["## 6. Observacions finals", ""])
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if annex_entries:
        lines.extend(["## 7. Annex A - Guia funcional dels checks", ""])
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- **Què detecta:** {entry['que_detecta']}")
            lines.append(f"- **Per què és important:** {entry['per_que_es_important']}")
            lines.append(f"- **Impacte sobre el lot:** {entry['impacte_sobre_lot']}")
            lines.append(f"- **Com s'ha de revisar:** {entry['com_revisar']}")
            lines.append(f"- **Com es pot corregir:** {entry['com_corregir']}")
            lines.append(f"- **Limitacions o falsos positius:** {entry['limitacions']}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {entry['validacio_posterior']}")
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _post_crq_pdf_cover(canvas, doc, profile, generated_at, cover_path, context, summary, time_filter):
    width, height = A4
    canvas.saveState()
    if cover_path and cover_path.exists():
        image_width = width - (2.4 * cm)
        image_height = height * 0.56
        image_x = 1.2 * cm
        image_y = height - image_height - 1.25 * cm
        canvas.drawImage(
            str(cover_path),
            image_x,
            image_y,
            width=image_width,
            height=image_height,
            preserveAspectRatio=True,
            anchor="n",
            mask="auto",
        )
    canvas.setFillColor(rl_colors.HexColor("#0f172a"))
    canvas.roundRect(1.2 * cm, 1.8 * cm, width - (2.4 * cm), 6.2 * cm, 12, fill=1, stroke=0)
    canvas.setFillColor(rl_colors.white)
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit-Regular" if "OracleAudit-Regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFont(title_font, 22)
    canvas.drawString(1.9 * cm, 7.2 * cm, "Informe d'auditoria post-CRQ")
    canvas.setFont(body_font, 11)
    for index, line in enumerate(
        [
            f"Perfil: {_fix_encoding(profile)}",
            f"Data de generació: {_fix_encoding(generated_at or '-')}",
            f"Finestra auditada: {_resolve_report_time_window_label_v2(time_filter)}",
            f"Període aplicat: {_fix_encoding(_display_period_label(time_filter))}",
            f"Resum global: {summary.get('checks_with_findings', 0)} checks amb troballes; {summary.get('critical_findings', 0)} incidències crítiques",
        ]
    ):
        canvas.drawString(1.9 * cm, 6.3 * cm - (index * 0.7 * cm), line)
    canvas.restoreState()


def _build_post_crq_pdf_from_report_model_v2(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover(canvas, current_doc, profile, generated_at, cover_path, context, summary, context.get("time_filter") or {})),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
    ])
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]
    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph("Checks activats", styles["check_heading"]))
        if isinstance(enabled_checks, str):
            story.append(Paragraph(html.escape(enabled_checks), styles["body"]))
        else:
            for line in enabled_checks:
                story.append(Paragraph(html.escape(line), styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    story.append(Paragraph("Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", styles["body"]))
    lot_rows = _build_lot_summary_rows_v2(report_model)
    story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, doc.width, styles) if lot_rows else Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("4. Incidències prioritzades per lot", styles["heading"]))
    for group in report_model.get("lot_incident_groups") or []:
        story.extend(_build_pdf_lot_incident_block_v2(group, styles, doc.width))
        story.append(Spacer(1, 0.18 * cm))
    if not (report_model.get("lot_incident_groups") or []):
        story.append(Paragraph("No hi ha incidències prioritzades per lot en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("5. Resultat detallat per check", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Temps d'execució:</b> {html.escape(_humanize_duration_ms_v2(section.get('duration_ms') or 0))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex A - Guia funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(entry['que_detecta'])}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(entry['per_que_es_important'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(entry['impacte_sobre_lot'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(entry['com_revisar'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(entry['com_corregir'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(entry['validacio_posterior'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))
    doc.build(story)
    return buffer.getvalue()

# Final active overrides for report-model rendering.
def _resolve_report_time_window_label_v2(time_filter: Dict[str, Any]) -> str:
    return _fix_encoding(_display_period_window(time_filter or {}))


def _report_model_index_entries_v2(include_annex: bool) -> List[str]:
    entries = [
        "1. Portada",
        "2. Índex",
        "3. Paràmetres d'execució",
        "4. Resum executiu per lots",
        "5. Incidències prioritzades per lot",
        "6. Resultat detallat per check",
        "7. Observacions finals",
    ]
    if include_annex:
        entries.append("8. Annex funcional dels checks")
    return entries


def _report_model_parameters_rows_v2(report: Dict[str, Any]) -> List[tuple[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    time_filter = context.get("time_filter") or {}
    schemas = execution_parameters.get("schemas") or context.get("schemas") or []
    return [
        ("Perfil", _fix_encoding(execution_parameters.get("profile") or context.get("profile") or "-")),
        ("Data i hora", _fix_encoding(execution_parameters.get("generated_at") or context.get("generated_at") or "-")),
        ("Mode temporal", _fix_encoding(_display_time_mode(time_filter))),
        ("Període aplicat", _fix_encoding(_display_period_label(time_filter))),
        ("Finestra consultada", _resolve_report_time_window_label_v2(time_filter)),
        ("Idioma", _fix_encoding(execution_parameters.get("language") or "Català")),
        ("Codificació", _fix_encoding(execution_parameters.get("encoding") or "UTF-8")),
        ("Fitxer de checks", _fix_encoding(execution_parameters.get("source_file") or context.get("source_file") or "-")),
        ("Lots o esquemes filtrats", _fix_encoding(", ".join(schemas) if schemas else "Tots")),
    ]


def _build_lot_summary_rows_v2(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "Lot": _fix_encoding(item.get("lot") or "SENSE LOT"),
            "Crítiques": item.get("critical") or 0,
            "Mitjanes": item.get("medium") or 0,
            "Baixes": item.get("low") or 0,
            "Checks afectats": _fix_encoding(", ".join(item.get("checks") or []) or "-"),
            "Acció inicial": _fix_encoding(item.get("first_action") or "-"),
            "Impacte principal": _fix_encoding(item.get("dominant_impact") or "-"),
            "Prioritat": _fix_encoding(item.get("priority") or "Baix"),
        }
        for item in (report_model.get("lot_summary") or [])
    ]


def _build_enabled_checks_text_v2(report_model: Dict[str, Any]) -> List[str]:
    return [
        f"- {_fix_encoding(item.get('check_id') or '-')}: {_fix_encoding(_display_title(item.get('title') or '-'))} [{_fix_encoding(item.get('criticality') or '-')}]"
        for item in (report_model.get("enabled_checks") or [])
    ]


def _markdown_lot_incident_group_lines_v2(group: Dict[str, Any]) -> List[str]:
    lines = [
        f"#### Lot: {_fix_encoding(group.get('lot') or 'SENSE LOT')}",
        f"- Check: {_fix_encoding(group.get('check') or '-')}",
        f"- Descripció del check: {_fix_encoding(group.get('description') or group.get('title') or '-')}",
        f"- Severitat: {_fix_encoding(group.get('severity') or '-')}",
        f"- Termini dies: {group.get('termini_dies') if group.get('termini_dies') is not None else '-'}",
        f"- Impacte sobre el lot: {_fix_encoding(group.get('impacte') or '-')}",
        f"- Acció recomanada: {_fix_encoding(group.get('accio_recomanada') or '-')}",
        f"- Validació posterior: {_fix_encoding(group.get('validacio_posterior') or '-')}",
        "- Esquemes afectats:",
    ]
    for schema_group in group.get("schemas") or []:
        lines.append(f"  - nom: {_fix_encoding(schema_group.get('nom') or '-')}")
        lines.append("    taules:")
        for objecte in schema_group.get("objectes") or []:
            lines.append(f"      - {_fix_encoding(objecte.get('nom') or '-')}")
    return lines


def _build_post_crq_markdown_from_report_model_v2(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [f"# Informe d'auditoria post-CRQ — {_fix_encoding(profile)}", "", "## 1. Índex"]
    lines.extend(f"- {entry}" for entry in _report_model_index_entries_v2(bool(annex_entries)))
    lines.extend(["", "## 2. Paràmetres d'execució", ""])
    for label, value in _report_model_parameters_rows_v2(report):
        lines.append(f"- **{label}:** {value}")
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        lines.extend(["", "### Checks activats"])
        lines.extend(enabled_checks)
    lines.extend(["", "## 3. Resum executiu per lots", "", "Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", ""])
    lot_rows = _build_lot_summary_rows_v2(report_model)
    lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, limit=None) if lot_rows else "No s'han detectat lots amb incidències en aquesta execució.")
    lines.extend(["", "## 4. Incidències prioritzades per lot", ""])
    if report_model.get("lot_incident_groups"):
        for group in report_model.get("lot_incident_groups") or []:
            lines.extend(_markdown_lot_incident_group_lines_v2(group))
            lines.append("")
    else:
        lines.append("No hi ha incidències prioritzades per lot en aquesta execució.")
    lines.extend(["", "## 5. Resultat detallat per check", ""])
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {_fix_encoding(section.get('criticality') or 'Baix')}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")
    lines.extend(["## 6. Observacions finals", ""])
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if annex_entries:
        lines.extend(["## 7. Annex funcional dels checks", ""])
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- **Què detecta:** {entry['que_detecta']}")
            lines.append(f"- **Per què és important:** {entry['per_que_es_important']}")
            lines.append(f"- **Impacte sobre el lot:** {entry['impacte_sobre_lot']}")
            lines.append(f"- **Com s'ha de revisar:** {entry['com_revisar']}")
            lines.append(f"- **Com es pot corregir:** {entry['com_corregir']}")
            lines.append(f"- **Limitacions o falsos positius:** {entry['limitacions']}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {entry['validacio_posterior']}")
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _post_crq_pdf_cover(canvas, doc, profile, generated_at, cover_path, context, summary, time_filter):
    width, height = A4
    canvas.saveState()
    if cover_path and cover_path.exists():
        image_height = height * 0.72
        canvas.drawImage(str(cover_path), 0, height - image_height, width=width, height=image_height, preserveAspectRatio=False, mask="auto")
    canvas.setFillColor(rl_colors.HexColor("#0f172a"))
    canvas.roundRect(1.2 * cm, 1.8 * cm, width - (2.4 * cm), 6.2 * cm, 12, fill=1, stroke=0)
    canvas.setFillColor(rl_colors.white)
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit-Regular" if "OracleAudit-Regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFont(title_font, 22)
    canvas.drawString(1.9 * cm, 7.2 * cm, "Informe d'auditoria post-CRQ")
    canvas.setFont(body_font, 11)
    lines = [
        f"Perfil: {_fix_encoding(profile)}",
        f"Data de generació: {_fix_encoding(generated_at or '-')}",
        f"Finestra auditada: {_resolve_report_time_window_label_v2(time_filter)}",
        f"Període aplicat: {_fix_encoding(_display_period_label(time_filter))}",
        f"Resum global: {summary.get('checks_with_findings', 0)} checks amb troballes; {summary.get('critical_findings', 0)} incidències crítiques",
    ]
    y_position = 6.3 * cm
    for line in lines:
        canvas.drawString(1.9 * cm, y_position, line)
        y_position -= 0.7 * cm
    canvas.restoreState()


def _build_pdf_lot_incident_block_v2(group: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> List[Any]:
    blocks: List[Any] = [
        _build_labeled_pdf_table_v2(
            [
                ("Lot", _fix_encoding(group.get("lot") or "SENSE LOT")),
                ("Check", _fix_encoding(group.get("check") or "-")),
                ("Descripció del check", _fix_encoding(group.get("description") or group.get("title") or "-")),
                ("Severitat", _fix_encoding(group.get("severity") or "-")),
            ],
            total_width,
            styles,
        ),
        Spacer(1, 0.1 * cm),
        Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(group.get('impacte') or '-'))}", styles["body"]),
        Paragraph(f"<b>Acció recomanada:</b> {html.escape(_fix_encoding(group.get('accio_recomanada') or '-'))}", styles["body"]),
        Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(group.get('validacio_posterior') or '-'))}", styles["body"]),
        Paragraph(f"<b>Termini orientatiu:</b> {group.get('termini_dies') if group.get('termini_dies') is not None else '-'} dies", styles["body"]),
    ]
    for schema_group in group.get("schemas") or []:
        blocks.append(Spacer(1, 0.08 * cm))
        blocks.append(Paragraph(f"<b>Esquema:</b> {html.escape(_fix_encoding(schema_group.get('nom') or '-'))} ({schema_group.get('object_count') or 0} objectes)", styles["body"]))
        object_rows = [
            {key: _fix_encoding(value) for key, value in _incident_object_table_row_v7(schema_group, item).items()}
            for item in (schema_group.get("objectes") or [])
        ]
        if object_rows:
            blocks.append(_build_post_crq_table(["OBJECTE", "TIPUS", "DADA TÈCNICA"], object_rows, total_width, styles))
    return blocks


def _build_post_crq_pdf_from_report_model_v2(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover(canvas, current_doc, profile, generated_at, cover_path, context, summary, context.get("time_filter") or {})),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
    ])
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]
    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph("Checks activats", styles["check_heading"]))
        for line in enabled_checks:
            story.append(Paragraph(html.escape(line), styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    story.append(Paragraph("Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", styles["body"]))
    lot_rows = _build_lot_summary_rows_v2(report_model)
    story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, doc.width, styles) if lot_rows else Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("4. Incidències prioritzades per lot", styles["heading"]))
    lot_incident_groups = report_model.get("lot_incident_groups") or []
    if lot_incident_groups:
        for group in lot_incident_groups:
            story.extend(_build_pdf_lot_incident_block_v2(group, styles, doc.width))
            story.append(Spacer(1, 0.18 * cm))
    else:
        story.append(Paragraph("No hi ha incidències prioritzades per lot en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("5. Resultat detallat per check", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Temps d'execució:</b> {html.escape(_humanize_duration_ms_v2(section.get('duration_ms') or 0))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(entry['que_detecta'])}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(entry['per_que_es_important'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(entry['impacte_sobre_lot'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(entry['com_revisar'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(entry['com_corregir'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(entry['validacio_posterior'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))
    doc.build(story)
    return buffer.getvalue()


def _resolve_report_time_window_label_v2(time_filter: Dict[str, Any]) -> str:
    return _fix_encoding(_display_period_window(time_filter or {}))


def _report_model_index_entries_v2(include_annex: bool) -> List[str]:
    entries = [
        "1. Portada",
        "2. Índex",
        "3. Paràmetres d'execució",
        "4. Resum executiu per lots",
        "5. Incidències prioritzades per lot",
        "6. Resultat detallat per check",
        "7. Observacions finals",
    ]
    if include_annex:
        entries.append("8. Annex funcional dels checks")
    return entries


def _report_model_parameters_rows_v2(report: Dict[str, Any]) -> List[tuple[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    time_filter = context.get("time_filter") or {}
    schemas = execution_parameters.get("schemas") or context.get("schemas") or []
    return [
        ("Perfil", _fix_encoding(execution_parameters.get("profile") or context.get("profile") or "-")),
        ("Data i hora", _fix_encoding(execution_parameters.get("generated_at") or context.get("generated_at") or "-")),
        ("Mode temporal", _fix_encoding(_display_time_mode(time_filter))),
        ("Període aplicat", _fix_encoding(_display_period_label(time_filter))),
        ("Finestra consultada", _resolve_report_time_window_label_v2(time_filter)),
        ("Idioma", _fix_encoding(execution_parameters.get("language") or "Català")),
        ("Codificació", _fix_encoding(execution_parameters.get("encoding") or "UTF-8")),
        ("Fitxer de checks", _fix_encoding(execution_parameters.get("source_file") or context.get("source_file") or "-")),
        ("Lots o esquemes filtrats", _fix_encoding(", ".join(schemas) if schemas else "Tots")),
    ]


def _build_lot_summary_rows_v2(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in report_model.get("lot_summary") or []:
        rows.append(
            {
                "Lot": _fix_encoding(item.get("lot") or "SENSE LOT"),
                "Crítiques": item.get("critical") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
                "Checks afectats": _fix_encoding(", ".join(item.get("checks") or []) or "-"),
                "Acció inicial": _fix_encoding(item.get("first_action") or "-"),
                "Impacte principal": _fix_encoding(item.get("dominant_impact") or "-"),
                "Prioritat": _fix_encoding(item.get("priority") or "Baix"),
            }
        )
    return rows


def _build_enabled_checks_text_v2(report_model: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for item in report_model.get("enabled_checks") or []:
        check_id = _fix_encoding(item.get("check_id") or "-")
        title = _fix_encoding(_display_title(item.get("title") or "-"))
        criticality = _fix_encoding(item.get("criticality") or "-")
        lines.append(f"- {check_id}: {title} [{criticality}]")
    return lines


def _markdown_lot_incident_group_lines_v2(group: Dict[str, Any]) -> List[str]:
    lines = [
        f"#### Lot: {_fix_encoding(group.get('lot') or 'SENSE LOT')}",
        f"- Check: {_fix_encoding(group.get('check') or '-')}",
        f"- Descripció del check: {_fix_encoding(group.get('description') or group.get('title') or '-')}",
        f"- Severitat: {_fix_encoding(group.get('severity') or '-')}",
        f"- Termini dies: {group.get('termini_dies') if group.get('termini_dies') is not None else '-'}",
        f"- Impacte sobre el lot: {_fix_encoding(group.get('impacte') or '-')}",
        f"- Acció recomanada: {_fix_encoding(group.get('accio_recomanada') or '-')}",
        f"- Validació posterior: {_fix_encoding(group.get('validacio_posterior') or '-')}",
        "- Esquemes afectats:",
    ]
    for schema_group in group.get("schemas") or []:
        lines.append(f"  - nom: {_fix_encoding(schema_group.get('nom') or '-')}")
        if schema_group.get("object_count") is not None:
            lines.append(f"    objectes: {schema_group.get('object_count')}")
        lines.append("    detalls:")
        for objecte in schema_group.get("objectes") or []:
            detail = _fix_encoding(objecte.get("nom") or "-")
            tipus = _fix_encoding(objecte.get("tipus") or "")
            dada = _fix_encoding(objecte.get("dada_tecnica") or "")
            accio = _fix_encoding(objecte.get("accio_recomanada") or "")
            fragments = [detail]
            if tipus:
                fragments.append(tipus)
            if dada:
                fragments.append(dada)
            if accio:
                fragments.append(f"Acció: {accio}")
            lines.append(f"      - {' · '.join(fragments)}")
    return lines


def _build_post_crq_markdown_from_report_model_v2(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [
        f"# Informe d'auditoria post-CRQ — {_fix_encoding(profile)}",
        "",
        "## 1. Índex",
    ]
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        lines.append(f"- {entry}")
    lines.extend(["", "## 2. Paràmetres d'execució", ""])
    parameter_rows = _report_model_parameters_rows_v2(report)
    for label, value in parameter_rows:
        lines.append(f"- **{label}:** {value}")
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        lines.extend(["", "### Checks activats"])
        lines.extend(enabled_checks)
    lines.extend(["", "## 3. Resum executiu per lots", "", "Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", ""])
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, limit=None))
    else:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    lines.extend(["", "## 4. Incidències prioritzades per lot", ""])
    if report_model.get("lot_incident_groups"):
        for group in report_model.get("lot_incident_groups") or []:
            lines.extend(_markdown_lot_incident_group_lines_v2(group))
            lines.append("")
    else:
        lines.append("No hi ha incidències prioritzades per lot en aquesta execució.")
    lines.extend(["", "## 5. Resultat detallat per check", ""])
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {_fix_encoding(section.get('criticality') or 'Baix')}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")
    lines.extend(["## 6. Observacions finals", ""])
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if annex_entries:
        lines.extend(["## 7. Annex funcional dels checks", ""])
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- **Què detecta:** {entry['que_detecta']}")
            lines.append(f"- **Per què és important:** {entry['per_que_es_important']}")
            lines.append(f"- **Impacte sobre el lot:** {entry['impacte_sobre_lot']}")
            lines.append(f"- **Com s'ha de revisar:** {entry['com_revisar']}")
            lines.append(f"- **Com es pot corregir:** {entry['com_corregir']}")
            lines.append(f"- **Limitacions o falsos positius:** {entry['limitacions']}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {entry['validacio_posterior']}")
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _post_crq_pdf_cover(canvas, doc, profile, generated_at, cover_path, context, summary, time_filter):
    width, height = A4
    canvas.saveState()
    if cover_path and cover_path.exists():
        image_height = height * 0.72
        canvas.drawImage(str(cover_path), 0, height - image_height, width=width, height=image_height, preserveAspectRatio=False, mask="auto")
    canvas.setFillColor(rl_colors.HexColor("#0f172a"))
    canvas.roundRect(1.2 * cm, 1.8 * cm, width - (2.4 * cm), 6.2 * cm, 12, fill=1, stroke=0)
    canvas.setFillColor(rl_colors.white)
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit-Regular" if "OracleAudit-Regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFont(title_font, 22)
    canvas.drawString(1.9 * cm, 7.2 * cm, "Informe d'auditoria post-CRQ")
    canvas.setFont(body_font, 11)
    lines = [
        f"Perfil: {_fix_encoding(profile)}",
        f"Data de generació: {_fix_encoding(generated_at or '-')}",
        f"Finestra auditada: {_resolve_report_time_window_label_v2(time_filter)}",
        f"Període aplicat: {_fix_encoding(_display_period_label(time_filter))}",
        f"Resum global: {summary.get('checks_with_findings', 0)} checks amb troballes; {summary.get('critical_findings', 0)} incidències crítiques",
    ]
    y_position = 6.3 * cm
    for line in lines:
        canvas.drawString(1.9 * cm, y_position, line)
        y_position -= 0.7 * cm
    canvas.restoreState()


def _build_pdf_lot_incident_block_v2(group: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> List[Any]:
    blocks: List[Any] = []
    blocks.append(
        _build_labeled_pdf_table_v2(
            [
                ("Lot", _fix_encoding(group.get("lot") or "SENSE LOT")),
                ("Check", _fix_encoding(group.get("check") or "-")),
                ("Descripció del check", _fix_encoding(group.get("description") or group.get("title") or "-")),
                ("Severitat", _fix_encoding(group.get("severity") or "-")),
            ],
            total_width,
            styles,
        )
    )
    blocks.append(Spacer(1, 0.1 * cm))
    blocks.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(group.get('impacte') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Acció recomanada:</b> {html.escape(_fix_encoding(group.get('accio_recomanada') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(group.get('validacio_posterior') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Termini orientatiu:</b> {group.get('termini_dies') if group.get('termini_dies') is not None else '-'} dies", styles["body"]))
    for schema_group in group.get("schemas") or []:
        blocks.append(Spacer(1, 0.08 * cm))
        blocks.append(
            Paragraph(
                f"<b>Esquema:</b> {html.escape(_fix_encoding(schema_group.get('nom') or '-'))} "
                f"({schema_group.get('object_count') or 0} objectes)",
                styles["body"],
            )
        )
        object_rows = [
            {key: _fix_encoding(value) for key, value in _incident_object_table_row_v7(schema_group, item).items()}
            for item in (schema_group.get("objectes") or [])
        ]
        if object_rows:
            blocks.append(_build_post_crq_table(["OBJECTE", "TIPUS", "DADA TÈCNICA"], object_rows, total_width, styles))
    return blocks


def _build_post_crq_pdf_from_report_model_v2(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover(canvas, current_doc, profile, generated_at, cover_path, context, summary, context.get("time_filter") or {})),
            PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
            PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        ]
    )
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]
    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph("Checks activats", styles["check_heading"]))
        for line in enabled_checks:
            story.append(Paragraph(html.escape(line), styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    story.append(Paragraph("Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", styles["body"]))
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, doc.width, styles))
    else:
        story.append(Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("4. Incidències prioritzades per lot", styles["heading"]))
    lot_incident_groups = report_model.get("lot_incident_groups") or []
    if lot_incident_groups:
        for group in lot_incident_groups:
            story.extend(_build_pdf_lot_incident_block_v2(group, styles, doc.width))
            story.append(Spacer(1, 0.18 * cm))
    else:
        story.append(Paragraph("No hi ha incidències prioritzades per lot en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("5. Resultat detallat per check", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Temps d'execució:</b> {html.escape(_humanize_duration_ms_v2(section.get('duration_ms') or 0))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(entry['que_detecta'])}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(entry['per_que_es_important'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(entry['impacte_sobre_lot'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(entry['com_revisar'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(entry['com_corregir'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(entry['validacio_posterior'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))
    doc.build(story)
    return buffer.getvalue()
def _extract_check12_ai_summary(executed_checks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    item = next((current for current in executed_checks if current.get("check_id") == "CHECK_12"), None)
    if not item:
        return None
    ai_summary = item.get("ai_analysis", {}).get("summary") if isinstance(item.get("ai_analysis"), dict) else None
    return {
        "total_findings": int(item.get("row_count", 0)),
        "mala_praxis": int((ai_summary or {}).get("mala_praxis", 0)),
        "falso_positivo": int((ai_summary or {}).get("falso_positivo", 0)),
        "revision_manual": int((ai_summary or {}).get("revision_manual", 0)),
        "estat_analisi_ia": (item.get("ai_analysis") or {}).get("status") if isinstance(item.get("ai_analysis"), dict) else "no disponible",
        "model_ia": (item.get("ai_analysis") or {}).get("model") if isinstance(item.get("ai_analysis"), dict) else None,
    }


def _build_queries_txt(
    profile: str,
    source_path: str,
    selected_ids: List[str],
    normalized_filter: Dict[str, Any],
    schemas: List[str],
    executed_checks: List[Dict[str, Any]],
) -> str:
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "AUDITORIA BBDD POST-CRQ - CONSULTES EXECUTADES",
        f"Perfil: {profile}",
        f"Generat: {generated_at}",
        f"Font de consultes: {os.path.basename(source_path)}",
        f"Ruta font de consultes: {source_path}",
        f"Checks seleccionats: {', '.join(selected_ids) if selected_ids else 'TOTS'}",
        f"Esquemes filtrats: {', '.join(schemas) if schemas else 'TOTS'}",
        f"Mode temporal: {normalized_filter.get('mode') or 'preset'}",
        f"PerÃ­ode aplicat: {normalized_filter.get('preset') or (str(normalized_filter.get('start_date')) + ' -> ' + str(normalized_filter.get('end_date')))}",
        f"Dies enrere resolts: {normalized_filter.get('days_back')}",
        "",
    ]

    for item in executed_checks:
        lines.extend(
            [
                "=" * 92,
                f"{item.get('check_id')} - {item.get('title')}",
                f"Criticitat: {_criticality_label(item.get('criticitat_key'))}",
                f"Temps: {item.get('duration_ms', 0)} ms",
                f"Font: {item.get('source_file') or os.path.basename(source_path)}",
                f"Filtres empesos a SQL: esquema={item.get('schema_filter_pushed', False)} | temporal={item.get('time_filter_pushed', False)}",
                "BINDS:",
            ]
        )
        bind_lines = item.get("sql_binds") or {}
        if bind_lines:
            for bind_name, bind_value in bind_lines.items():
                lines.append(f"  - {bind_name} = {bind_value}")
        else:
            lines.append("  - (sense binds)")
        lines.extend(
            [
                "",
                "SQL EXECUTAT:",
                item.get("executed_sql") or "",
                "",
                "SQL EXPANDIT PER PROVA MANUAL:",
                item.get("rendered_sql") or "",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _run_single_post_crq_check(
    check: Dict[str, Any],
    db_manager: Any,
    normalized_filter: Dict[str, Any],
    cleaned_schemas: List[str],
    days_back: int,
    source_file: str,
    criticality_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    sql = _sql_with_binds(check["sql"])
    start_date_str = (normalized_filter.get("start_date") or "")[:10]
    end_date_str = (normalized_filter.get("end_date") or "")[:10]
    start_at_str, end_at_str, _ = _build_time_bind_values(normalized_filter)
    
    base_binds = {
        "days_back": days_back,
        "DAYS_BACK": days_back,
        "start_date": start_date_str,
        "START_DATE": start_date_str,
        "end_date": end_date_str,
        "END_DATE": end_date_str,
        "start_at": start_at_str or "",
        "START_AT": start_at_str or "",
        "end_at": end_at_str or "",
        "END_AT": end_at_str or "",
    }
    executed_sql, sql_binds, schema_alias, temporal_alias, schema_pushed, time_pushed = _build_wrapped_sql(
        sql,
        normalized_filter,
        cleaned_schemas,
        base_binds,
    )

    rows: List[Dict[str, Any]] = []
    columns: List[str] = []
    temporal_column = temporal_alias
    criticality_key = _resolve_check_criticality(check["check_id"], criticality_overrides, default_severity=check.get("severitat"))
    criticality_label = _criticality_label(criticality_key)

    try:
        raw_rows, raw_columns = db_manager.execute_query(executed_sql, sql_binds)
        if raw_rows is None or raw_columns is None:
            raise RuntimeError(getattr(db_manager, "last_error", None) or "query_execution_failed")

        columns = list(raw_columns)
        rows = [dict(zip(raw_columns, row)) for row in raw_rows]
        if cleaned_schemas:
            rows = _filter_rows_by_schema(rows, cleaned_schemas)
        rows, detected_temporal = _filter_rows_by_range(rows, normalized_filter)
        temporal_column = detected_temporal or temporal_column
        if not temporal_column and rows:
            temporal_column = _pick_time_key(rows[0])

        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "check_id": check["check_id"],
            "title": check["title"],
            "severitat": criticality_label,
            "criticitat": criticality_label,
            "criticitat_key": criticality_key,
            "severitat_original": check["severitat"],
            "criteri": check["criteri"],
            "status": "ok",
            "row_count": len(rows),
            "columns": columns,
            "rows": rows,
            "schema_filtered": bool(cleaned_schemas),
            "temporal_column": temporal_column,
            "duration_ms": duration_ms,
            "executed_sql": executed_sql,
            "sql_binds": sql_binds,
            "rendered_sql": _render_sql_for_export(executed_sql, sql_binds),
            "schema_filter_pushed": schema_pushed,
            "time_filter_pushed": time_pushed,
            "source_file": source_file,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "check_id": check["check_id"],
            "title": check["title"],
            "severitat": criticality_label,
            "criticitat": criticality_label,
            "criticitat_key": criticality_key,
            "severitat_original": check["severitat"],
            "criteri": check["criteri"],
            "status": "error",
            "row_count": 0,
            "columns": columns,
            "rows": [],
            "schema_filtered": bool(cleaned_schemas),
            "temporal_column": temporal_column,
            "error": str(exc),
            "duration_ms": duration_ms,
            "executed_sql": executed_sql,
            "sql_binds": sql_binds,
            "rendered_sql": _render_sql_for_export(executed_sql, sql_binds),
            "schema_filter_pushed": schema_pushed,
            "time_filter_pushed": time_pushed,
            "source_file": source_file,
        }


def run_post_crq_audit(
    db_manager: Any,
    selected_checks: List[str],
    schemas: Optional[List[str]],
    time_filter: Optional[Dict[str, Any]],
    profile: str,
    markdown_path: Optional[str] = None,
    criticality_overrides: Optional[Dict[str, Any]] = None,
    ownership_db_path: Optional[str] = None,
    scheduler_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    path = markdown_path or resolve_post_crq_markdown_path()
    available_checks = parse_post_crq_checks(path)
    selected_ids = [check_id for check_id in selected_checks or [] if str(check_id).strip()]
    if not selected_ids:
        selected_ids = [item["check_id"] for item in available_checks]

    lookup = {item["check_id"]: item for item in available_checks}
    missing = [check_id for check_id in selected_ids if check_id not in lookup]
    if missing:
        raise ValueError(f"Checks no trobats: {', '.join(missing)}")

    execution_started_at = datetime.datetime.now()
    days_back, normalized_filter = _days_back_from_filter(time_filter, reference_dt=execution_started_at)
    cleaned_schemas = [schema.strip().upper() for schema in (schemas or []) if schema and schema.strip()]
    execution_context = build_execution_context(
        profile=profile,
        schemas=cleaned_schemas,
        selected_checks=selected_ids,
        time_filter=normalized_filter,
        source_file=os.path.basename(path),
        source_path=path,
        generated_at=execution_started_at.isoformat(timespec="seconds"),
    )
    execution_plan = build_execution_plan(
        execution_context,
        selected_checks=selected_ids,
        criticality_overrides=criticality_overrides,
    )
    scheduler_config = resolve_scheduler_config(scheduler_options)
    execution_plan["scheduler"] = {
        "max_concurrency_global": scheduler_config.max_concurrency_global,
        "max_concurrency_upper_bound": scheduler_config.max_concurrency_upper_bound,
        "max_heavy_concurrency": scheduler_config.max_heavy_concurrency,
        "max_medium_concurrency": scheduler_config.max_medium_concurrency,
        "max_light_concurrency": scheduler_config.max_light_concurrency,
        "max_retries": scheduler_config.max_retries,
        "enable_auto_throttle": scheduler_config.enable_auto_throttle,
    }

    executed_checks: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    source_file = os.path.basename(path)
    run_started = time.perf_counter()

    can_parallelize = hasattr(db_manager, "config") and isinstance(getattr(db_manager, "config", None), dict)
    scheduler_metrics = {
        "configured_max_concurrency": 1,
        "effective_max_concurrency": 1,
        "max_parallel_observed": 1,
        "max_parallel_by_category": {"heavy": 0, "medium": 0, "light": 0},
        "degraded_mode_triggered": False,
        "retries_used": 0,
        "queue_policy": "weighted_fifo",
        "auto_throttle_enabled": False,
        "category_distribution": {"heavy": 0, "medium": 0, "light": 0},
    }

    if can_parallelize and len(selected_ids) > 1 and scheduler_config.max_concurrency_global > 1:
        scheduled_tasks: List[SchedulerTask] = []
        for index, check_id in enumerate(selected_ids):
            check = lookup[check_id]
            category = classify_check_category(check_id, check.get("sql") or "")
            scheduled_tasks.append(
                SchedulerTask(
                    index=index,
                    check_id=check_id,
                    category=category,
                    timeout_seconds=timeout_for_category(scheduler_config, category),
                    payload={"check": check},
                )
            )

        def execute_task(task: SchedulerTask) -> Dict[str, Any]:
            worker_config = dict(db_manager.config)
            worker_config["CALL_TIMEOUT_MS"] = int(task.timeout_seconds * 1000)
            worker_dbm = OracleDBManager(worker_config)
            try:
                result = _run_single_post_crq_check(
                    task.payload["check"],
                    worker_dbm,
                    normalized_filter,
                    cleaned_schemas,
                    days_back,
                    source_file,
                    criticality_overrides,
                )
                result["query_category"] = task.category.value
                result["ai_enabled"] = task.payload["check"].get("ai_enabled", 0)
                return result
            finally:
                worker_dbm.close()

        scheduler_run = run_scheduled_tasks(scheduled_tasks, execute_task, scheduler_config)
        executed_checks = scheduler_run["results"]
        scheduler_metrics = scheduler_run["metrics"]
    else:
        for check_id in selected_ids:
            category = classify_check_category(check_id, lookup[check_id].get("sql") or "")
            item = _run_single_post_crq_check(
                lookup[check_id],
                db_manager,
                normalized_filter,
                cleaned_schemas,
                days_back,
                source_file,
                criticality_overrides,
            )
            item["query_category"] = category.value
            item["ai_enabled"] = lookup[check_id].get("ai_enabled", 0)
            item["scheduler"] = {
                "query_category": category.value,
                "queue_wait_ms": 0,
                "attempt": 1,
                "timeout_seconds": timeout_for_category(scheduler_config, category),
            }
            executed_checks.append(item)
        scheduler_metrics = {
            **scheduler_metrics,
            "configured_max_concurrency": 1,
            "effective_max_concurrency": 1,
            "max_parallel_observed": 1,
            "auto_throttle_enabled": scheduler_config.enable_auto_throttle,
            "category_distribution": {
                "heavy": sum(1 for item in executed_checks if item.get("query_category") == "heavy"),
                "medium": sum(1 for item in executed_checks if item.get("query_category") == "medium"),
                "light": sum(1 for item in executed_checks if item.get("query_category") == "light"),
            },
        }

    for item in executed_checks:
        is_check_with_ai = str(item.get("check_id") or "").upper() == "CHECK_12"
        if item.get("status") == "ok" and (item.get("rows") or []) and is_check_with_ai:
            ai_result = analyze_check11_results(item.get("rows") or [])
            item["ai_analysis"] = ai_result
            item["rows"] = merge_check11_ai_results(item.get("rows") or [], ai_result)
            for extra_column in [
                "ESTAT_ANALISI_IA",
                "CLASSIFICACIO_IA",
                "CONFIANCA_IA",
                "EXPLICACIO_IA",
                "RECOMANACIO_IA",
            ]:
                if extra_column not in item.get("columns", []):
                    item.setdefault("columns", []).append(extra_column)
        elif is_check_with_ai:
            item["ai_analysis"] = {
                "called": False,
                "status": "skipped_no_rows" if not (item.get("rows") or []) else "no disponible",
                "items": [],
                "summary": None,
            }

    ownership_path = ownership_db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    finding_envelopes = build_finding_envelopes(
        executed_checks,
        context=execution_context,
        ownership_db_path=ownership_path,
    )
    executed_checks = apply_ownership_to_check_rows(executed_checks, finding_envelopes)
    report_model = build_report_model(execution_context, execution_plan, executed_checks, finding_envelopes)
    quality_gate = report_model.get("quality_gate") or {}

    corrected_criticality_labels = {
        "CRITIC": "Crític",
        "MITJA": "Mitjà",
        "BAIX": "Baix",
    }
    for item in executed_checks:
        current_key = str(item.get("criticitat_key") or "BAIX").upper()
        item["criticitat"] = corrected_criticality_labels.get(current_key, "Baix")
        item["severitat"] = item["criticitat"]

    for item in executed_checks:
        if item.get("status") != "ok":
            errors.append({"check_id": item.get("check_id"), "message": item.get("error") or "query_execution_failed"})

    executed_checks.sort(
        key=lambda item: (
            _criticality_rank(item.get("criticitat_key")),
            int(item.get("row_count", 0)),
            int(item.get("duration_ms", 0)),
        ),
        reverse=True,
    )

    schema_last_modifications = _build_schema_last_modifications(executed_checks, normalized_filter)
    summary = _build_summary_v2(executed_checks, profile, normalized_filter)
    if report_model.get("criticality_blocks"):
        summary["criticality_sections"] = report_model["criticality_blocks"]
    summary["schema_last_modifications"] = schema_last_modifications
    summary["schemas_with_detected_changes"] = len(schema_last_modifications)
    summary["latest_change_at"] = summary.get("detected_time_range", {}).get("end_at") or (
        schema_last_modifications[0]["last_modified_at"] if schema_last_modifications else None
    )
    summary["check11_ai_summary"] = _extract_check12_ai_summary(executed_checks)
    summary["total_duration_ms"] = int((time.perf_counter() - run_started) * 1000)
    summary["parallel_workers"] = scheduler_metrics.get("configured_max_concurrency", 1)
    summary["scheduler"] = scheduler_metrics
    summary["quality_gate"] = quality_gate
    summary["slowest_checks"] = [
        {
            "check_id": item.get("check_id"),
            "title": item.get("title"),
            "duration_ms": item.get("duration_ms", 0),
            "query_category": item.get("query_category"),
        }
        for item in sorted(executed_checks, key=lambda current: int(current.get("duration_ms", 0)), reverse=True)[:5]
    ]
    queries_txt = _build_queries_txt(
        profile=profile,
        source_path=path,
        selected_ids=selected_ids,
        normalized_filter=normalized_filter,
        schemas=cleaned_schemas,
        executed_checks=executed_checks,
    )
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "audit_type": "post_crq",
        "report_options": {
            "include_annex": True,
        },
        "context": {
            "profile": profile,
            "schemas": cleaned_schemas,
            "time_filter": normalized_filter,
            "source_file": os.path.basename(path),
            "source_path": path,
            "generated_at": execution_started_at.isoformat(timespec="seconds"),
            "environment_message": _environment_message(profile),
            "scheduler": execution_plan["scheduler"],
        },
        "agent_runtime": report_model.get("agent_runtime"),
        "execution_plan": execution_plan,
        "summary": summary,
        "executed_checks": [
            {
                "check_id": item["check_id"],
                "title": item["title"],
                "severitat": item["severitat"],
                "criticitat": item["criticitat"],
                "criticitat_key": item["criticitat_key"],
                "severitat_original": item["severitat_original"],
                "criteri": item["criteri"],
                "status": item["status"],
                "row_count": item["row_count"],
                "schema_filtered": item.get("schema_filtered", False),
                "temporal_column": item.get("temporal_column"),
                "error": item.get("error"),
                "duration_ms": item.get("duration_ms", 0),
                "query_category": item.get("query_category"),
                "schema_filter_pushed": item.get("schema_filter_pushed", False),
                "time_filter_pushed": item.get("time_filter_pushed", False),
                "ai_analysis": item.get("ai_analysis"),
                "scheduler": item.get("scheduler"),
                "quality_gate": quality_gate.get("status"),
            }
            for item in executed_checks
        ],
        "schema_last_modifications": schema_last_modifications,
        "finding_envelopes": finding_envelopes,
        "report_model": report_model,
        "results_by_check": executed_checks,
        "query_export": {
            "filename": f"consultes_post_crq_{profile}_{timestamp}.txt",
            "content": queries_txt,
            "source_file": os.path.basename(path),
            "source_path": path,
        },
        "criticality_overrides": {
            check_id: corrected_criticality_labels.get(
                _resolve_check_criticality(check_id, criticality_overrides, default_severity=lookup.get(check_id, {}).get("severitat")), "Baix"
            )
            for check_id in selected_ids
        },
        "errors": errors,
    }


def is_post_crq_audit_data(data: Any) -> bool:
    return isinstance(data, dict) and data.get("audit_type") == "post_crq"


def _should_include_annex(report: Dict[str, Any]) -> bool:
    options = report.get("report_options") or {}
    if "include_annex" not in options:
        return True
    return bool(options.get("include_annex"))


def _build_annex_entries(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    executed_checks = _sort_check_dicts(report.get("executed_checks") or [])
    entries: List[Dict[str, Any]] = []
    for item in executed_checks:
        check_id = str(item.get("check_id") or "").strip()
        if not check_id:
            continue
        guidance = ANNEX_CHECK_GUIDANCE.get(check_id, {})
        entries.append(
            {
                "check_id": check_id,
                "title": _fix_encoding(_display_title(item.get("title") or check_id)),
                "severitat": _fix_encoding(item.get("severitat") or "N/A"),
                "objectiu": _fix_encoding(guidance.get("objectiu", "No s'ha definit una interpretació funcional específica per a aquest check.")),
                "impacte": _fix_encoding(guidance.get("impacte", "Sense impacte funcional documentat.")),
                "possible_millora": _fix_encoding(guidance.get("possible_millora", "Sense proposta específica de millora.")),
                "limitacions": _fix_encoding(guidance.get("limitacions", "Sense limitacions documentades.")),
                "remediacio": _fix_encoding(guidance.get("remediacio", "Revisar el check amb criteri DBA i context funcional.")),
            }
        )
    return entries


def _safe_html(value: Any) -> str:
    return html.escape(_normalize_text(value))


_PDF_FONT_STATE = {"registered": False}


def _register_post_crq_pdf_fonts() -> Tuple[str, str]:
    if _PDF_FONT_STATE["registered"]:
        return "OracleAudit", "OracleAudit-Bold"

    root = Path(_project_root())
    regular_candidates = [
        root / "resources" / "fonts" / "arial.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    bold_candidates = [
        root / "resources" / "fonts" / "arialbd.ttf",
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]

    regular_path = next((path for path in regular_candidates if path.exists()), None)
    bold_path = next((path for path in bold_candidates if path.exists()), None)
    if not regular_path or not bold_path:
        return "Helvetica", "Helvetica-Bold"

    pdfmetrics.registerFont(TTFont("OracleAudit", str(regular_path)))
    pdfmetrics.registerFont(TTFont("OracleAudit-Bold", str(bold_path)))
    pdfmetrics.registerFontFamily("OracleAudit", normal="OracleAudit", bold="OracleAudit-Bold", italic="OracleAudit", boldItalic="OracleAudit-Bold")
    _PDF_FONT_STATE["registered"] = True
    return "OracleAudit", "OracleAudit-Bold"


def _pdf_header_wrap(value: Any) -> str:
    # Usem _safe_xml però sense escapar el <br/> que posarem nosaltres
    text = _normalize_text(value) or "-"
    if len(text) > 20 and " " in text:
        parts = text.split(" ")
        lines: List[str] = []
        current = ""
        for part in parts:
            candidate = f"{current} {part}".strip()
            if current and len(candidate) > 18:
                lines.append(_safe_xml(current))
                current = part
            else:
                current = candidate
        if current:
            lines.append(_safe_xml(current))
        return "<br/>".join(lines)
    return _safe_xml(text)


def _pdf_cell_wrap(value: Any, column_name: Optional[str] = None) -> str:
    text = _normalize_text(value) or "-"
    normalized = _normalize_key(column_name or "")
    if normalized.startswith("dada_t") or normalized.startswith("observacio"):
        return _safe_xml(text)
    protected = {
        "taula",
        "table",
        "objecte",
        "sequencia",
        "sequence",
        "constraint_fk",
        "nom_constraint",
        "num_files",
        "data_modificacio_objecte",
        "data_modificacio_taula",
        "darrera_estadistica",
    }
    if normalized in protected and len(text) <= 34:
        return _safe_xml(text)
    if len(text) <= 22:
        return _safe_xml(text)
    if "_" in text:
        groups = text.split("_")
        lines: List[str] = []
        current = []
        current_len = 0
        for group in groups:
            projected = current_len + len(group) + (1 if current else 0)
            threshold = 22 if normalized in protected else 16
            if current and projected > threshold:
                lines.append("_".join(current))
                current = [group]
                current_len = len(group)
            else:
                current.append(group)
                current_len = projected
        if current:
            lines.append("_".join(current))
        return "<br/>".join(_safe_xml(line) for line in lines)
    chunk_size = 22 if normalized in protected else 18
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    return "<br/>".join(_safe_xml(c) for c in chunks)


def _leading_upper(value: str) -> str:
    text = str(value or "")
    for index, character in enumerate(text):
        if character.isalpha():
            return text[:index] + character.upper() + text[index + 1 :]
    return text


def _display_column_header(value: Any) -> str:
    text = _normalize_text(value) or "-"
    normalized = _normalize_key(text)
    labels = {
        "esquema": "ESQUEMA",
        "schema": "ESQUEMA",
        "taula": "taula",
        "table": "taula",
        "sequencia": "seqüència",
        "cache_actual": "cache actual",
        "increment_by_value": "increment",
        "cicle": "cicle",
        "descripcio": "descripció",
        "num_files": "Núm. files",
        "darrera_estadistica": "Darrera estadística",
        "data_modificacio_objecte": "Data modificació objecte",
        "data_modificacio_taula": "Data modificació taula",
        "data_modificacio_constraint": "Data modificació constraint",
        "data_modificacio_mes_recent": "Data modificació més recent",
        "constraint_fk": "Constraint FK",
        "constraint_name": "Nom constraint",
        "columnes_fk": "Columnes FK",
        "taula_pare": "Taula pare",
        "index_suport": "Índex suport",
        "index_1": "Índex 1",
        "index_2": "Índex 2",
        "columna_lider_comuna": "Columna líder comuna",
        "tipus_1": "Tipus 1",
        "tipus_2": "Tipus 2",
        "tipus": "Tipus",
        "tipus_constraint": "Tipus constraint",
        "tipus_dada": "Tipus dada",
        "columna": "columna",
        "codi": "codi",
        "linia": "línia",
        "posicio": "posició",
        "nullable": "nullable",
        "validada": "validada",
        "check": "CHECK",
        "severitat": "sev.",
        "estat": "estat",
        "files": "files",
        "temps_ms": "temps (ms)",
        "objecte": "objecte",
        "objecte_plsql": "objecte PL/SQL",
        "sinonim": "sinònim",
        "objecte_desti": "Objecte destí",
        "propietari_desti": "Propietari destí",
        "linies_sospitoses_en_loop": "Línies sospitoses en loop",
        "total_linies_codi": "Total línies codi",
        "severitat_sql": "Severitat SQL",
        "explicacio_ia": "Explicació IA",
        "recomanacio_ia": "Recomanació IA",
        "estat_analisi_ia": "Estat anàlisi IA",
    }
    if normalized in labels:
        return labels[normalized]
    if normalized == "check":
        return "CHECK"
    if normalized in {"esquema", "schema"}:
        return "ESQUEMA"
    return text.lower()


def _display_check_title(value: Any) -> str:
    text = _normalize_text(value)
    normalized = _normalize_key(text)
    overrides = {
        "objectes_recents_invalid": "objectes recents invàlids",
        "objectes_recents_inva_lids": "objectes recents invàlids",
        "when_others_then_null_en_codi_recent": "ús de WHEN OTHERS THEN NULL en codi recent",
        "us_de_when_others_then_null_en_codi_recent": "ús de WHEN OTHERS THEN NULL en codi recent",
        "sequencies_sense_cache_recomanacio_per_heuristica": "seqüències sense cache - recomanació per heurística",
    }
    rendered = overrides.get(normalized, text.lower() if text else "-")
    rendered = re.sub(r"\bprimary key\b", "clau primària", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\bforeign keys\b", "claus foranes", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\bforeign key\b", "clau forana", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\bnumber\b", "NUMBER", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\bapex\b", "APEX", rendered, flags=re.IGNORECASE)
    return rendered

def _display_title(value: Any) -> str:
    return _display_check_title(value)


def _display_time_mode(time_filter: Dict[str, Any]) -> str:
    mode = (time_filter.get("mode") or "preset").strip().lower()
    return "rang de dates" if mode == "range" else "mode predefinit"


def _display_preset_label(value: Any) -> str:
    mapping = {
        "daily": "diari",
        "weekly": "setmanal",
        "monthly": "mensual",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "-"))


def _display_period_label(time_filter: Dict[str, Any]) -> str:
    mode = (time_filter.get("mode") or "preset").strip().lower()
    if mode == "range":
        return _format_display_time_range(
            start_raw=time_filter.get("range_start_at") or time_filter.get("start_at") or time_filter.get("start_date"),
            end_raw=time_filter.get("range_end_at") or time_filter.get("end_at") or time_filter.get("end_date"),
        )
    return _display_preset_label(time_filter.get("preset"))


def _display_period_window(time_filter: Dict[str, Any]) -> str:
    mode = (time_filter.get("mode") or "preset").strip().lower()

    if mode == "range":
        return _format_display_time_range(
            start_raw=time_filter.get("range_start_at") or time_filter.get("start_at") or time_filter.get("start_date"),
            end_raw=time_filter.get("range_end_at") or time_filter.get("end_at") or time_filter.get("end_date"),
        )

    days_back = max(1, int(time_filter.get("days_back") or 1))
    anchor_raw = str(time_filter.get("resolved_at") or "").strip()
    anchor_dt = _parse_iso_dt(anchor_raw)
    if anchor_dt is None:
        anchor_date_raw = str(time_filter.get("resolved_on") or time_filter.get("end_date") or "").strip()
        if not anchor_date_raw:
            return "-"
        anchor_dt = _parse_iso_dt(anchor_date_raw)
    if not anchor_dt:
        return "-"
    end_dt = anchor_dt
    start_dt = end_dt - datetime.timedelta(days=days_back)
    return f"{_format_display_datetime(start_dt)} - {_format_display_datetime(end_dt)}"


def _resolved_criteria_text(criteri: Any, days_back: Any) -> str:
    text = _normalize_text(criteri) or "-"
    try:
        days = int(days_back or 0)
    except (TypeError, ValueError):
        days = 0
    day_label = "1 dia" if days == 1 else f"{days} dies"
    text = re.sub(r"\bN dies\b", day_label, text, flags=re.IGNORECASE)
    return text


def _severity_badge_color(severity: Any) -> rl_colors.Color:
    normalized = _criticality_key(severity)
    if normalized == "CRITIC":
        return rl_colors.HexColor("#b91c1c")
    if normalized == "MITJA":
        return rl_colors.HexColor("#f97316")
    if normalized == "BAIX":
        return rl_colors.HexColor("#16a34a")
    return rl_colors.HexColor("#64748b")


def _severity_badge_text(severity: Any) -> str:
    return _criticality_label(severity)


def _severity_badge_hex(severity: Any) -> str:
    normalized = _criticality_key(severity)
    mapping = {
        "CRITIC": "#b91c1c",
        "MITJA": "#f97316",
        "BAIX": "#16a34a",
    }
    return mapping.get(normalized, "#64748b")


def _post_crq_pdf_column_weight(column_name: str) -> float:
    normalized = _normalize_key(column_name)
    if normalized in {"esquema", "schema"}:
        return 1.65
    if normalized in {"taula", "table", "taula_pare", "sequencia", "sequence", "objecte", "sinonim"}:
        return 2.25
    if normalized in {"index_1", "index_2", "constraint_fk", "nom_constraint", "objecte_desti", "propietari_desti"}:
        return 1.55
    if normalized in {"columnes_fk", "columna_lider_comuna", "descripcio", "codi", "observacio", "explicacio_ia", "recomanacio_ia", "linies_detall"}:
        return 2.0
    if normalized in {"tipus_1", "tipus_2", "tipus", "tipus_constraint", "tipus_objecte"}:
        return 0.78
    if normalized in {"severitat", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle", "severitat_sql", "confianca_ia", "estat_analisi_ia"}:
        return 0.44
    if any(token in normalized for token in ("darrera_estadistica", "data_modificacio", "data_invalidacio", "data_creacio", "date", "data")):
        return 0.72
    if normalized in {"validada", "estat"}:
        return 0.58
    return 1.0


def _post_crq_pdf_min_ratio(column_name: str) -> float:
    normalized = _normalize_key(column_name)
    if normalized in {"check", "esquema", "schema"}:
        return 0.09
    if normalized in {"taula", "table", "sequencia", "sequence", "objecte", "sinonim", "constraint_fk"}:
        return 0.12
    if normalized in {"columnes_fk", "columna_lider_comuna", "descripcio", "codi", "observacio", "explicacio_ia", "recomanacio_ia", "linies_detall"}:
        return 0.14
    if normalized in {"severitat", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle", "severitat_sql", "confianca_ia", "estat_analisi_ia"}:
        return 0.05
    if any(token in normalized for token in ("data", "date", "estadistica")):
        return 0.08
    return 0.07


def _post_crq_pdf_max_ratio(column_name: str) -> float:
    normalized = _normalize_key(column_name)
    if normalized in {"columnes_fk", "columna_lider_comuna", "descripcio", "codi", "observacio", "explicacio_ia", "recomanacio_ia", "linies_detall"}:
        return 0.28
    if normalized in {"taula", "table", "sequencia", "sequence", "objecte", "sinonim", "constraint_fk"}:
        return 0.23
    if normalized in {"esquema", "schema"}:
        return 0.17
    if normalized in {"severitat", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle", "severitat_sql", "confianca_ia", "estat_analisi_ia"}:
        return 0.09
    if any(token in normalized for token in ("data", "date", "estadistica")):
        return 0.13
    return 0.19


def _column_text_score(column: str, rows: List[Dict[str, Any]]) -> float:
    normalized = _normalize_key(column)
    header = _display_column_header(column)
    score = max(10.0, len(header) * 1.15)
    if not rows:
        return score

    sample_rows = rows[: min(len(rows), 45)]
    lengths: List[int] = []
    for row in sample_rows:
        text = _normalize_text(row.get(column) or "-")
        lengths.append(max(1, len(text)))

    lengths.sort(reverse=True)
    top_lengths = lengths[:6] if lengths else [10]
    avg_top = sum(top_lengths) / len(top_lengths)
    overall_avg = sum(lengths) / len(lengths) if lengths else avg_top
    multiplier = 1.0
    if normalized in {"columnes_fk", "columna_lider_comuna", "descripcio", "codi"}:
        multiplier = 1.55
    elif normalized in {"taula", "table", "sequencia", "sequence", "objecte", "sinonim", "constraint_fk"}:
        multiplier = 1.35
    elif normalized in {"esquema", "schema"}:
        multiplier = 1.18
    elif normalized in {"severitat", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle"}:
        multiplier = 0.72
    elif any(token in normalized for token in ("data", "date", "estadistica")):
        multiplier = 0.88
    score = max(score, (avg_top * 0.72 + overall_avg * 0.28) * multiplier)
    return score


def _fit_column_widths(columns: List[str], rows: List[Dict[str, Any]], total_width: float) -> List[float]:
    scores = [_column_text_score(column, rows) for column in columns]
    total_score = sum(scores) or 1.0
    widths = [(score / total_score) * total_width for score in scores]

    min_widths = [total_width * _post_crq_pdf_min_ratio(column) for column in columns]
    max_widths = [total_width * _post_crq_pdf_max_ratio(column) for column in columns]

    for index in range(len(widths)):
        widths[index] = max(min_widths[index], min(widths[index], max_widths[index]))

    current_total = sum(widths) or 1.0
    scale = total_width / current_total
    widths = [width * scale for width in widths]

    for _ in range(6):
        adjusted = False
        spare = 0.0
        needy_indexes: List[int] = []
        for index, width in enumerate(widths):
            min_width = min_widths[index]
            max_width = max_widths[index]
            if width < min_width:
                spare -= min_width - width
                widths[index] = min_width
                adjusted = True
            elif width > max_width:
                spare += width - max_width
                widths[index] = max_width
                adjusted = True
            elif width < max_width:
                needy_indexes.append(index)
        if not adjusted:
            break
        if spare > 0 and needy_indexes:
            total_need = sum(max_widths[i] - widths[i] for i in needy_indexes) or 1.0
            for index in needy_indexes:
                growth = spare * ((max_widths[index] - widths[index]) / total_need)
                widths[index] = min(max_widths[index], widths[index] + growth)

    final_total = sum(widths) or 1.0
    return [(width / final_total) * total_width for width in widths]


def _detail_requires_landscape(columns: List[str], rows: List[Dict[str, Any]]) -> bool:
    normalized = [_normalize_key(column) for column in columns]
    header_score = sum(len(_display_column_header(column)) for column in columns)
    row_score = 0
    sampled_rows = rows[: min(len(rows), 20)]
    for row in sampled_rows:
        row_score = max(
            row_score,
            sum(min(len(_normalize_text(row.get(column) or "-")), 28) for column in columns),
        )

    if len(columns) >= 8:
        return True
    if len(columns) >= 7 and header_score >= 68:
        return True
    if any(key in normalized for key in {"columnes_fk", "columna_lider_comuna", "codi", "descripcio"}):
        return True
    if len(columns) >= 6 and row_score >= 95:
        return True
    return False


def _post_crq_pdf_column_widths(columns: List[str], rows: List[Dict[str, Any]], total_width: float, table_kind: str = "detail_table") -> List[float]:
    if not columns:
        return []
    normalized = [_normalize_key(column) for column in columns]
    fitted = _fit_column_widths(columns, rows, total_width)

    if (
        table_kind == "object_table"
        and len(normalized) == 3
        and normalized[0] == "objecte"
        and normalized[1] == "tipus"
        and normalized[2].startswith("dada_t")
    ):
        weights = [2.4, 1.2, 2.4]
        total = sum(weights) or 1.0
        return [(weight / total) * total_width for weight in weights]

    if normalized == [
        "esquema",
        "taula",
        "num_files",
        "darrera_estadistica",
        "data_modificacio_objecte",
        "severitat",
    ]:
        weights = [1.45, 3.75, 0.56, 0.72, 0.84, 0.38]
    elif normalized == [
        "esquema",
        "sequencia",
        "cache_actual",
        "increment_by_value",
        "cicle",
        "descripcio",
        "severitat",
        "data_modificacio_objecte",
    ]:
        weights = [1.6, 2.95, 0.36, 0.46, 0.34, 1.45, 0.34, 0.62]
    elif normalized == [
        "esquema",
        "taula",
        "index_1",
        "index_2",
        "columna_lider_comuna",
        "tipus_1",
        "tipus_2",
        "data_modificacio_mes_recent",
        "severitat",
    ]:
        weights = [1.15, 1.7, 1.85, 1.85, 1.95, 0.5, 0.5, 0.72, 0.32]
    elif normalized == [
        "esquema",
        "objecte",
        "tipus",
        "linia",
        "codi",
        "data_modificacio_objecte",
        "severitat",
    ]:
        weights = [1.1, 1.65, 0.58, 0.32, 2.85, 0.72, 0.3]
    elif normalized == [
        "esquema",
        "taula",
        "constraint_fk",
        "columnes_fk",
        "index_suport",
        "data_modificacio_constraint",
        "severitat",
    ]:
        weights = [1.15, 1.65, 1.35, 2.65, 1.35, 0.78, 0.32]
    elif normalized == [
        "esquema",
        "taula",
        "constraint_name",
        "tipus_constraint",
        "validada",
        "data_modificacio_objecte",
        "severitat",
    ]:
        weights = [1.1, 1.95, 1.6, 0.75, 0.55, 0.82, 0.32]
    elif normalized == [
        "esquema",
        "taula",
        "columna",
        "tipus_dada",
        "nullable",
        "posicio",
        "severitat",
    ]:
        weights = [1.15, 1.85, 1.75, 1.45, 0.42, 0.42, 0.32]
    elif normalized == [
        "esquema",
        "taula",
        "columna",
        "tipus_dada",
        "precision",
        "escala",
        "severitat",
    ]:
        weights = [1.15, 1.95, 1.9, 1.45, 0.38, 0.38, 0.32]
    else:
        return fitted

    total = sum(weights) or 1.0
    return [(weight / total) * total_width for weight in weights]


def _post_crq_pdf_header_footer(
    canvas,
    doc,
    profile: str,
    generated_at: str,
    footer_text: str,
    logo_path: Optional[Path],
    show_header: bool = True,
) -> None:
    canvas.saveState()
    width, height = doc.pagesize
    is_landscape = width > height
    page_margin = 0.65 * cm if is_landscape else doc.leftMargin
    left_margin = page_margin
    right_edge = width - page_margin
    top_y = height - 1.0 * cm
    footer_y = 0.8 * cm

    if show_header:
        if logo_path and logo_path.exists():
            canvas.drawImage(
                str(logo_path),
                left_margin,
                top_y - 0.7 * cm,
                width=5.2 * cm,
                height=0.9 * cm,
                preserveAspectRatio=True,
                mask="auto",
            )

        canvas.setFont("OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 9)
        canvas.setFillColor(rl_colors.HexColor("#1e3a8a"))
        canvas.drawRightString(right_edge, top_y, f"Auditoria Oracle {_fix_encoding(profile or '-')}")
        canvas.setFont("OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 8)
        canvas.setFillColor(rl_colors.HexColor("#6b7280"))
        canvas.drawRightString(right_edge, top_y - 0.35 * cm, "Departament d'Educació i Formació Professional")
        canvas.drawRightString(right_edge, top_y - 0.68 * cm, f"Perfil: {profile} | {generated_at}")

    canvas.setStrokeColor(rl_colors.HexColor("#d1d5db"))
    canvas.line(left_margin, footer_y + 0.22 * cm, right_edge, footer_y + 0.22 * cm)
    canvas.setFont("OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 7.5)
    canvas.drawRightString(right_edge, footer_y, f"Pàgina {canvas.getPageNumber()} | {footer_text}")
    canvas.restoreState()


def _post_crq_pdf_cover(
    canvas,
    doc,
    profile: str,
    generated_at: str,
    cover_path: Optional[Path],
    context: Dict[str, Any],
    summary: Dict[str, Any],
    time_filter: Dict[str, Any],
) -> None:
    canvas.saveState()
    width, height = doc.pagesize
    image_bottom = 4.9 * cm
    if cover_path and cover_path.exists():
        canvas.drawImage(
            str(cover_path),
            0,
            image_bottom,
            width=width,
            height=height - image_bottom,
            preserveAspectRatio=False,
            mask="auto",
        )

    panel_x = 1.2 * cm
    panel_y = 0.9 * cm
    panel_width = width - (2.4 * cm)
    panel_height = 3.25 * cm

    canvas.setFillColor(rl_colors.HexColor("#0b1f3a"))
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 10, stroke=0, fill=1)
    canvas.setStrokeColor(rl_colors.HexColor("#58e0ff"))
    canvas.setLineWidth(1.0)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 10, stroke=1, fill=0)
    canvas.line(panel_x + 0.55 * cm, panel_y + panel_height - 0.72 * cm, panel_x + panel_width - 0.55 * cm, panel_y + panel_height - 0.72 * cm)

    canvas.setFillColor(rl_colors.white)
    canvas.setFont("OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold", 12)
    canvas.drawString(panel_x + 0.6 * cm, panel_y + panel_height - 0.48 * cm, "Informe de validació post-CRQ")

    canvas.setFont("OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 9.4)
    left_x = panel_x + 0.6 * cm
    right_x = panel_x + 9.1 * cm
    base_y = panel_y + panel_height - 1.4 * cm
    line_gap = 0.52 * cm

    canvas.drawString(left_x, base_y, f"Perfil: {profile}")
    canvas.drawString(left_x, base_y - line_gap, f"Generat: {generated_at}")
    canvas.drawString(left_x, base_y - (2 * line_gap), f"Mode temporal: {_display_time_mode(time_filter)}")

    canvas.drawString(right_x, base_y, f"Període aplicat: {_display_period_label(time_filter)}")
    canvas.drawString(right_x, base_y - line_gap, f"Finestra consultada: {_display_period_window(time_filter)}")
    canvas.drawString(right_x, base_y - (2 * line_gap), f"Fitxer de checks: {str(context.get('source_file') or '-')}")
    canvas.restoreState()


def _build_post_crq_paragraph_styles() -> Dict[str, ParagraphStyle]:
    font_name, bold_name = _register_post_crq_pdf_fonts()
    styles = getSampleStyleSheet()
    shared = dict(splitLongWords=1, allowWidows=1, allowOrphans=1, wordWrap="CJK")
    return {
        "title": ParagraphStyle(
            "PostCrqTitle",
            parent=styles["Title"],
            fontName=bold_name,
            fontSize=22,
            leading=26,
            textColor=PDF_BRAND_BLUE,
            spaceAfter=12,
            **shared,
        ),
        "kicker": ParagraphStyle(
            "PostCrqKicker",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=8.2,
            leading=10,
            textColor=PDF_BRAND_BLUE,
            spaceAfter=4,
            **shared,
        ),
        "cover_title": ParagraphStyle(
            "PostCrqCoverTitle",
            parent=styles["Title"],
            fontName=bold_name,
            fontSize=24,
            leading=28,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=10,
            **shared,
        ),
        "cover_meta": ParagraphStyle(
            "PostCrqCoverMeta",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10.2,
            leading=13,
            textColor=PDF_MUTED_TEXT,
            **shared,
        ),
        "body": ParagraphStyle(
            "PostCrqBody",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10.0,
            leading=13.8,
            alignment=TA_JUSTIFY,
            textColor=rl_colors.HexColor("#1f2937"),
            spaceAfter=7,
            **shared,
        ),
        "lead": ParagraphStyle(
            "PostCrqLead",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10.8,
            leading=14.2,
            alignment=TA_JUSTIFY,
            textColor=PDF_MUTED_TEXT,
            spaceAfter=8,
            **shared,
        ),
        "body_small": ParagraphStyle(
            "PostCrqBodySmall",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=8.8,
            leading=11.6,
            alignment=TA_JUSTIFY,
            textColor=PDF_MUTED_TEXT,
            spaceAfter=4,
            **shared,
        ),
        "section_heading": ParagraphStyle(
            "PostCrqSectionHeading",
            parent=styles["Heading2"],
            fontName=bold_name,
            fontSize=15.2,
            leading=18.6,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=9,
            spaceBefore=13,
            **shared,
        ),
        "index_heading": ParagraphStyle(
            "PostCrqIndexHeading",
            parent=styles["Heading2"],
            fontName=bold_name,
            fontSize=15.2,
            leading=18.6,
            alignment=TA_CENTER,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=9,
            spaceBefore=13,
            **shared,
        ),
        "heading": ParagraphStyle(
            "PostCrqHeading",
            parent=styles["Heading2"],
            fontName=bold_name,
            fontSize=15.2,
            leading=18.6,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=9,
            spaceBefore=13,
            **shared,
        ),
        "subsection_heading": ParagraphStyle(
            "PostCrqSubsectionHeading",
            parent=styles["Heading3"],
            fontName=bold_name,
            fontSize=11.2,
            leading=13.8,
            textColor=PDF_BRAND_BLUE,
            spaceAfter=5,
            spaceBefore=8,
            **shared,
        ),
        "check_heading": ParagraphStyle(
            "PostCrqCheckHeading",
            parent=styles["Heading2"],
            fontName=bold_name,
            fontSize=13.1,
            leading=16.4,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=7,
            **shared,
        ),
        "severity_heading": ParagraphStyle(
            "PostCrqSeverityHeading",
            parent=styles["Heading3"],
            fontName=bold_name,
            fontSize=14.0,
            leading=17.1,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=6,
            spaceBefore=8,
            **shared,
        ),
        "incident_heading": ParagraphStyle(
            "PostCrqIncidentHeading",
            parent=styles["Heading3"],
            fontName=bold_name,
            fontSize=10.9,
            leading=13.4,
            textColor=PDF_BRAND_BLUE,
            spaceAfter=5,
            spaceBefore=2,
            **shared,
        ),
        "meta": ParagraphStyle(
            "PostCrqMeta",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=9.3,
            leading=12.2,
            alignment=TA_JUSTIFY,
            textColor=PDF_MUTED_TEXT,
            spaceAfter=6,
            **shared,
        ),
        "toc_title": ParagraphStyle(
            "PostCrqTocTitle",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=10.8,
            leading=13.2,
            textColor=PDF_BRAND_NAVY,
            **shared,
        ),
        "toc_number": ParagraphStyle(
            "PostCrqTocNumber",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=9.2,
            leading=11.6,
            alignment=TA_CENTER,
            textColor=PDF_BRAND_BLUE,
            **shared,
        ),
        "toc": ParagraphStyle(
            "PostCrqToc",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=9.9,
            leading=12.9,
            textColor=PDF_BRAND_BLUE,
            leftIndent=2,
            **shared,
        ),
        "toc_lot": ParagraphStyle(
            "PostCrqTocLot",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=8.9,
            leading=10.9,
            textColor=PDF_BRAND_NAVY,
            leftIndent=10,
            **shared,
        ),
        "card_title": ParagraphStyle(
            "PostCrqCardTitle",
            parent=styles["Heading2"],
            fontName=bold_name,
            fontSize=12.8,
            leading=16.0,
            textColor=PDF_BRAND_NAVY,
            spaceAfter=7,
            **shared,
        ),
        "toc_sub": ParagraphStyle(
            "PostCrqTocSub",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=8.2,
            leading=10.2,
            textColor=PDF_BRAND_BLUE,
            leftIndent=18,
            **shared,
        ),
        "toc_micro": ParagraphStyle(
            "PostCrqTocMicro",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=7.6,
            leading=9.2,
            textColor=PDF_MUTED_TEXT,
            leftIndent=26,
            **shared,
        ),
        "toc_detail": ParagraphStyle(
            "PostCrqTocDetail",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=7.1,
            leading=8.3,
            textColor=PDF_MUTED_TEXT,
            leftIndent=34,
            **shared,
        ),
        "check_index": ParagraphStyle(
            "PostCrqCheckIndex",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=9.2,
            leading=12.9,
            alignment=TA_JUSTIFY,
            textColor=rl_colors.HexColor("#334155"),
            **shared,
        ),
        "callout_title": ParagraphStyle(
            "PostCrqCalloutTitle",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=10.4,
            leading=12.8,
            textColor=PDF_BRAND_NAVY,
            **shared,
        ),
        "callout_body": ParagraphStyle(
            "PostCrqCalloutBody",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=9.8,
            leading=12.8,
            alignment=TA_JUSTIFY,
            textColor=rl_colors.HexColor("#1f2937"),
            **shared,
        ),
        "annex_body": ParagraphStyle(
            "PostCrqAnnexBody",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10.2,
            leading=14.0,
            alignment=TA_JUSTIFY,
            textColor=rl_colors.HexColor("#1f2937"),
            spaceAfter=9,
            splitLongWords=0,
            wordWrap=None,
        ),
        "lot_badge": ParagraphStyle(
            "PostCrqLotBadge",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=12.0,
            leading=14.4,
            textColor=PDF_BRAND_NAVY,
            **shared,
        ),
        "severity_line": ParagraphStyle(
            "PostCrqSeverityLine",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=10.2,
            leading=12.4,
            alignment=TA_LEFT,
            textColor=PDF_BRAND_BLUE,
            **shared,
        ),
        "table_header": ParagraphStyle(
            "PostCrqTableHeader",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=6.5,
            leading=7.4,
            alignment=TA_CENTER,
            textColor=rl_colors.white,
        ),
        "table_header_large": ParagraphStyle(
            "PostCrqTableHeaderLarge",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=7.4,
            leading=8.5,
            alignment=TA_CENTER,
            textColor=rl_colors.white,
        ),
        "table_header_tight": ParagraphStyle(
            "PostCrqTableHeaderTight",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=6.1,
            leading=6.9,
            alignment=TA_CENTER,
            textColor=rl_colors.white,
        ),
        "table_cell": ParagraphStyle(
            "PostCrqTableCell",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=6.15,
            leading=7.2,
            textColor=rl_colors.HexColor("#1f2937"),
            wordWrap="LTR",
        ),
        "table_cell_large": ParagraphStyle(
            "PostCrqTableCellLarge",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=7.1,
            leading=8.2,
            textColor=rl_colors.HexColor("#1f2937"),
            wordWrap="LTR",
        ),
        "table_cell_tight": ParagraphStyle(
            "PostCrqTableCellTight",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=5.9,
            leading=6.8,
            textColor=rl_colors.HexColor("#1f2937"),
            wordWrap="LTR",
        ),
        "table_cell_center": ParagraphStyle(
            "PostCrqTableCellCenter",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=6.05,
            leading=7.0,
            textColor=rl_colors.HexColor("#1f2937"),
            alignment=TA_CENTER,
            wordWrap="LTR",
        ),
        "table_cell_center_large": ParagraphStyle(
            "PostCrqTableCellCenterLarge",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=7.0,
            leading=8.0,
            textColor=rl_colors.HexColor("#1f2937"),
            alignment=TA_CENTER,
            wordWrap="LTR",
        ),
        "table_cell_center_tight": ParagraphStyle(
            "PostCrqTableCellCenterTight",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=5.85,
            leading=6.7,
            textColor=rl_colors.HexColor("#1f2937"),
            alignment=TA_CENTER,
            wordWrap="LTR",
        ),
        "badge": ParagraphStyle(
            "PostCrqBadge",
            parent=styles["Normal"],
            fontName=bold_name,
            fontSize=5.8,
            leading=6.4,
            alignment=TA_CENTER,
            textColor=rl_colors.white,
        ),
    }


def _build_post_crq_table(
    columns: List[str],
    rows: List[Dict[str, Any]],
    total_width: float,
    styles: Dict[str, ParagraphStyle],
    table_kind: str = "detail_table",
) -> Table:
    if not columns:
        columns = ["Resultat"]
    normalized_columns = [_normalize_key(column) for column in columns]
    wide_table = len(columns) >= 8 or sum(len(column) for column in columns) >= 70
    if table_kind in {"summary_table", "object_table"}:
        header_style = styles.get("table_header_large", styles["table_header"])
        cell_style = styles.get("table_cell_large", styles["table_cell"])
        center_style = styles.get("table_cell_center_large", styles["table_cell_center"])
    else:
        header_style = styles["table_header_tight"] if wide_table else styles["table_header"]
        cell_style = styles["table_cell_tight"] if wide_table else styles["table_cell"]
        center_style = styles["table_cell_center_tight"] if wide_table else styles["table_cell_center"]
    table_rows: List[List[Any]] = [
        [Paragraph(_pdf_header_wrap(_leading_upper(_display_column_header(column))), header_style) for column in columns]
    ]
    center_columns = {
        column
        for column in columns
        if _normalize_key(column) in {"severitat", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle"}
        or any(token in _normalize_key(column) for token in ("data", "date"))
    }

    if not rows:
        table_rows.append([Paragraph("Sense troballes per aquest check.", styles["table_cell"])] + [""] * (len(columns) - 1))
    else:
        for row in rows:
            rendered_row = []
            for column in columns:
                style = center_style if column in center_columns else cell_style
                rendered_row.append(Paragraph(_pdf_cell_wrap(row.get(column, "-"), column), style))
            table_rows.append(rendered_row)

    style_tokens = {
        "summary_table": {
            "header_bg": PDF_BRAND_NAVY,
            "grid": PDF_BRAND_LINE,
            "row_backgrounds": [rl_colors.white, PDF_SOFT_ALT],
            "header_top": 7.5,
            "header_bottom": 7.5,
            "cell_top": 5.8,
            "cell_bottom": 5.8,
            "padding": 5.6,
        },
        "object_table": {
            "header_bg": PDF_BRAND_BLUE,
            "grid": PDF_BRAND_LINE,
            "row_backgrounds": [rl_colors.white, PDF_SOFT_FILL],
            "header_top": 6.6,
            "header_bottom": 6.6,
            "cell_top": 5.2,
            "cell_bottom": 5.2,
            "padding": 5.0,
        },
        "detail_table": {
            "header_bg": PDF_BRAND_BLUE,
            "grid": PDF_BRAND_LINE,
            "row_backgrounds": [rl_colors.white, rl_colors.HexColor("#f8fafc")],
            "header_top": 5.8,
            "header_bottom": 5.8,
            "cell_top": 4.0,
            "cell_bottom": 4.0,
            "padding": 4.2,
        },
    }.get(table_kind, {
        "header_bg": PDF_BRAND_BLUE,
        "grid": PDF_BRAND_LINE,
        "row_backgrounds": [rl_colors.white, PDF_SOFT_FILL],
        "header_top": 6,
        "header_bottom": 6,
        "cell_top": 4.2,
        "cell_bottom": 4.2,
        "padding": 4.4,
    })
    table = Table(
        table_rows,
        colWidths=_post_crq_pdf_column_widths(columns, rows, total_width, table_kind=table_kind),
        repeatRows=1,
        splitByRow=1,
        splitInRow=1,
        longTableOptimize=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), style_tokens["header_bg"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, style_tokens["grid"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, style_tokens["grid"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), style_tokens["padding"] - (1.0 if wide_table else 0)),
                ("RIGHTPADDING", (0, 0), (-1, -1), style_tokens["padding"] - (1.0 if wide_table else 0)),
                ("TOPPADDING", (0, 0), (-1, 0), style_tokens["header_top"]),
                ("BOTTOMPADDING", (0, 0), (-1, 0), style_tokens["header_bottom"]),
                ("TOPPADDING", (0, 1), (-1, -1), style_tokens["cell_top"]),
                ("BOTTOMPADDING", (0, 1), (-1, -1), style_tokens["cell_bottom"]),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), style_tokens["row_backgrounds"]),
            ]
        )
    )
    return table


def _rows_to_markdown_table(columns: List[str], rows: List[Dict[str, Any]], limit: Optional[int] = None) -> str:
    if not columns:
        return "_Sense columnes disponibles._"
    if not rows:
        return "_Sense troballes per aquest check._"

    visible_rows = rows if limit in (None, 0) else rows[:limit]
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in visible_rows:
        body.append("| " + " | ".join(_normalize_text(row.get(column)) or "-" for column in columns) + " |")
    if limit not in (None, 0) and len(rows) > limit:
        body.append(f"\n_Mostrant {limit} de {len(rows)} files._")
    return "\n".join([header, sep, *body])


def _empty_criticality_text(criticality_key: str) -> str:
    mapping = {
        "CRITIC": "No s'han detectat incidÃ¨ncies crÃ­tiques en aquesta execuciÃ³.",
        "MITJA": "No s'han detectat incidÃ¨ncies mitjanes en aquesta execuciÃ³.",
        "BAIX": "No s'han detectat incidÃ¨ncies baixes en aquesta execuciÃ³.",
    }
    return mapping.get(criticality_key, "No s'han detectat incidÃ¨ncies en aquest bloc.")


def _build_post_crq_markdown_from_report_model(profile: str, report: Dict[str, Any]) -> str:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    results = report.get("results_by_check") or []
    report_model = report.get("report_model") or {}
    criticality_blocks = report_model.get("criticality_blocks") or []
    critical_cards = report_model.get("critical_incident_cards") or []
    detail_sections = report_model.get("detail_sections") or []
    time_filter = context.get("time_filter") or {}
    annex_entries = _build_annex_entries(report) if _should_include_annex(report) else []

    lines: List[str] = []
    lines.append(f"# Informe d'auditoria de canvis post-CRQ - Perfil: {profile}")
    lines.append("")
    lines.append("## Context de l'auditoria")
    lines.append(f"- Perfil actiu: **{profile}**")
    lines.append(f"- Fitxer de checks: **{context.get('source_file', 'N/A')}**")
    lines.append(f"- Mode temporal: **{_display_time_mode(time_filter)}**")
    lines.append(f"- PerÃ­ode aplicat: **{_display_period_label(time_filter)}**")
    lines.append(f"- Finestra consultada: **{_display_period_window(time_filter)}**")
    lines.append(f"- Darrera modificaciÃ³ detectada: **{summary.get('latest_change_at') or 'No disponible'}**")
    lines.append(f"- Esquemes filtrats: **{', '.join(context.get('schemas') or ['TOTS'])}**")
    lines.append("")
    lines.append("## Resum executiu ordenat per criticitat")
    lines.append(
        f"S'han executat **{summary.get('executed_checks', 0)}** checks, amb **{summary.get('checks_with_findings', 0)}** checks amb troballes i **{summary.get('checks_with_errors', 0)}** checks amb error."
    )
    lines.append("")

    for index, block in enumerate(criticality_blocks, start=2):
        lines.append(f"### 2.{index} IncidÃ¨ncies {_criticality_plural_label(block.get('criticality_key'))}")
        lines.append(block.get("action_text") or _criticality_action_text(block.get("criticality_key")))
        lines.append("")
        if not block.get("items"):
            lines.append("No s'han detectat incidÃ¨ncies en aquest bloc.")
            lines.append("")
            continue
        for item in block["items"]:
            lines.append(f"#### {item['check_id']} - {_display_title(item.get('title'))}")
            lines.append(item.get("summary_text") or "")
            examples = item.get("top_examples") or []
            if examples:
                lines.append("")
                for example in examples:
                    lines.append(
                        f"- Exemple: esquema **{example.get('schema') or 'N/A'}**, objecte **{example.get('object_name') or 'N/A'}**, lot **{example.get('lot') or 'SENSE LOT'}**, responsable **{example.get('responsable') or 'No assignat'}**."
                    )
            lines.append("")

    lines.append("## IncidÃ¨ncies crÃ­tiques detallades")
    lines.append("")
    if not critical_cards:
        lines.append("No s'han detectat incidÃ¨ncies crÃ­tiques en aquesta execuciÃ³.")
        lines.append("")
    else:
        for card in critical_cards:
            lines.append(f"### {card['check_id']} - {card['title']}")
            lines.append(f"- Severitat: **{card.get('severity') or 'N/A'}**")
            lines.append(f"- Esquema: **{card.get('schema') or 'No disponible'}**")
            lines.append(f"- Objecte afectat: **{card.get('object_name') or 'No disponible'}**")
            lines.append(f"- Lote: **{card.get('lot') or 'SENSE LOT'}**")
            lines.append(f"- Responsable: **{card.get('responsable') or 'No assignat'}**")
            lines.append(f"- Resum executiu: {card.get('summary_text') or 'No disponible'}")
            lines.append(f"- ExplicaciÃ³ tÃ¨cnica: {card.get('technical_explanation') or 'No disponible'}")
            lines.append(f"- EvidÃ¨ncia: {card.get('evidence_text') or 'No disponible'}")
            lines.append(f"- Impacte probable: {card.get('impact_text') or 'No disponible'}")
            lines.append(f"- AcciÃ³ recomanada: {card.get('recommended_action') or 'No disponible'}")
            lines.append(f"- ValidaciÃ³ posterior: {card.get('post_validation') or 'No disponible'}")
            if card.get("oracle_error_code"):
                lines.append(f"- Error Oracle: **{card['oracle_error_code']}** - {card.get('oracle_error_summary') or ''}")
            lines.append("")

    lines.append("## Detall de les consultes/checks")
    lines.append("")
    for section in detail_sections:
        source = next((item for item in results if item.get("check_id") == section.get("check_id")), None) or {}
        lines.append(f"### {section['check_id']} - {_display_title(section.get('title'))}")
        lines.append(f"- Criticitat: **{section.get('criticality') or source.get('criticitat') or 'Baix'}**")
        lines.append(f"- Estat: **{str(section.get('status') or source.get('status') or '').lower()}**")
        lines.append(f"- Troballes: **{section.get('finding_count', 0)}**")
        if section.get("overview"):
            lines.append(f"- ExplicaciÃ³: {section['overview']}")
        if source.get("error"):
            lines.append(f"- Error detectat: `{source['error']}`")
        lines.append("")
        lines.append(_rows_to_markdown_table(source.get("columns") or [], source.get("rows") or [], limit=None))
        lines.append("")

    if annex_entries:
        lines.append("## Annex A - AnÃ lisi funcional de cada check")
        lines.append("")
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- Check: **{entry['check_id']}**")
            lines.append(f"- TÃ­tol normalitzat: **{entry['title']}**")
            lines.append(f"- Severitat: **{entry['severitat']}**")
            lines.append(f"- Objectiu: {entry['objectiu']}")
            lines.append(f"- Impacte: {entry['impacte']}")
            lines.append(f"- Possible millora del check: {entry['possible_millora']}")
            lines.append(f"- Limitacions / falsos positius possibles: {entry['limitacions']}")
            lines.append(f"- RecomanaciÃ³ de remediaciÃ³: {entry['remediacio']}")
            lines.append("")

    return _fix_encoding("\n".join(lines))


def build_post_crq_markdown_report(profile: str, report: Dict[str, Any]) -> str:
    if report.get("report_model"):
        return _fix_encoding(_build_post_crq_markdown_from_report_model_final_v7(profile, report))
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    executed_checks = report.get("executed_checks") or []
    results = report.get("results_by_check") or []
    criticality_sections = summary.get("criticality_sections") or []
    import re as local_re
    def get_check_num(c_id):
        m = local_re.search(r"(\d+)", str(c_id))
        return int(m.group(1)) if m else 999

    # --- Load schema lot mapping ---
    import sqlite3
    from src.core.sqlite_paths import resolve_sqlite_path
    db_path = resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    schema_to_lot_mapping = {}
    try:
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                # Intentem llegir de schema_lots (taula nova)
                try:
                    cursor.execute("SELECT schema_name, lot_name FROM schema_lots")
                    schema_to_lot_mapping = {row[0].upper(): row[1] for row in cursor.fetchall()}
                except Exception:
                    pass
    except Exception:
        pass

    # Sort checks numerically
    results.sort(key=lambda x: get_check_num(x.get("check_id") or "999"))
    executed_checks.sort(key=lambda x: get_check_num(x.get("check_id") or "999"))
    for sec in criticality_sections:
        if "items" in sec:
            sec["items"].sort(key=lambda x: get_check_num(x.get("check_id") or "999"))

    # Fix encoding and add lot info to results
    for item in results:
        item["title"] = _fix_encoding(item.get("title", ""))
        item["summary_text"] = _fix_encoding(item.get("summary_text", ""))
        if "Lot" not in (item.get("columns") or []):
            lot_col_idx = -1
            columns = item.get("columns") or []
            if "esquema" in columns: lot_col_idx = columns.index("esquema")
            elif "schema" in columns: lot_col_idx = columns.index("schema")
            
            if lot_col_idx >= 0:
                item["columns"] = columns + ["Lot"]
                new_rows = []
                for row in (item.get("rows") or []):
                    schema_val = str(row.get(columns[lot_col_idx]) or "").upper()
                    lot_val = schema_to_lot_mapping.get(schema_val, "Lot desconegut")
                    row["Lot"] = lot_val
                    new_rows.append(row)
                item["rows"] = new_rows

    results_by_id = {str(item.get("check_id")): item for item in results}
    time_filter = context.get("time_filter") or {}
    detected_time_range = summary.get("detected_time_range") or {}
    criticality_sections = summary.get("criticality_sections") or []
    check11_ai_summary = summary.get("check11_ai_summary") or {}
    annex_entries = _build_annex_entries(report) if _should_include_annex(report) else []
    if annex_entries:
        annex_entries.sort(key=lambda x: get_check_num(x.get("check_id") or "999"))


    lines: List[str] = []
    lines.append(f"# Informe d'auditoria de canvis post-CRQ - Perfil: {profile}")
    lines.append("")
    lines.append("## Context de l'auditoria")
    lines.append(f"- Perfil actiu: **{profile}**")
    lines.append(f"- Fitxer de checks: **{context.get('source_file', 'N/A')}**")
    lines.append(f"- Mode temporal: **{_display_time_mode(time_filter)}**")
    lines.append(f"- PerÃ­ode aplicat: **{_display_period_label(time_filter)}**")
    lines.append(f"- Finestra consultada: **{_display_period_window(time_filter)}**")
    if detected_time_range.get("start_at") and detected_time_range.get("end_at"):
        lines.append(f"- Rang real detectat a les dades: **{detected_time_range['start_at']} -> {detected_time_range['end_at']}**")
    lines.append(f"- Darrera modificaciÃ³ detectada: **{summary.get('latest_change_at') or 'No disponible'}**")
    if time_filter.get("resolved_on"):
        lines.append(f"- Data de resoluciÃ³: **{time_filter['resolved_on']}**")
    lines.append(f"- Esquemes filtrats: **{', '.join(context.get('schemas') or ['TOTS'])}**")
    lines.append("")
    lines.append("## Resum executiu")
    lines.append(f"- Checks executats: **{summary.get('executed_checks', 0)}**")
    lines.append(f"- Checks amb troballes: **{summary.get('checks_with_findings', 0)}**")
    lines.append(f"- Total de registres afectats: **{summary.get('total_findings', 0)}**")
    lines.append(f"- Checks amb error: **{summary.get('checks_with_errors', 0)}**")
    lines.append("")

    # --- Nova taula resum per Check i Lot ---
    findings_by_check = []
    for item in results:
        count = len(item.get("rows") or [])
        if count > 0:
            # Obtenim lots Ãºnics per aquest check
            lots = sorted(list(set(row.get("Lot", "SENSE LOT") for row in (item.get("rows") or []))))
            lots_str = ", ".join(lots) if lots else "-"
            findings_by_check.append({
                "Check": item.get("check_id"),
                "TÃ­tol": item.get("title"),
                "Severitat": item.get("severity", "N/A"),
                "Troballes": count,
                "Lots": lots_str
            })
    
    if findings_by_check:
        lines.append("### Resum de troballes per Check i Lot")
        lines.append("")
        # Ordre numÃ¨ric ja garantit per la sort de 'results' prÃ¨via
        summary_cols = ["Check", "Lots", "Troballes", "TÃ­tol", "Severitat"]
        lines.append(_rows_to_markdown_table(summary_cols, findings_by_check))
        lines.append("")
    lines.append(f"- Esquemes amb canvis detectats: **{summary.get('schemas_with_detected_changes', 0)}**")
    lines.append("")
    lines.append("### 2.1 KPI per criticitat")
    for criticality in CRITICALITY_ORDER:
        label = _criticality_label(criticality)
        lines.append(f"- **{label}**: {(summary.get('findings_by_criticality') or {}).get(label, 0)}")
    lines.append("")

    for index, section in enumerate(criticality_sections, start=2):
        lines.append(f"### 2.{index} IncidÃ¨ncies {_criticality_plural_label(section['criticality_key'])}")
        lines.append(section["action_text"])
        lines.append("")
        if not section.get("items"):
            lines.append(_empty_criticality_text(section["criticality_key"]))
        else:
            for item in section["items"]:
                check_meta = results_by_id.get(str(item.get("check_id"))) or {}
                lines.append(f"#### {item['check_id']} - {_display_title(check_meta.get('title') or item['check_id'])}")
                lines.append("")
                lines.append(item["summary_text"])
                lines.append("")
                lines.append(f"AcciÃ³ recomanada: {section['action_text']}")
                if item.get("error"):
                    lines.append("")
                    lines.append(f"Error detectat: `{item['error']}`")
                lines.append("")
        lines.append("")

    if check11_ai_summary:
        lines.append("### 2.5 Resum IA del CHECK_12")
        lines.append(f"- Total de troballes: **{check11_ai_summary.get('total_findings', 0)}**")
        lines.append(f"- Mala praxis: **{check11_ai_summary.get('mala_praxis', 0)}**")
        lines.append(f"- Fals positiu: **{check11_ai_summary.get('falso_positivo', 0)}**")
        lines.append(f"- RevisiÃ³ manual: **{check11_ai_summary.get('revision_manual', 0)}**")
        lines.append(f"- Estat anÃ lisi IA: **{check11_ai_summary.get('estat_analisi_ia') or 'no disponible'}**")
        lines.append("")

    lines.append("## Detall de les consultes/checks")
    lines.append("")
    lines.append("| CHECK | tÃ­tol | criticitat | estat | files | lot afectat |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in executed_checks:
        affected_lot = "N/A"
        if item.get("row_count", 0) > 0:
            c_id = str(item.get("check_id"))
            res_item = results_by_id.get(c_id)
            if res_item and res_item.get("rows"):
                lots = set(str(r.get("Lot")) for r in res_item["rows"] if r.get("Lot"))
                affected_lot = ", ".join(sorted(list(lots))) if lots else "desconegut"

        lines.append(
            f"| {item.get('check_id')} | {_display_title(item.get('title'))} | {item.get('criticitat') or item.get('severitat')} | "
            f"{str(item.get('status') or '').lower()} | {item.get('row_count', 0)} | {affected_lot} |"
        )
    lines.append("")

    for item in results:
        lines.append(f"## {item.get('check_id')} - {_display_title(item.get('title'))}")
        lines.append(f"- criticitat: **{item.get('criticitat') or item.get('severitat')}**")
        if item.get("check_id") == "CHECK_12":
            ai_meta = item.get("ai_analysis") or {}
            lines.append(f"- estat anÃ lisi IA: **{ai_meta.get('status') or 'no disponible'}**")
            if ai_meta.get("model"):
                lines.append(f"- model IA: **{ai_meta.get('model')}**")
        if item.get("criteri"):
            lines.append(f"- criteri: {_resolved_criteria_text(item.get('criteri'), time_filter.get('days_back'))}")
        lines.append(f"- estat: **{str(item.get('status') or '').lower()}**")
        lines.append(f"- files retornades: **{item.get('row_count', 0)}**")
        if item.get("error"):
            lines.append(f"- error: `{item.get('error')}`")
        lines.append("")
        lines.append(_rows_to_markdown_table(item.get("columns") or [], item.get("rows") or [], limit=None))
        lines.append("")

    if annex_entries:
        lines.append("## Annex A - AnÃ lisi funcional de cada check")
        lines.append("")
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- Check: **{entry['check_id']}**")
            lines.append(f"- TÃ­tol normalitzat: **{entry['title']}**")
            lines.append(f"- Severitat: **{entry['severitat']}**")
            lines.append(f"- Objectiu: {entry['objectiu']}")
            lines.append(f"- Impacte: {entry['impacte']}")
            lines.append(f"- Possible millora del check: {entry['possible_millora']}")
            lines.append(f"- Limitacions / falsos positius possibles: {entry['limitacions']}")
            lines.append(f"- RecomanaciÃ³ de remediaciÃ³: {entry['remediacio']}")
            lines.append("")

    return _fix_encoding("\n".join(lines))


def _build_post_crq_pdf_from_report_model(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    results = report.get("results_by_check") or []
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    styles = _build_post_crq_paragraph_styles()
    logo_path = Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"
    cover_path = Path(_project_root()) / "logo" / "portada.png"
    buffer = io.BytesIO()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.25 * cm,
        rightMargin=1.25 * cm,
        topMargin=3.1 * cm,
        bottomMargin=1.55 * cm,
        title=f"Informe Post-CRQ {profile}",
    )
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    cover_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="cover-frame")
    landscape_frame = Frame(0.9 * cm, 1.75 * cm, landscape(A4)[0] - 1.8 * cm, landscape(A4)[1] - 4.85 * cm, id="landscape-frame")
    footer_text = "GESIN @ 2026"
    doc.addPageTemplates(
        [
            PageTemplate(
                id="cover",
                pagesize=A4,
                frames=[cover_frame],
                onPage=lambda canvas, current_doc: _post_crq_pdf_cover(
                    canvas,
                    current_doc,
                    profile,
                    generated_at,
                    cover_path,
                    context,
                    summary,
                    context.get("time_filter") or {},
                ),
            ),
            PageTemplate(
                id="portrait",
                pagesize=A4,
                frames=[portrait_frame],
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, footer_text, logo_path),
            ),
            PageTemplate(
                id="landscape",
                pagesize=landscape(A4),
                frames=[landscape_frame],
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, footer_text, logo_path),
            ),
        ]
    )

    story: List[Any] = [NextPageTemplate("portrait"), PageBreak()]
    story.append(Paragraph("1. Context de l'auditoria", styles["heading"]))
    story.append(Paragraph(f"Perfil actiu: <b>{profile}</b>", styles["meta"]))
    story.append(Paragraph(f"Fitxer de checks: <b>{html.escape(str(context.get('source_file') or 'N/A'))}</b>", styles["meta"]))
    story.append(Paragraph(f"Mode temporal: <b>{_display_time_mode(context.get('time_filter') or {})}</b>", styles["meta"]))
    story.append(Paragraph(f"PerÃ­ode aplicat: <b>{_display_period_label(context.get('time_filter') or {})}</b>", styles["meta"]))
    story.append(Paragraph(f"Finestra consultada: <b>{_display_period_window(context.get('time_filter') or {})}</b>", styles["meta"]))
    story.append(Paragraph(f"Darrera modificaciÃ³ detectada: <b>{summary.get('latest_change_at') or 'No disponible'}</b>", styles["meta"]))
    story.append(Paragraph(f"Esquemes filtrats: <b>{', '.join(context.get('schemas') or ['TOTS'])}</b>", styles["meta"]))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("2. Resum executiu ordenat per criticitat", styles["heading"]))
    story.append(
        Paragraph(
            f"S'han executat <b>{summary.get('executed_checks', 0)}</b> checks, amb <b>{summary.get('checks_with_findings', 0)}</b> checks amb troballes i <b>{summary.get('checks_with_errors', 0)}</b> checks amb error.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 0.15 * cm))

    for index, block in enumerate(report_model.get("criticality_blocks") or [], start=2):
        story.append(Paragraph(f"2.{index} IncidÃ¨ncies {_criticality_plural_label(block.get('criticality_key'))}", styles["heading"]))
        story.append(Paragraph(block.get("action_text") or _criticality_action_text(block.get("criticality_key")), styles["body"]))
        story.append(Spacer(1, 0.1 * cm))
        for item in block.get("items") or []:
            story.append(Paragraph(f"{item['check_id']} - {_display_title(item.get('title'))}", styles["check_heading"]))
            story.append(Paragraph(item.get("summary_text") or "", styles["body"]))
            for example in item.get("top_examples") or []:
                story.append(
                    Paragraph(
                        f"Exemple: esquema <b>{example.get('schema') or 'N/A'}</b>, objecte <b>{example.get('object_name') or 'N/A'}</b>, lot <b>{example.get('lot') or 'SENSE LOT'}</b>, responsable <b>{example.get('responsable') or 'No assignat'}</b>.",
                        styles["body_small"],
                    )
                )
            story.append(Spacer(1, 0.12 * cm))

    story.append(Paragraph("3. IncidÃ¨ncies crÃ­tiques detallades", styles["heading"]))
    critical_cards = report_model.get("critical_incident_cards") or []
    if not critical_cards:
        story.append(Paragraph("No s'han detectat incidÃ¨ncies crÃ­tiques en aquesta execuciÃ³.", styles["body"]))
    else:
        for card in critical_cards:
            story.append(Paragraph(f"{card['check_id']} - {card['title']}", styles["check_heading"]))
            card_rows = [
                ["Severitat", card.get("severity") or "N/A"],
                ["Esquema", card.get("schema") or "No disponible"],
                ["Objecte afectat", card.get("object_name") or "No disponible"],
                ["Lote", card.get("lot") or "SENSE LOT"],
                ["Responsable", card.get("responsable") or "No assignat"],
                ["Resum executiu", card.get("summary_text") or "No disponible"],
                ["ExplicaciÃ³ tÃ¨cnica", card.get("technical_explanation") or "No disponible"],
                ["EvidÃ¨ncia", card.get("evidence_text") or "No disponible"],
                ["Impacte probable", card.get("impact_text") or "No disponible"],
                ["AcciÃ³ recomanada", card.get("recommended_action") or "No disponible"],
                ["ValidaciÃ³ posterior", card.get("post_validation") or "No disponible"],
            ]
            if card.get("oracle_error_code"):
                card_rows.append(["Error Oracle", f"{card['oracle_error_code']} - {card.get('oracle_error_summary') or ''}"])
            table = Table(
                [[Paragraph(str(left), styles["table_header"]), Paragraph(str(right), styles["table_cell"])] for left, right in card_rows],
                colWidths=[4.4 * cm, doc.width - 4.4 * cm],
                repeatRows=0,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), rl_colors.HexColor("#1e3a8a")),
                        ("TEXTCOLOR", (0, 0), (0, -1), rl_colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.35, rl_colors.HexColor("#cbd5e1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ROWBACKGROUNDS", (1, 0), (1, -1), [rl_colors.white, rl_colors.HexColor("#f8fafc")]),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 0.18 * cm))

    story.append(Paragraph("4. Detall de les consultes/checks", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        source = next((item for item in results if item.get("check_id") == section.get("check_id")), None) or {}
        use_landscape = _detail_requires_landscape(source.get("columns") or [], source.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{section['check_id']} - {_display_title(section.get('title'))}", styles["check_heading"]))
        story.append(Paragraph(f"Criticitat: <b>{section.get('criticality') or source.get('criticitat') or 'Baix'}</b>", styles["meta"]))
        story.append(Paragraph(f"Estat: <b>{str(section.get('status') or source.get('status') or '').lower()}</b>", styles["meta"]))
        story.append(Paragraph(f"Troballes: <b>{section.get('finding_count', 0)}</b>", styles["meta"]))
        if section.get("overview"):
            story.append(Paragraph(section["overview"], styles["body"]))
        if source.get("error"):
            story.append(Paragraph(f"Error detectat: <b>{html.escape(str(source['error']))}</b>", styles["body"]))
        story.append(Spacer(1, 0.12 * cm))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(source.get("columns") or [], source.get("rows") or [], current_width, styles))

    if _should_include_annex(report):
        story.append(NextPageTemplate("portrait"))
        story.append(PageBreak())
        story.append(Paragraph("5. Annex A - AnÃ lisi funcional de cada check", styles["heading"]))
        for entry in _build_annex_entries(report):
            story.append(Paragraph(f"{entry['check_id']} - {entry['title']}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Objectiu:</b> {html.escape(entry['objectiu'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte:</b> {html.escape(entry['impacte'])}", styles["body"]))
            story.append(Paragraph(f"<b>Possible millora del check:</b> {html.escape(entry['possible_millora'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions / falsos positius possibles:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>RecomanaciÃ³ de remediaciÃ³:</b> {html.escape(entry['remediacio'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))

    doc.build(story)
    return buffer.getvalue()


def _visible_report_value(value: Any) -> bool:
    normalized = _normalize_key(value)
    return normalized not in {"", "no_informat", "no_assignat", "responsable_no_informat"}


def _build_annex_entries_v2(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    catalog = load_check_explanation_catalog()
    executed_checks = _sort_check_dicts(report.get("executed_checks") or [])
    entries: List[Dict[str, Any]] = []
    for item in executed_checks:
        check_id = str(item.get("check_id") or "").strip()
        if not check_id:
            continue
        guidance = catalog.get(check_id, {})
        entries.append(
            {
                "check_id": check_id,
                "title": _fix_encoding(_display_title(item.get("title") or guidance.get("title") or check_id)),
                "severitat": _fix_encoding(item.get("severitat") or item.get("criticitat") or "N/A"),
                "que_detecta": _fix_encoding(guidance.get("que_detecta") or "Sense explicació funcional disponible."),
                "per_que_es_important": _fix_encoding(guidance.get("per_que_es_important") or "Sense context d'impacte disponible."),
                "impacte_sobre_lot": _fix_encoding(guidance.get("impacte_sobre_lot") or "Impacte sobre el lot pendent de concretar."),
                "com_revisar": _fix_encoding(guidance.get("com_revisar") or "Revisar la incidència amb el detall tècnic del check."),
                "com_corregir": _fix_encoding(guidance.get("com_corregir") or "Aplicar la correcció estructural recomanada."),
                "limitacions": _fix_encoding(guidance.get("limitacions") or "Sense limitacions documentades."),
                "columnes_taula_recomanades": [_fix_encoding(col) for col in (guidance.get("columnes_taula_recomanades") or [])],
                "validacio_posterior": _fix_encoding(guidance.get("validacio_posterior") or "Reexecutar el check després de la correcció."),
            }
        )
    return entries


def _report_model_index_entries_v2(include_annex: bool) -> List[str]:
    entries = [
        "1. Índex",
        "2. Paràmetres d'execució",
        "3. Resum executiu per lots",
        "4. Incidències crítiques agrupades per check",
        "5. Resultat detallat de les consultes",
        "6. Observacions finals",
    ]
    if include_annex:
        entries.append("7. Annex A - Guia funcional dels checks")
    return entries


def _report_model_parameters_rows_v2(report: Dict[str, Any]) -> List[tuple[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    time_window = execution_parameters.get("time_window") or {}
    enabled_checks = execution_parameters.get("enabled_checks") or report_model.get("enabled_checks") or []
    schemas = execution_parameters.get("schemas") or context.get("schemas") or []
    time_window_label = _format_display_time_range(
        start_raw=time_window.get("start_at") or time_window.get("range_start_at") or time_window.get("start_date"),
        end_raw=time_window.get("end_at") or time_window.get("range_end_at") or time_window.get("end_date"),
    )

    return [
        ("Perfil", execution_parameters.get("profile") or context.get("profile") or "-"),
        ("Data i hora", execution_parameters.get("generated_at") or "-"),
        ("Finestra consultada", time_window_label),
        ("Idioma", execution_parameters.get("language") or "Català"),
        ("Codificació", execution_parameters.get("encoding") or "UTF-8"),
        ("Fitxer de checks", execution_parameters.get("source_file") or context.get("source_file") or "-"),
        (
            "Checks activats",
            ", ".join(
                f"{item.get('check_id')} ({_fix_encoding(item.get('criticality') or '-')})"
                for item in enabled_checks
            ) or "-",
        ),
        ("Esquemes o lots filtrats", ", ".join(schemas) if schemas else "TOTS"),
    ]


def _build_post_crq_markdown_from_report_model_v2(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [f"# Informe d'auditoria de canvis post-CRQ - Perfil: {profile}", ""]

    lines.append("## 1. Índex")
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        lines.append(f"- {entry}")
    lines.append("")

    lines.append("## 2. Paràmetres d'execució")
    for label, value in _report_model_parameters_rows_v2(report):
        if _visible_report_value(value):
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    lines.append("## 3. Resum executiu per lots")
    lot_summary = report_model.get("lot_summary") or []
    if not lot_summary:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    else:
        lot_columns = [
            "Lot",
            "Crítiques",
            "Altes",
            "Mitjanes",
            "Baixes",
            "Checks afectats",
            "Què s'ha de solucionar primer",
            "Impacte principal",
            "Prioritat",
        ]
        lot_rows = []
        for row in lot_summary:
            lot_rows.append(
                {
                    "Lot": row.get("lot") or "SENSE LOT",
                    "Crítiques": row.get("critical") or 0,
                    "Altes": row.get("high") or 0,
                    "Mitjanes": row.get("medium") or 0,
                    "Baixes": row.get("low") or 0,
                    "Checks afectats": ", ".join(row.get("checks") or []) or "-",
                    "Què s'ha de solucionar primer": row.get("first_action") or "-",
                    "Impacte principal": row.get("dominant_impact") or "-",
                    "Prioritat": row.get("priority") or "Baix",
                }
            )
        lines.append(_rows_to_markdown_table(lot_columns, lot_rows, limit=None))
    lines.append("")

    lines.append("## 4. Incidències crítiques agrupades per check")
    critical_groups = report_model.get("critical_checks_grouped") or []
    if not critical_groups:
        lines.append("No s'han detectat incidències crítiques en aquesta execució.")
        lines.append("")
    else:
        for card in critical_groups:
            lines.append(f"### {card.get('check_id')} - {_fix_encoding(_display_title(card.get('title')))}")
            lines.append(f"**Acció recomanada:** {_fix_encoding(card.get('recommended_action') or '-')}")
            lines.append("")
            lines.append(f"**Impacte sobre el lot:** {_fix_encoding(card.get('impact_text') or '-')}")
            lines.append("")
            lines.append(f"**Evidència resumida:** {_fix_encoding(card.get('summary_text') or '-')}")
            if card.get("review_steps"):
                lines.append("")
                lines.append(f"**Com s'ha de revisar:** {_fix_encoding(card.get('review_steps'))}")
            if card.get("post_validation"):
                lines.append("")
                lines.append(f"**Validació posterior:** {_fix_encoding(card.get('post_validation'))}")
            lines.append("")
            lot_rows = card.get("lot_rows") or []
            if lot_rows:
                lines.append(
                    _rows_to_markdown_table(
                        ["lot", "esquema", "objecte", "severitat", "dada_tecnica", "accio_recomanada"],
                        lot_rows,
                        limit=None,
                    )
                )
            lines.append("")

    lines.append("## 5. Resultat detallat de les consultes")
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {section.get('criticality') or 'Baix'}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")

    lines.append("## 6. Observacions finals")
    final_observations = report_model.get("final_observations") or {}
    blocking = final_observations.get("blocking_errors") or []
    warnings = final_observations.get("warnings") or []
    next_steps = final_observations.get("next_steps") or []
    if blocking:
        lines.append("### Bloquejos")
        for item in blocking:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if warnings:
        lines.append("### Advertiments")
        for item in warnings:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if next_steps:
        lines.append("### Següents passos")
        for item in next_steps:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")

    if annex_entries:
        lines.append("## 7. Annex A - Guia funcional dels checks")
        lines.append("")
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- **Què detecta:** {entry['que_detecta']}")
            lines.append(f"- **Per què és important:** {entry['per_que_es_important']}")
            lines.append(f"- **Impacte sobre el lot:** {entry['impacte_sobre_lot']}")
            lines.append(f"- **Com s'ha de revisar:** {entry['com_revisar']}")
            lines.append(f"- **Com es pot corregir:** {entry['com_corregir']}")
            lines.append(f"- **Limitacions o falsos positius:** {entry['limitacions']}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {entry['validacio_posterior']}")
            lines.append("")

    return _fix_encoding("\n".join(lines))


def _build_labeled_pdf_table_v2(
    rows: List[tuple[str, str]],
    total_width: float,
    styles: Dict[str, ParagraphStyle],
    table_kind: str = "label_table",
) -> Table:
    table_rows = []
    cell_style = styles.get("table_cell_large", styles["table_cell"]) if table_kind == "label_table_large" else styles["table_cell"]
    for label, value in rows:
        label_text = html.unescape(_fix_encoding(label))
        value_text = html.unescape(_fix_encoding(value))
        table_rows.append(
            [
                Paragraph(f"<b>{safe_pdf_text(label_text)}</b>", cell_style),
                Paragraph(safe_pdf_text(value_text), cell_style),
            ]
        )
    tokens = {
        "label_table": {
            "label_bg": PDF_SOFT_ALT,
            "body_bg": rl_colors.white,
            "grid": PDF_BRAND_LINE,
            "padding": 6.2,
        },
        "label_table_large": {
            "label_bg": PDF_SOFT_ALT,
            "body_bg": rl_colors.white,
            "grid": PDF_BRAND_LINE,
            "padding": 6.8,
        },
        "compact_label_table": {
            "label_bg": PDF_SOFT_FILL,
            "body_bg": rl_colors.white,
            "grid": PDF_BRAND_LINE,
            "padding": 5.0,
        },
    }.get(
        table_kind,
        {
            "label_bg": PDF_SOFT_ALT,
            "body_bg": rl_colors.white,
            "grid": PDF_BRAND_LINE,
            "padding": 6.2,
        },
    )
    table = Table(table_rows, colWidths=[4.6 * cm, max(total_width - (4.6 * cm), 5 * cm)], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), tokens["label_bg"]),
                ("BACKGROUND", (1, 0), (1, -1), tokens["body_bg"]),
                ("BOX", (0, 0), (-1, -1), 0.45, tokens["grid"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, tokens["grid"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), tokens["padding"]),
                ("RIGHTPADDING", (0, 0), (-1, -1), tokens["padding"]),
                ("TOPPADDING", (0, 0), (-1, -1), tokens["padding"]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), tokens["padding"]),
            ]
        )
    )
    return table


def _build_post_crq_pdf_from_report_model_v2(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    regular_font, bold_font = _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.9 * cm,
        bottomMargin=1.4 * cm,
    )
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.75 * cm
    landscape_frame = Frame(
        landscape_margin,
        landscape_margin,
        landscape_pagesize[0] - (2 * landscape_margin),
        landscape_pagesize[1] - (2 * landscape_margin),
        id="landscape-frame",
    )
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates(
        [
            PageTemplate(
                id="cover",
                frames=[cover_frame],
                pagesize=A4,
                onPage=lambda canvas, current_doc: _post_crq_pdf_cover(
                    canvas,
                    current_doc,
                    profile,
                    generated_at,
                    cover_path,
                    context,
                    summary,
                    context.get("time_filter") or {},
                ),
            ),
            PageTemplate(
                id="portrait",
                frames=[portrait_frame],
                pagesize=A4,
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(
                    canvas,
                    current_doc,
                    profile,
                    generated_at,
                    "GESIN @ 2026",
                    logo_path,
                    show_header=True,
                ),
            ),
            PageTemplate(
                id="landscape",
                frames=[landscape_frame],
                pagesize=landscape_pagesize,
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(
                    canvas,
                    current_doc,
                    profile,
                    generated_at,
                    "GESIN @ 2026",
                    logo_path,
                    show_header=True,
                ),
            ),
        ]
    )

    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    lot_summary = report_model.get("lot_summary") or []
    if lot_summary:
        lot_columns = ["Lot", "Crítiques", "Altes", "Mitjanes", "Baixes", "Checks afectats", "Què s'ha de solucionar primer", "Impacte principal", "Prioritat"]
        lot_rows = [
            {
                "Lot": item.get("lot") or "SENSE LOT",
                "Crítiques": item.get("critical") or 0,
                "Altes": item.get("high") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
                "Checks afectats": ", ".join(item.get("checks") or []) or "-",
                "Què s'ha de solucionar primer": item.get("first_action") or "-",
                "Impacte principal": item.get("dominant_impact") or "-",
                "Prioritat": item.get("priority") or "Baix",
            }
            for item in lot_summary
        ]
        story.append(_build_post_crq_table(lot_columns, lot_rows, doc.width, styles))
    else:
        story.append(Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("4. Incidències crítiques agrupades per check", styles["heading"]))
    critical_groups = report_model.get("critical_checks_grouped") or []
    if not critical_groups:
        story.append(Paragraph("No s'han detectat incidències crítiques en aquesta execució.", styles["body"]))
    else:
        for card in critical_groups:
            story.append(Paragraph(f"{html.escape(str(card.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(card.get('title'))))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Acció recomanada:</b> {html.escape(_fix_encoding(card.get('recommended_action') or '-'))}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(card.get('impact_text') or '-'))}", styles["body"]))
            story.append(Paragraph(f"<b>Evidència resumida:</b> {html.escape(_fix_encoding(card.get('summary_text') or '-'))}", styles["body"]))
            if card.get("review_steps"):
                story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(_fix_encoding(card.get('review_steps')))}", styles["body"]))
            if card.get("post_validation"):
                story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(card.get('post_validation')))}", styles["body"]))
            if card.get("lot_rows"):
                story.append(
                    _build_post_crq_table(
                        ["lot", "esquema", "objecte", "severitat", "dada_tecnica", "accio_recomanada"],
                        card.get("lot_rows") or [],
                        doc.width,
                        styles,
                    )
                )
            story.append(Spacer(1, 0.18 * cm))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("5. Resultat detallat de les consultes", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
        story.append(Spacer(1, 0.12 * cm))

    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    blocking = final_observations.get("blocking_errors") or []
    warnings = final_observations.get("warnings") or []
    next_steps = final_observations.get("next_steps") or []
    if blocking:
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in blocking:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if warnings:
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in warnings:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if next_steps:
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in next_steps:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))

    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex A - Guia funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(entry['que_detecta'])}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(entry['per_que_es_important'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(entry['impacte_sobre_lot'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(entry['com_revisar'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(entry['com_corregir'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(entry['validacio_posterior'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))

    doc.build(story)
    return buffer.getvalue()


def _humanize_duration_ms_v2(value: Any) -> str:
    try:
        duration_ms = int(value or 0)
    except (TypeError, ValueError):
        return "-"
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    if duration_ms < 60000:
        return f"{duration_ms / 1000:.2f} s".replace(".", ",")
    minutes, seconds = divmod(duration_ms // 1000, 60)
    return f"{minutes} min {seconds} s"


def _report_model_index_entries_v2(include_annex: bool) -> List[str]:
    entries = [
        "1. Portada",
        "2. Índex",
        "3. Paràmetres d'execució",
        "4. Resum executiu per lots",
        "5. Incidències prioritzades per lot",
        "6. Resultat detallat per check",
        "7. Observacions finals",
    ]
    if include_annex:
        entries.append("8. Annex funcional dels checks")
    return entries


def _report_model_parameters_rows_v2(report: Dict[str, Any]) -> List[tuple[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    time_window = execution_parameters.get("time_window") or {}
    schemas = execution_parameters.get("schemas") or context.get("schemas") or []
    return [
        ("Perfil", _fix_encoding(execution_parameters.get("profile") or context.get("profile") or "-")),
        ("Data i hora", _fix_encoding(execution_parameters.get("generated_at") or "-")),
        ("Mode temporal", _fix_encoding(_display_time_mode(context.get("time_filter") or {}))),
        ("Període aplicat", _fix_encoding(_display_period_label(context.get("time_filter") or {}))),
        (
            "Finestra consultada",
            _format_display_time_range(
                start_raw=time_window.get("start_at") or time_window.get("range_start_at") or time_window.get("start_date"),
                end_raw=time_window.get("end_at") or time_window.get("range_end_at") or time_window.get("end_date"),
            ),
        ),
        ("Idioma", "Català"),
        ("Codificació", "UTF-8"),
        ("Fitxer de checks", _fix_encoding(execution_parameters.get("source_file") or context.get("source_file") or "-")),
        ("Lots o esquemes filtrats", ", ".join(schemas) if schemas else "Tots"),
    ]


def _build_lot_summary_rows_v2(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in report_model.get("lot_summary") or []:
        check_descriptions = item.get("check_descriptions") or []
        rows.append(
            {
                "Lot": item.get("lot") or "SENSE LOT",
                "Crítiques": item.get("critical") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
                "Check afectat": ", ".join(entry.get("check_id") or "-" for entry in check_descriptions[:3]) or "-",
                "Descripció del check": " | ".join(
                    _fix_encoding(_display_title(entry.get("title") or entry.get("check_id") or "-"))
                    for entry in check_descriptions[:2]
                )
                or "-",
                "Prioritat": item.get("priority") or "Baix",
                "Acció inicial": _fix_encoding(item.get("first_action") or "-"),
            }
        )
    return rows


def _build_enabled_checks_text_v2(report_model: Dict[str, Any]) -> str:
    enabled_checks = report_model.get("enabled_checks") or []
    if not enabled_checks:
        return "Sense checks activats."
    return ", ".join(
        f"{item.get('check_id')} ({_fix_encoding(item.get('criticality') or '-')})"
        for item in enabled_checks
    )


def _markdown_lot_incident_group_lines_v2(group: Dict[str, Any]) -> List[str]:
    lines = [
        f"### Lot {group.get('lot') or 'SENSE LOT'} — {group.get('check') or '-'}",
        "",
        f"- **Descripció del check:** {_fix_encoding(_display_title(group.get('title') or group.get('check') or '-'))}",
        f"- **Severitat:** {_fix_encoding(group.get('severity') or '-')}",
        f"- **Termini orientatiu:** {group.get('termini_dies') if group.get('termini_dies') is not None else '-'} dies",
        "",
        f"**Impacte sobre el lot:** {_fix_encoding(group.get('impacte') or '-')}",
        "",
        f"**Acció recomanada:** {_fix_encoding(group.get('accio_recomanada') or '-')}",
        "",
        f"**Validació posterior:** {_fix_encoding(group.get('validacio_posterior') or '-')}",
        "",
        "**Esquemes afectats:**",
    ]
    for schema_group in group.get("schemas") or []:
        lines.append(f"- **{_fix_encoding(schema_group.get('nom') or '-')}** ({schema_group.get('object_count') or 0} objectes)")
        object_rows = []
        for objecte in schema_group.get("objectes") or []:
            object_rows.append(
                {key: _fix_encoding(value) for key, value in _incident_object_table_row_v7(schema_group, objecte).items()}
            )
        if object_rows:
            lines.append("")
            lines.append(_rows_to_markdown_table(["OBJECTE", "TIPUS", "DADA TÈCNICA"], object_rows, limit=None))
            lines.append("")
    return lines


def _build_post_crq_markdown_from_report_model_v2(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lot_summary_rows = _build_lot_summary_rows_v2(report_model)
    lot_incident_groups = report_model.get("lot_incident_groups") or []
    final_observations = report_model.get("final_observations") or {}

    critical_lot_count = sum(1 for item in report_model.get("lot_summary") or [] if (item.get("critical") or 0) > 0)
    lines: List[str] = [
        f"# Informe d'auditoria post-CRQ — {profile}",
        "",
        f"Data de generació: {_fix_encoding((report_model.get('execution_parameters') or {}).get('generated_at') or '-')}",
        f"Finestra auditada: {_report_model_parameters_rows_v2(report)[4][1]}",
        f"Resum global: {len(report_model.get('lot_summary') or [])} lots amb incidències; {critical_lot_count} lots amb incidències crítiques.",
        "",
        "## 1. Índex",
    ]
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        lines.append(f"- {entry}")
    lines.extend(
        [
            "",
            "## 2. Paràmetres d'execució",
        ]
    )
    for label, value in _report_model_parameters_rows_v2(report):
        if _visible_report_value(value):
            lines.append(f"- **{label}:** {_fix_encoding(value)}")
    lines.append("")
    lines.append(f"**Checks activats:** {_build_enabled_checks_text_v2(report_model)}")
    lines.append("")
    lines.append("## 3. Resum executiu per lots")
    lines.append("Aquest apartat resumeix, per a cada lot, les incidències detectades, els checks afectats, la prioritat i la primera acció recomanada.")
    lines.append("")
    if lot_summary_rows:
        lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Check afectat", "Descripció del check", "Prioritat", "Acció inicial"], lot_summary_rows, limit=None))
    else:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    lines.extend(["", "## 4. Incidències prioritzades per lot", ""])
    if lot_incident_groups:
        for group in lot_incident_groups:
            lines.extend(_markdown_lot_incident_group_lines_v2(group))
            lines.append("")
    else:
        lines.append("No hi ha incidències prioritzades per lot en aquesta execució.")
        lines.append("")
    lines.append("## 5. Resultat detallat per check")
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} — {_fix_encoding(_display_title(section.get('title') or '-'))}")
        lines.append(f"- **Criticitat:** {_fix_encoding(section.get('criticality') or 'Baix')}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")
    lines.append("## 6. Observacions finals")
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if annex_entries:
        lines.append("## 7. Annex funcional dels checks")
        lines.append("")
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} — {_fix_encoding(entry['title'])}")
            lines.append(f"- **Què detecta:** {_fix_encoding(entry['que_detecta'])}")
            lines.append(f"- **Per què és important:** {_fix_encoding(entry['per_que_es_important'])}")
            lines.append(f"- **Impacte sobre el lot:** {_fix_encoding(entry['impacte_sobre_lot'])}")
            lines.append(f"- **Com s'ha de revisar:** {_fix_encoding(entry['com_revisar'])}")
            lines.append(f"- **Com es pot corregir:** {_fix_encoding(entry['com_corregir'])}")
            lines.append(f"- **Limitacions o falsos positius:** {_fix_encoding(entry['limitacions'])}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(_fix_encoding(column) for column in entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {_fix_encoding(entry['validacio_posterior'])}")
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _post_crq_pdf_cover(canvas, doc, profile, generated_at, cover_path, context, summary, time_filter):
    width, height = A4
    if cover_path and cover_path.exists():
        canvas.drawImage(str(cover_path), 0, 4.8 * cm, width=width, height=height - (4.8 * cm), preserveAspectRatio=False, mask="auto")
    panel_x = 1.4 * cm
    panel_y = 1.1 * cm
    panel_w = width - (2.8 * cm)
    panel_h = 3.1 * cm
    canvas.setFillColor(rl_colors.HexColor("#0d2346"))
    canvas.roundRect(panel_x, panel_y, panel_w, panel_h, 12, stroke=0, fill=1)
    canvas.setFillColor(rl_colors.white)
    canvas.setFont("OracleAudit-Bold", 20)
    canvas.drawString(panel_x + 0.6 * cm, panel_y + panel_h - 0.75 * cm, f"Informe d'auditoria post-CRQ — {profile}")
    canvas.setFont("OracleAudit", 10)
    rows = [
        f"Data de generació: {generated_at or '-'}",
        f"Finestra auditada: {_resolve_report_time_window_label_v2(context.get('time_filter') or {})}",
        f"Període aplicat: {_display_period_label(time_filter)}",
        f"Resum global: {summary.get('lots_with_findings', 0) or 0} lots amb incidències; {summary.get('critical_lots', 0) or 0} lots amb incidències crítiques.",
    ]
    current_y = panel_y + panel_h - 1.35 * cm
    for row in rows:
        canvas.drawString(panel_x + 0.6 * cm, current_y, _fix_encoding(row))
        current_y -= 0.48 * cm


def _resolve_report_time_window_label_v2(time_filter: Dict[str, Any]) -> str:
    window = _resolve_time_window(time_filter or {})
    return f"{window.get('start_at') or '-'} -> {window.get('end_at') or '-'}"


def _build_pdf_lot_incident_block_v2(group: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> List[Any]:
    rows = [
        ("Lot", _fix_encoding(group.get("lot") or "SENSE LOT")),
        ("Check", _fix_encoding(group.get("check") or "-")),
        ("Descripció del check", _fix_encoding(_display_title(group.get("title") or group.get("check") or "-"))),
        ("Severitat", _fix_encoding(group.get("severity") or "-")),
        ("Termini orientatiu", f"{group.get('termini_dies') if group.get('termini_dies') is not None else '-'} dies"),
    ]
    blocks: List[Any] = [_build_labeled_pdf_table_v2(rows, total_width, styles)]
    blocks.append(Spacer(1, 0.08 * cm))
    blocks.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(group.get('impacte') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Acció recomanada:</b> {html.escape(_fix_encoding(group.get('accio_recomanada') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(group.get('validacio_posterior') or '-'))}", styles["body"]))
    for schema_group in group.get("schemas") or []:
        blocks.append(Spacer(1, 0.08 * cm))
        blocks.append(Paragraph(f"<b>Esquema:</b> {html.escape(_fix_encoding(schema_group.get('nom') or '-'))} ({schema_group.get('object_count') or 0} objectes)", styles["body"]))
        table_rows = [
            {key: _fix_encoding(value) for key, value in _incident_object_table_row_v7(schema_group, item).items()}
            for item in (schema_group.get("objectes") or [])
        ]
        if table_rows:
            blocks.append(_build_post_crq_table(["OBJECTE", "TIPUS", "DADA TÈCNICA"], table_rows, total_width, styles))
    blocks.append(Spacer(1, 0.16 * cm))
    return blocks


def _build_post_crq_pdf_from_report_model_v2(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    report_model = report.get("report_model") or {}
    summary = report.get("summary") or {}
    cover_summary = {
        **summary,
        "lots_with_findings": len(report_model.get("lot_summary") or []),
        "critical_lots": sum(1 for item in (report_model.get("lot_summary") or []) if (item.get("critical") or 0) > 0),
    }
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.75 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates(
        [
            PageTemplate(
                id="cover",
                frames=[cover_frame],
                pagesize=A4,
                onPage=lambda canvas, current_doc: _post_crq_pdf_cover(canvas, current_doc, profile, generated_at, cover_path, context, cover_summary, context.get("time_filter") or {}),
            ),
            PageTemplate(
                id="portrait",
                frames=[portrait_frame],
                pagesize=A4,
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True),
            ),
            PageTemplate(
                id="landscape",
                frames=[landscape_frame],
                pagesize=landscape_pagesize,
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True),
            ),
        ]
    )

    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    story.append(Paragraph("2. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("3. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    story.append(Spacer(1, 0.08 * cm))
    story.append(Paragraph(f"<b>Checks activats:</b> {html.escape(_build_enabled_checks_text_v2(report_model))}", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("4. Resum executiu per lots", styles["heading"]))
    story.append(
        Paragraph(
            "Aquest apartat resumeix, per a cada lot, les incidències detectades, els checks afectats, la prioritat i la primera acció recomanada.",
            styles["body"],
        )
    )
    lot_summary_rows = _build_lot_summary_rows_v2(report_model)
    if lot_summary_rows:
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Check afectat", "Descripció del check", "Prioritat", "Acció inicial"], lot_summary_rows, doc.width, styles))
    else:
        story.append(Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("5. Incidències prioritzades per lot", styles["heading"]))
    lot_incident_groups = report_model.get("lot_incident_groups") or []
    if lot_incident_groups:
        for group in lot_incident_groups:
            story.extend(_build_pdf_lot_incident_block_v2(group, styles, doc.width))
    else:
        story.append(Paragraph("No hi ha incidències prioritzades per lot en aquesta execució.", styles["body"]))

    story.append(Paragraph("6. Resultat detallat per check", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} — {html.escape(_fix_encoding(_display_title(section.get('title') or '-')))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Temps d'execució:</b> {html.escape(_humanize_duration_ms_v2(section.get('duration_ms') or 0))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
        story.append(Spacer(1, 0.12 * cm))

    story.append(PageBreak())
    story.append(Paragraph("7. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))

    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("8. Annex funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{entry['check_id']} — {html.escape(_fix_encoding(entry['title']))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(entry['que_detecta']))}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(entry['per_que_es_important']))}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(entry['impacte_sobre_lot']))}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(_fix_encoding(entry['com_revisar']))}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(_fix_encoding(entry['com_corregir']))}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(_fix_encoding(entry['limitacions']))}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(_fix_encoding(column) for column in entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(entry['validacio_posterior']))}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))

    doc.build(story)
    return buffer.getvalue()


def _resolve_report_time_window_label_final_v3(time_filter: Dict[str, Any]) -> str:
    return _fix_encoding(_display_period_window(time_filter or {}))


def _build_post_crq_markdown_from_report_model_final_v3(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [f"# Informe d'auditoria post-CRQ - {_fix_encoding(profile)}", "", "## 1. Índex"]
    lines.extend(f"- {entry}" for entry in _report_model_index_entries_v2(bool(annex_entries)))
    lines.extend(["", "## 2. Paràmetres d'execució", ""])
    for label, value in _report_model_parameters_rows_v2(report):
        lines.append(f"- **{label}:** {value}")
    enabled_checks = _fix_encoding(_build_enabled_checks_text_v2(report_model))
    if enabled_checks:
        lines.extend(["", "### Checks activats", enabled_checks])
    lines.extend(["", "## 3. Resum executiu per lots", "", "Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", ""])
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, limit=None))
    else:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    lines.extend(["", "## 4. Incidències prioritzades per lot", ""])
    lot_groups = report_model.get("lot_incident_groups") or []
    if lot_groups:
        for group in lot_groups:
            lines.extend(_markdown_lot_incident_group_lines_v2(group))
            lines.append("")
    else:
        lines.append("No hi ha incidències prioritzades per lot en aquesta execució.")
    lines.extend(["", "## 5. Resultat detallat per check", ""])
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {_fix_encoding(section.get('criticality') or 'Baix')}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")
    lines.extend(["## 6. Observacions finals", ""])
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if annex_entries:
        lines.extend(["## 7. Annex A - Guia funcional dels checks", ""])
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- **Què detecta:** {entry['que_detecta']}")
            lines.append(f"- **Per què és important:** {entry['per_que_es_important']}")
            lines.append(f"- **Impacte sobre el lot:** {entry['impacte_sobre_lot']}")
            lines.append(f"- **Com s'ha de revisar:** {entry['com_revisar']}")
            lines.append(f"- **Com es pot corregir:** {entry['com_corregir']}")
            lines.append(f"- **Limitacions o falsos positius:** {entry['limitacions']}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {entry['validacio_posterior']}")
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _post_crq_pdf_cover_final_v3(canvas, profile, generated_at, cover_path, summary, time_filter):
    width, height = A4
    canvas.saveState()
    if cover_path and cover_path.exists():
        image_height = height * 0.72
        canvas.drawImage(str(cover_path), 0, height - image_height, width=width, height=image_height, preserveAspectRatio=False, mask="auto")
    canvas.setFillColor(rl_colors.HexColor("#0f172a"))
    canvas.roundRect(1.2 * cm, 1.8 * cm, width - (2.4 * cm), 6.2 * cm, 12, fill=1, stroke=0)
    canvas.setFillColor(rl_colors.white)
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit-Regular" if "OracleAudit-Regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFont(title_font, 22)
    canvas.drawString(1.9 * cm, 7.2 * cm, "Informe d'auditoria post-CRQ")
    canvas.setFont(body_font, 11)
    lines = [
        f"Perfil: {_fix_encoding(profile)}",
        f"Data de generació: {_fix_encoding(generated_at or '-')}",
        f"Finestra auditada: {_resolve_report_time_window_label_final_v3(time_filter)}",
        f"Període aplicat: {_fix_encoding(_display_period_label(time_filter))}",
        f"Resum global: {summary.get('checks_with_findings', 0)} checks amb troballes; {summary.get('critical_findings', 0)} incidències crítiques",
    ]
    for index, line in enumerate(lines):
        canvas.drawString(1.9 * cm, 6.3 * cm - (index * 0.7 * cm), line)
    canvas.restoreState()


def _build_post_crq_pdf_from_report_model_final_v3(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover_final_v3(canvas, profile, generated_at, cover_path, summary, context.get("time_filter") or {})),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
    ])
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]
    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph("Checks activats", styles["check_heading"]))
        for line in enabled_checks:
            story.append(Paragraph(html.escape(line), styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    story.append(Paragraph("Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", styles["body"]))
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Checks afectats", "Acció inicial", "Impacte principal", "Prioritat"], lot_rows, doc.width, styles))
    else:
        story.append(Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("4. Incidències prioritzades per lot", styles["heading"]))
    lot_groups = report_model.get("lot_incident_groups") or []
    if lot_groups:
        for group in lot_groups:
            story.extend(_build_pdf_lot_incident_block_v2(group, styles, doc.width))
            story.append(Spacer(1, 0.18 * cm))
    else:
        story.append(Paragraph("No hi ha incidències prioritzades per lot en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("5. Resultat detallat per check", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Temps d'execució:</b> {html.escape(_humanize_duration_ms_v2(section.get('duration_ms') or 0))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(entry['que_detecta'])}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(entry['per_que_es_important'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(entry['impacte_sobre_lot'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(entry['com_revisar'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(entry['com_corregir'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(entry['validacio_posterior'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))
    doc.build(story)
    return buffer.getvalue()


def build_post_crq_pdf_report(profile: str, report: Dict[str, Any]) -> bytes:
    time_filter = (report.get("context") or {}).get("time_filter") or {}
    logger.debug(
        "Generating post-crq PDF profile=%s mode=%s range_start_at=%s range_end_at=%s start_date=%s end_date=%s",
        profile,
        time_filter.get("mode"),
        time_filter.get("range_start_at"),
        time_filter.get("range_end_at"),
        time_filter.get("start_date"),
        time_filter.get("end_date"),
    )
    if report.get("report_model"):
        # We NO LONGER call _sanitize_reportlab_payload here to avoid double escaping
        # (Paragraphs and Tables already escape their inputs via safe_pdf_text/_safe_xml)
        report_data = copy.deepcopy(report)
        try:
            return _build_post_crq_pdf_from_report_model_final_v7(profile, report_data)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            print(
                f"[post_crq_pdf] Falling back to safe PDF builder for profile={profile}: {exc}",
                file=sys.stderr,
            )
            try:
                return _build_post_crq_pdf_from_report_model_safe_fallback(profile, report_data)
            except Exception as fallback_exc:
                if "paraparser" not in str(exc).lower():
                    raise
                raise fallback_exc from exc
    # --- Load schema lot mapping ---
    import sqlite3
    db_path = resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    schema_to_lot_mapping = {}
    try:
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT schema_name, lot_name FROM schema_lots")
                schema_to_lot_mapping = {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        print(f"Error loading schema lots: {e}")
    # -------------------------------

    context = report.get("context") or {}
    summary = report.get("summary") or {}
    results = report.get("results_by_check") or []
    time_filter = context.get("time_filter") or {}
    criticality_sections = summary.get("criticality_sections") or []
    
    try:
        import re as local_re
        def get_check_num(c_id):
            m = local_re.search(r"(\d+)", str(c_id))
            return int(m.group(1)) if m else 999
        
        # Sort main results
        results.sort(key=lambda x: get_check_num(x.get("check_id") or "999"))
        
        # Sort executed checks (traceability)
        executed_checks = report.get("executed_checks") or []
        executed_checks.sort(key=lambda x: get_check_num(x.get("check_id") or "999"))
        report["executed_checks"] = executed_checks

        # Sort items within criticality sections
        for sec in criticality_sections:
            if "items" in sec:
                sec["items"].sort(key=lambda x: get_check_num(x.get("check_id") or "999"))
    except Exception:
        pass

    for item in results:
        item["title"] = _fix_encoding(item.get("title", ""))
        item["summary_text"] = _fix_encoding(item.get("summary_text", ""))
        cols = item.get("columns") or []
        rows = item.get("rows") or []
        schema_idx = -1
        if rows and len(rows) > 0 and cols:
            for i, col in enumerate(cols):
                if str(col).lower() in ["esquema", "propietari", "owner"]:
                    schema_idx = i
                    break
            if schema_idx >= 0 and "Lot" not in cols:
                cols.append("Lot")
                for r in rows:
                    curr_sch = str(r[schema_idx]).strip().upper() if len(r) > schema_idx else ""
                    r.append(schema_to_lot_mapping.get(curr_sch, "SENSE LOT"))

    for sec in criticality_sections:
        if "items" in sec:
            for s_itm in sec["items"]:
                if "summary_text" in s_itm:
                    s_itm["summary_text"] = _fix_encoding(s_itm["summary_text"])
    detected_time_range = summary.get("detected_time_range") or {}
    check11_ai_summary = summary.get("check11_ai_summary") or {}
    annex_entries = _build_annex_entries(report) if _should_include_annex(report) else []
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    styles = _build_post_crq_paragraph_styles()
    logo_path = Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"
    cover_path = Path(_project_root()) / "logo" / "portada.png"
    buffer = io.BytesIO()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.25 * cm,
        rightMargin=1.25 * cm,
        topMargin=3.1 * cm,
        bottomMargin=1.55 * cm,
        title=f"Informe Post-CRQ {profile}",
    )
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    cover_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="cover-frame")
    landscape_frame = Frame(0.9 * cm, 1.75 * cm, landscape(A4)[0] - 1.8 * cm, landscape(A4)[1] - 4.85 * cm, id="landscape-frame")
    footer_text = "GESIN @ 2026"
    doc.addPageTemplates(
        [
            PageTemplate(
                id="cover",
                pagesize=A4,
                frames=[cover_frame],
                onPage=lambda canvas, current_doc: _post_crq_pdf_cover(
                    canvas,
                    current_doc,
                    profile,
                    generated_at,
                    cover_path,
                    context,
                    summary,
                    time_filter,
                ),
            ),
            PageTemplate(
                id="portrait",
                pagesize=A4,
                frames=[portrait_frame],
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, footer_text, logo_path),
            ),
            PageTemplate(
                id="landscape",
                pagesize=landscape(A4),
                frames=[landscape_frame],
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, footer_text, logo_path),
            ),
        ]
    )

    story: List[Any] = []
    story.append(NextPageTemplate("portrait"))
    story.append(PageBreak())
    toc_rows = [
        [Paragraph('<a href="#context">1. Context de l\'auditoria</a>', styles["toc"])],
        [Paragraph('<a href="#resum">2. Resum executiu post-CRQ</a>', styles["toc"])],
        [Paragraph('<a href="#detall">3. Detall de les consultes/checks</a>', styles["toc"])],
    ]
    if annex_entries:
        toc_rows.append([Paragraph('<a href="#annex">4. Annex A - anàlisi funcional de cada check</a>', styles["toc"])])
    toc_table = Table(toc_rows, colWidths=[16.0 * cm])
    toc_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, rl_colors.HexColor("#dbe3ef")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(Paragraph("Índex", styles["heading"]))
    story.append(toc_table)
    story.append(Spacer(1, 0.55 * cm))
    story.append(
        _build_check_index_block(
            results,
            styles,
            16.0 * cm,
            anchor_builder=lambda check_id: f"check_{_safe_xml(str(check_id))}",
            min_body_rows=len(toc_rows) + max(1, len(toc_rows) // 2),
        )
    )

    story.append(PageBreak())
    story.append(Paragraph('<a name="context"/>1. Context de l\'auditoria', styles["heading"]))
    context_table = Table(
        [
            ["Fitxer origen", _safe_xml(str(context.get("source_file") or "-"))],
            ["Mode temporal", _safe_xml(_display_time_mode(time_filter))],
            ["Període aplicat", _safe_xml(_display_period_label(time_filter))],
            ["Finestra consultada", _safe_xml(_display_period_window(time_filter))],
            ["Rang real detectat", _safe_xml(f"{detected_time_range.get('start_at') or 'No disponible'} -> {detected_time_range.get('end_at') or 'No disponible'}")],
            ["Darrera modificació detectada", _safe_xml(summary.get("latest_change_at") or "No disponible")],
            ["Data de resolució", _safe_xml(str(time_filter.get("resolved_on") or "-"))],
            ["Esquemes", _safe_xml(", ".join(context.get("schemas") or ["TOTS"]))],
        ],
        colWidths=[4.4 * cm, 11.2 * cm],
    )
    context_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.45, rl_colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, 0), (0, -1), rl_colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 0), (0, -1), "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(context_table)

    story.append(Spacer(1, 0.18 * cm))
    story.append(Paragraph('<a name="resum"/>2. Resum executiu post-CRQ', styles["heading"]))
    story.append(
        Paragraph(
            "Visió resumida de l'auditoria post-canvi ordenada per criticitat i construïda amb dades reals retornades pels checks executats.",
            styles["body"],
        )
    )
    kpi_table = Table(
        [
            ["Checks executats", summary.get("executed_checks", 0)],
            ["Checks amb troballes", summary.get("checks_with_findings", 0)],
            ["Total registres afectats", summary.get("total_findings", 0)],
            ["Checks amb error", summary.get("checks_with_errors", 0)],
            ["Esquemes amb canvis detectats", summary.get("schemas_with_detected_changes", 0)],
            ["Darrera modificació detectada", summary.get("latest_change_at") or "No disponible"],
        ],
        colWidths=[8.0 * cm, 7.6 * cm],
    )
    kpi_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.45, rl_colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, 0), (0, -1), rl_colors.HexColor("#f8fafc")),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (0, -1), "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(kpi_table)
    
    # --- Nova taula resum per Check i Lot al PDF ---
    findings_by_check = []
    # Results ja estan ordenats numÃ¨ricament pel bloc anterior de build_post_crq_pdf_report o crides prÃ¨vies
    for item in results:
        count = len(item.get("rows") or [])
        if count > 0:
            lots = sorted(list(set(str(row.get("Lot", "SENSE LOT")) for row in (item.get("rows") or []))))
            lots_str = ", ".join(lots) if lots else "-"
            findings_by_check.append({
                "Check": item.get("check_id"),
                "Lots": lots_str,
                "Troballes": count,
                "Títol": _fix_encoding(item.get("title")),
                "Severitat": item.get("severity", "N/A")
            })

    if findings_by_check:
        story.append(Spacer(1, 0.38 * cm))
        story.append(Paragraph("2.1 Resum de troballes per Check i Lot", styles["heading"]))
        
        lot_summary_rows = [["Check", "Lots", "Troballes", "Títol", "Severitat"]]
        for f in findings_by_check:
            lot_summary_rows.append([
                _safe_xml(str(f["Check"])),
                Paragraph(_safe_xml(f["Lots"]), styles["body_small"]),
                _safe_xml(str(f["Troballes"])),
                Paragraph(_safe_xml(f["Títol"]), styles["body_small"]),
                _safe_xml(str(f["Severitat"]))
            ])
            
        lot_summary_table = Table(
            lot_summary_rows, 
            colWidths=[2.2*cm, 3.5*cm, 1.8*cm, 6.0*cm, 2.1*cm],
            repeatRows=1
        )
        lot_summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1e3a8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.45, rl_colors.HexColor("#cbd5e1")),
                    ("FONTNAME", (0, 0), (-1, 0), "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (2, 0), (2, -1), "CENTER"),
                ]
            )
        )
        story.append(lot_summary_table)

    severity_rows = [["Criticitat", "Total troballes"]]
    severity_styles = []
    for criticality in CRITICALITY_ORDER:
        label = _criticality_label(criticality)
        count = (summary.get("findings_by_criticality") or {}).get(label, 0)
        row_index = len(severity_rows)
        severity_rows.append(
            [
                Paragraph(label, styles["badge"]),
                count,
            ]
        )
        severity_styles.append(("BACKGROUND", (0, row_index), (0, row_index), _severity_badge_color(criticality)))
    severity_table = Table(severity_rows, colWidths=[7.8 * cm, 3.6 * cm], repeatRows=1)
    severity_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1e3a8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("GRID", (0, 0), (-1, -1), 0.45, rl_colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 0), (-1, 0), "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"),
                ("ALIGN", (1, 1), (1, -1), "CENTER"),
                ("TEXTCOLOR", (0, 1), (0, -1), rl_colors.white),
            ]
            + severity_styles
        )
    )
    story.append(Spacer(1, 0.38 * cm))
    story.append(Paragraph("2.1 KPI per criticitat", styles["heading"]))
    story.append(severity_table)

    results_by_id = {str(item.get("check_id")): item for item in results}
    for section_index, section in enumerate(criticality_sections, start=2):
        story.append(Spacer(1, 0.34 * cm))
        title_label = _safe_xml(str(_criticality_plural_label(section.get('criticality_key'))))
        story.append(Paragraph(f"2.{section_index} Incidències {title_label}", styles["heading"]))
        story.append(Paragraph(_safe_xml(section.get("action_text")), styles["body"]))
        if not section.get("items"):
            story.append(Paragraph(_safe_xml(_empty_criticality_text(section.get("criticality_key"))), styles["body_small"]))
            continue

        for item in section["items"]:
            check_meta = results_by_id.get(str(item.get("check_id"))) or {}
            story.append(Spacer(1, 0.12 * cm))
            
            lots_afectats = []
            if check_meta:
                c_cols = check_meta.get("columns") or []
                c_rows = check_meta.get("rows") or []
                if "Lot" in c_cols:
                    idx_lot = c_cols.index("Lot")
                    lots_afectats = sorted(list(set(str(r[idx_lot]) for r in c_rows if len(r) > idx_lot)))
            
            lots_text = f"<br/><b>Lots afectats identificats:</b> {_safe_xml(', '.join(lots_afectats))}" if lots_afectats else ""

            story.append(
                Paragraph(
                    f"{_safe_xml(str(item.get('check_id')))} — {_safe_xml(_display_title(check_meta.get('title') or item.get('check_id')))}",
                    styles["check_heading"],
                )
            )
            story.append(Paragraph(_safe_xml(str(item.get("summary_text") or "-")), styles["body"]))
            action_raw = section.get('action_text') or "-"
            story.append(Paragraph(f"<b>Acció recomanada:</b> {_safe_xml(action_raw)}{lots_text}", styles["meta"]))
            if item.get("error"):
                story.append(Paragraph(f"<b>Error detectat:</b> {_safe_xml(str(item['error']))}", styles["meta"]))

    if check11_ai_summary:
        story.append(Spacer(1, 0.34 * cm))
        story.append(Paragraph(_safe_xml("2.5 Resum IA del CHECK_12"), styles["heading"]))
        check11_table = Table(
            [
                ["Total troballes", check11_ai_summary.get("total_findings", 0)],
                ["Mala praxis", check11_ai_summary.get("mala_praxis", 0)],
                ["Fals positiu", check11_ai_summary.get("falso_positivo", 0)],
                ["Revisió manual", check11_ai_summary.get("revision_manual", 0)],
                ["Estat anàlisi IA", _safe_xml(check11_ai_summary.get("estat_analisi_ia") or "no disponible")],
            ],
            colWidths=[8.0 * cm, 7.6 * cm],
        )
        check11_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.45, rl_colors.HexColor("#d1d5db")),
                    ("BACKGROUND", (0, 0), (0, -1), rl_colors.HexColor("#f8fafc")),
                    ("FONTNAME", (0, 0), (0, -1), "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"),
                ]
            )
        )
        story.append(check11_table)

    story.append(Spacer(1, 0.42 * cm))
    story.append(Paragraph('<a name="detall"/>3. Detall de les consultes/checks', styles["heading"]))
    story.append(Paragraph(_safe_xml("Traçabilitat d'execució i detall complet ordenat per criticitat."), styles["body_small"]))
    trace_rows = [[
        Paragraph(_safe_xml("CHECK"), styles["table_header"]),
        Paragraph(_safe_xml("títol"), styles["table_header"]),
        Paragraph(_safe_xml("criticitat"), styles["table_header"]),
        Paragraph(_safe_xml("estat"), styles["table_header"]),
        Paragraph(_safe_xml("files"), styles["table_header"]),
        Paragraph(_safe_xml("temps (ms)"), styles["table_header"]),
    ]]
    severity_row_styles = []
    for row_index, item in enumerate(results, start=1):
        severity_text = str(item.get("criticitat") or item.get("severitat") or "")
        trace_rows.append([
            Paragraph(_safe_xml(str(item.get("check_id") or "")), styles["table_cell_center"]),
            Paragraph(_safe_xml(_display_title(item.get("title"))), styles["table_cell"]),
            Paragraph(_safe_xml(_criticality_label(severity_text)), styles["badge"]),
            Paragraph(_safe_xml(str(item.get("status") or "").lower()), styles["table_cell_center"]),
            Paragraph(str(item.get("row_count", 0)), styles["table_cell_center"]),
            Paragraph(str(item.get("duration_ms", 0)), styles["table_cell_center"]),
        ])
        severity_row_styles.append(
            ("BACKGROUND", (2, row_index), (2, row_index), _severity_badge_color(severity_text))
        )
    trace_table = Table(trace_rows, colWidths=[2.0 * cm, 9.1 * cm, 1.55 * cm, 1.4 * cm, 1.1 * cm, 1.45 * cm], repeatRows=1)
    trace_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1e3a8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("GRID", (0, 0), (-1, -1), 0.45, rl_colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 0), (-1, 0), "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"),
                ("ALIGN", (2, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TEXTCOLOR", (2, 1), (2, -1), rl_colors.white),
            ]
            + severity_row_styles
        )
    )
    story.append(trace_table)

    visible_results = [item for item in results if int(item.get("row_count", 0)) > 0 or item.get("status") != "ok"]
    detail_index = 1
    for item in visible_results:
        use_landscape = _detail_requires_landscape(item.get("columns") or [], item.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        if detail_index == 1:
            story.append(Paragraph("3.1 Detall de troballes", styles["heading"]))
            story.append(Spacer(1, 0.12 * cm))
        check_id_esc = _safe_xml(str(item.get("check_id")))
        story.append(
            Paragraph(
                f'<a name="check_{check_id_esc}"/>3.1.{detail_index} {check_id_esc} — {_safe_xml(_display_title(item.get("title")))}',
                styles["check_heading"],
            )
        )
        sev = item.get('criticitat') or item.get('severitat')
        story.append(
            Paragraph(
                f"<b>criticitat:</b> <font color='{_severity_badge_hex(sev)}'>{_safe_xml(_severity_badge_text(sev))}</font> | "
                f"<b>estat:</b> {_safe_xml(str(item.get('status') or '').lower())} | <b>files: {item.get('row_count', 0)}",
                styles["meta"],
            )
        )
        if item.get("check_id") == "CHECK_12":
            ai_meta = item.get("ai_analysis") or {}
            story.append(
                Paragraph(
                    f"<b>estat anàlisi IA:</b> {_safe_xml(str(ai_meta.get('status') or 'no disponible'))}"
                    + (f" | <b>model IA:</b> {_safe_xml(str(ai_meta.get('model')))}" if ai_meta.get("model") else ""),
                    styles["meta"],
                )
            )
        story.append(Paragraph(f"<b>criteri:</b> {_safe_xml(_resolved_criteria_text(item.get('criteri'), time_filter.get('days_back')))}", styles["meta"]))
        if item.get("error"):
            story.append(Paragraph(f"<b>error:</b> {_safe_xml(str(item.get('error')))}", styles["meta"]))
        columns = item.get("columns") or []
        rows = item.get("rows") or []
        
        schema_col_idx = -1
        for i, col in enumerate(columns):
            col_lower = str(col).lower()
            if col_lower in ["esquema", "propietari", "owner", "schema", "propietari_desti", "propietari_index"]:
                schema_col_idx = i
                break
                
        if schema_col_idx >= 0 and rows and schema_to_lot_mapping:
            from collections import defaultdict
            lots_data = defaultdict(list)
            for row in rows:
                schema_val = str(row[schema_col_idx]).strip().upper() if len(row) > schema_col_idx else ""
                lot_name = schema_to_lot_mapping.get(schema_val, "SENSE LOT")
                lots_data[lot_name].append(row)
                
            sorted_lots = sorted(list(lots_data.keys()), key=lambda k: (k == "SENSE LOT", k))
            
            for lot in sorted_lots:
                lot_rows = lots_data[lot]
                story.append(Spacer(1, 0.15 * cm))
                story.append(Paragraph(f"<b>Responsabilitat Lot: {html.escape(lot)}</b> ({len(lot_rows)} files)", styles["meta"]))
                story.append(Spacer(1, 0.05 * cm))
                story.append(
                    _build_post_crq_table(
                        columns,
                        lot_rows,
                        landscape_frame.width if use_landscape else portrait_frame.width,
                        styles,
                    )
                )
        else:
            story.append(Spacer(1, 0.15 * cm))
            story.append(
                _build_post_crq_table(
                    columns,
                    rows,
                    landscape_frame.width if use_landscape else portrait_frame.width,
                    styles,
                )
            )
        detail_index += 1

    if annex_entries:
        story.append(NextPageTemplate("portrait"))
        story.append(PageBreak())
        story.append(Paragraph('<a name="annex"/>4. Annex A - Anàlisi funcional de cada check', styles["heading"]))
        story.append(
            Paragraph(
                "Fitxes funcionals per interpretar cada control més enllà del criteri tècnic i orientar la remediació.",
                styles["body"],
            )
        )
        for annex_index, entry in enumerate(annex_entries, start=1):
            story.append(Spacer(1, 0.22 * cm))
            story.append(Paragraph(f"4.{annex_index} {html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Check:</b> {html.escape(str(entry.get('check_id', '')))}", styles["meta"]))
            story.append(Paragraph(f"<b>Títol normalitzat:</b> {html.escape(entry['title'])}", styles["meta"]))
            story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(str(entry['severitat']))}", styles["meta"]))
            story.append(Paragraph(f"<b>Objectiu:</b> {html.escape(entry['objectiu'])}", styles["meta"]))
            story.append(Paragraph(f"<b>Impacte:</b> {html.escape(entry['impacte'])}", styles["meta"]))
            story.append(Paragraph(f"<b>Possible millora del check:</b> {html.escape(entry['possible_millora'])}", styles["meta"]))
            story.append(Paragraph(f"<b>Limitacions / falsos positius possibles:</b> {html.escape(entry['limitacions'])}", styles["meta"]))
            story.append(Paragraph(f"<b>Recomanació de remediació:</b> {html.escape(entry['remediacio'])}", styles["meta"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _report_model_parameters_rows_v2(report: Dict[str, Any]) -> List[tuple[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    time_window = execution_parameters.get("time_window") or {}
    enabled_checks = execution_parameters.get("enabled_checks") or report_model.get("enabled_checks") or []
    schemas = execution_parameters.get("schemas") or context.get("schemas") or []
    time_window_label = _format_display_time_range(
        start_raw=time_window.get("start_at") or time_window.get("range_start_at") or time_window.get("start_date"),
        end_raw=time_window.get("end_at") or time_window.get("range_end_at") or time_window.get("end_date"),
    )

    return [
        ("Perfil", execution_parameters.get("profile") or context.get("profile") or "-"),
        ("Data i hora", execution_parameters.get("generated_at") or "-"),
        ("Finestra consultada", time_window_label),
        ("Idioma", execution_parameters.get("language") or "Català"),
        ("Codificació", execution_parameters.get("encoding") or "UTF-8"),
        ("Fitxer de checks", execution_parameters.get("source_file") or context.get("source_file") or "-"),
        (
            "Checks activats",
            ", ".join(
                f"{item.get('check_id')} ({_fix_encoding(item.get('criticality') or '-')})"
                for item in enabled_checks
            ) or "-",
        ),
        ("Esquemes o lots filtrats", ", ".join(schemas) if schemas else "TOTS"),
    ]


def _markdown_lot_group_lines_v2(card: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for lot_group in card.get("lot_groups") or []:
        lot = _fix_encoding(lot_group.get("lot") or "SENSE LOT")
        check_id = _fix_encoding(lot_group.get("check") or card.get("check_id") or "-")
        severitat = _fix_encoding(lot_group.get("severitat") or card.get("sql_severity") or "-")
        termini = lot_group.get("termini_dies")
        lines.append(f"#### Lot: {lot}")
        lines.append(f"- **Check:** {check_id}")
        lines.append(f"- **Severitat SQL:** {severitat}")
        lines.append(f"- **Termini orientatiu:** {termini if termini is not None else '-'} dies")
        lines.append("- **Esquemes afectats:**")
        for schema_group in lot_group.get("esquemes") or []:
            schema_name = _fix_encoding(schema_group.get("nom") or "-")
            lines.append(f"  - **{schema_name}**")
            objectes = schema_group.get("objectes") or []
            if objectes:
                for objecte in objectes:
                    lines.append(f"    - {_fix_encoding(objecte)}")
            else:
                lines.append("    - Sense objectes detallats")
        lines.append("")
    return lines


def _build_post_crq_markdown_from_report_model_v2(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [f"# Informe d'auditoria de canvis post-CRQ - Perfil: {profile}", ""]

    lines.append("## 1. Índex")
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        lines.append(f"- {entry}")
    lines.append("")

    lines.append("## 2. Paràmetres d'execució")
    for label, value in _report_model_parameters_rows_v2(report):
        if _visible_report_value(value):
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    lines.append("## 3. Resum executiu per lots")
    lot_summary = report_model.get("lot_summary") or []
    if not lot_summary:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")
    else:
        lot_columns = [
            "Lot",
            "Crítiques",
            "Altes",
            "Mitjanes",
            "Baixes",
            "Checks afectats",
            "Què s'ha de solucionar primer",
            "Impacte principal",
            "Prioritat",
        ]
        lot_rows = [
            {
                "Lot": row.get("lot") or "SENSE LOT",
                "Crítiques": row.get("critical") or 0,
                "Altes": row.get("high") or 0,
                "Mitjanes": row.get("medium") or 0,
                "Baixes": row.get("low") or 0,
                "Checks afectats": ", ".join(row.get("checks") or []) or "-",
                "Què s'ha de solucionar primer": row.get("first_action") or "-",
                "Impacte principal": row.get("dominant_impact") or "-",
                "Prioritat": row.get("priority") or "Baix",
            }
            for row in lot_summary
        ]
        lines.append(_rows_to_markdown_table(lot_columns, lot_rows, limit=None))
    lines.append("")

    lines.append("## 4. Incidències crítiques agrupades per check")
    critical_groups = report_model.get("critical_checks_grouped") or []
    if not critical_groups:
        lines.append("No s'han detectat incidències crítiques en aquesta execució.")
        lines.append("")
    else:
        for card in critical_groups:
            lines.append(f"### {card.get('check_id')} - {_fix_encoding(_display_title(card.get('title')))}")
            lines.append(f"**Acció recomanada:** {_fix_encoding(card.get('recommended_action') or '-')}")
            lines.append("")
            lines.append(f"**Impacte sobre el lot:** {_fix_encoding(card.get('impact_text') or '-')}")
            lines.append("")
            lines.append(f"**Evidència resumida:** {_fix_encoding(card.get('summary_text') or '-')}")
            if card.get("review_steps"):
                lines.append("")
                lines.append(f"**Com s'ha de revisar:** {_fix_encoding(card.get('review_steps'))}")
            if card.get("post_validation"):
                lines.append("")
                lines.append(f"**Validació posterior:** {_fix_encoding(card.get('post_validation'))}")
            lines.append("")
            if card.get("lot_groups"):
                lines.extend(_markdown_lot_group_lines_v2(card))
            elif card.get("lot_rows"):
                lines.append(
                    _rows_to_markdown_table(
                        ["lot", "esquema", "objecte", "severitat", "dada_tecnica", "accio_recomanada"],
                        card.get("lot_rows") or [],
                        limit=None,
                    )
                )
            lines.append("")

    lines.append("## 5. Resultat detallat de les consultes")
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {section.get('criticality') or 'Baix'}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")

    lines.append("## 6. Observacions finals")
    final_observations = report_model.get("final_observations") or {}
    blocking = final_observations.get("blocking_errors") or []
    warnings = final_observations.get("warnings") or []
    next_steps = final_observations.get("next_steps") or []
    if blocking:
        lines.append("### Bloquejos")
        for item in blocking:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if warnings:
        lines.append("### Advertiments")
        for item in warnings:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if next_steps:
        lines.append("### Següents passos")
        for item in next_steps:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")

    if annex_entries:
        lines.append("## 7. Annex A - Guia funcional dels checks")
        lines.append("")
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {entry['title']}")
            lines.append(f"- **Què detecta:** {entry['que_detecta']}")
            lines.append(f"- **Per què és important:** {entry['per_que_es_important']}")
            lines.append(f"- **Impacte sobre el lot:** {entry['impacte_sobre_lot']}")
            lines.append(f"- **Com s'ha de revisar:** {entry['com_revisar']}")
            lines.append(f"- **Com es pot corregir:** {entry['com_corregir']}")
            lines.append(f"- **Limitacions o falsos positius:** {entry['limitacions']}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {entry['validacio_posterior']}")
            lines.append("")

    return _fix_encoding("\n".join(lines))


def _build_pdf_lot_group_block_v2(card: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> List[Any]:
    blocks: List[Any] = []
    for lot_group in card.get("lot_groups") or []:
        blocks.append(
            _build_labeled_pdf_table_v2(
                [
                    ("Lot", _fix_encoding(lot_group.get("lot") or "SENSE LOT")),
                    ("Check", _fix_encoding(lot_group.get("check") or card.get("check_id") or "-")),
                    ("Severitat SQL", _fix_encoding(lot_group.get("severitat") or card.get("sql_severity") or "-")),
                    ("Termini orientatiu", f"{lot_group.get('termini_dies') if lot_group.get('termini_dies') is not None else '-'} dies"),
                ],
                total_width,
                styles,
            )
        )
        blocks.append(Spacer(1, 0.08 * cm))
        for schema_group in lot_group.get("esquemes") or []:
            blocks.append(Paragraph(f"<b>Esquema:</b> {html.escape(_fix_encoding(schema_group.get('nom') or '-'))}", styles["body"]))
            objectes = [_fix_encoding(item) for item in (schema_group.get("objectes") or [])]
            if objectes:
                blocks.append(Paragraph("<br/>".join(f"• {html.escape(objecte)}" for objecte in objectes), styles["body"]))
            else:
                blocks.append(Paragraph("Sense objectes detallats.", styles["body"]))
            blocks.append(Spacer(1, 0.08 * cm))
        blocks.append(Spacer(1, 0.12 * cm))
    return blocks


def _build_post_crq_pdf_from_report_model_v2(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    summary = report.get("summary") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.75 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates(
        [
            PageTemplate(
                id="cover",
                frames=[cover_frame],
                pagesize=A4,
                onPage=lambda canvas, current_doc: _post_crq_pdf_cover(canvas, current_doc, profile, generated_at, cover_path, context, summary, context.get("time_filter") or {}),
            ),
            PageTemplate(
                id="portrait",
                frames=[portrait_frame],
                pagesize=A4,
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True),
            ),
            PageTemplate(
                id="landscape",
                frames=[landscape_frame],
                pagesize=landscape_pagesize,
                onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True),
            ),
        ]
    )

    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_model_index_entries_v2(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    lot_summary = report_model.get("lot_summary") or []
    if lot_summary:
        lot_rows = [
            {
                "Lot": item.get("lot") or "SENSE LOT",
                "Crítiques": item.get("critical") or 0,
                "Altes": item.get("high") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
                "Checks afectats": ", ".join(item.get("checks") or []) or "-",
                "Què s'ha de solucionar primer": item.get("first_action") or "-",
                "Impacte principal": item.get("dominant_impact") or "-",
                "Prioritat": item.get("priority") or "Baix",
            }
            for item in lot_summary
        ]
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Altes", "Mitjanes", "Baixes", "Checks afectats", "Què s'ha de solucionar primer", "Impacte principal", "Prioritat"], lot_rows, doc.width, styles))
    else:
        story.append(Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("4. Incidències crítiques agrupades per check", styles["heading"]))
    critical_groups = report_model.get("critical_checks_grouped") or []
    if not critical_groups:
        story.append(Paragraph("No s'han detectat incidències crítiques en aquesta execució.", styles["body"]))
    else:
        for card in critical_groups:
            story.append(Paragraph(f"{html.escape(str(card.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(card.get('title'))))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Acció recomanada:</b> {html.escape(_fix_encoding(card.get('recommended_action') or '-'))}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(card.get('impact_text') or '-'))}", styles["body"]))
            story.append(Paragraph(f"<b>Evidència resumida:</b> {html.escape(_fix_encoding(card.get('summary_text') or '-'))}", styles["body"]))
            if card.get("review_steps"):
                story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(_fix_encoding(card.get('review_steps')))}", styles["body"]))
            if card.get("post_validation"):
                story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(card.get('post_validation')))}", styles["body"]))
            if card.get("lot_groups"):
                story.extend(_build_pdf_lot_group_block_v2(card, styles, doc.width))
            elif card.get("lot_rows"):
                story.append(_build_post_crq_table(["lot", "esquema", "objecte", "severitat", "dada_tecnica", "accio_recomanada"], card.get("lot_rows") or [], doc.width, styles))
            story.append(Spacer(1, 0.18 * cm))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("5. Resultat detallat de les consultes", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))
        story.append(Spacer(1, 0.12 * cm))

    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))

    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex A - Guia funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(str(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(entry['que_detecta'])}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(entry['per_que_es_important'])}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(entry['impacte_sobre_lot'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(entry['com_revisar'])}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(entry['com_corregir'])}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(entry['limitacions'])}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(entry['validacio_posterior'])}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))

    doc.build(story)
    return buffer.getvalue()


def _report_operational_index_entries_v4(include_annex: bool) -> List[str]:
    entries = [
        "1. Índex",
        "2. Paràmetres d'execució",
        "3. Resum executiu per lots",
        "4. Incidències prioritzades per lot",
        "5. Resultat detallat per check",
        "6. Observacions finals",
    ]
    if include_annex:
        entries.append("7. Annex funcional dels checks")
    return entries


def _report_operational_cover_summary_v4(report_model: Dict[str, Any]) -> str:
    lot_summary = report_model.get("lot_summary") or []
    lots_with_findings = len(lot_summary)
    critical_lots = sum(1 for item in lot_summary if (item.get("critical") or 0) > 0)
    return f"{lots_with_findings} lots amb incidències; {critical_lots} lots amb incidències crítiques"


def _markdown_lot_incident_group_lines_final_v4(group: Dict[str, Any]) -> List[str]:
    lines = [
        f"### Lot: {_fix_encoding(group.get('lot') or 'SENSE LOT')}",
        f"- **Check:** {_fix_encoding(group.get('check') or '-')}",
        f"- **Descripció del check:** {_fix_encoding(_display_title(group.get('title') or group.get('check') or '-'))}",
        f"- **Severitat:** {_fix_encoding(group.get('severity') or '-')}",
        f"- **Termini dies:** {group.get('termini_dies') if group.get('termini_dies') is not None else '-'}",
        "",
        f"**Impacte sobre el lot:** {_fix_encoding(group.get('impacte') or '-')}",
        "",
        f"**Acció recomanada:** {_fix_encoding(group.get('accio_recomanada') or '-')}",
        "",
        f"**Validació posterior:** {_fix_encoding(group.get('validacio_posterior') or '-')}",
        "",
        "**Esquemes afectats:**",
    ]
    for schema_group in group.get("schemas") or []:
        lines.append(f"- **{_fix_encoding(schema_group.get('nom') or '-')}**")
        for objecte in schema_group.get("objectes") or []:
            lines.append(f"  - {_fix_encoding(objecte.get('nom') or '-')}")
    return lines


def _build_post_crq_markdown_from_report_model_final_v4(profile: str, report: Dict[str, Any]) -> str:
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    lines: List[str] = [
        f"# Informe d'auditoria post-CRQ — {_fix_encoding(profile)}",
        "",
        f"Data de generació: {_fix_encoding((report_model.get('execution_parameters') or {}).get('generated_at') or '-')}",
        f"Finestra auditada: {_resolve_report_time_window_label_final_v3((report.get('context') or {}).get('time_filter') or {})}",
        f"Resum global: {_report_operational_cover_summary_v4(report_model)}",
        "",
        "## 1. Índex",
    ]
    lines.extend(f"- {entry}" for entry in _report_operational_index_entries_v4(bool(annex_entries)))
    lines.extend(["", "## 2. Paràmetres d'execució", ""])
    for label, value in _report_model_parameters_rows_v2(report):
        if _visible_report_value(value):
            lines.append(f"- **{_fix_encoding(label)}:** {_fix_encoding(value)}")

    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        lines.extend(["", "### Checks activats", enabled_checks])

    lines.extend([
        "",
        "## 3. Resum executiu per lots",
        "",
        "Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.",
        "",
    ])
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        lines.append(_rows_to_markdown_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Check afectat", "Descripció del check", "Prioritat", "Acció inicial"], lot_rows, limit=None))
    else:
        lines.append("No s'han detectat lots amb incidències en aquesta execució.")

    lines.extend(["", "## 4. Incidències prioritzades per lot", ""])
    lot_groups = report_model.get("lot_incident_groups") or []
    if lot_groups:
        for group in lot_groups:
            lines.extend(_markdown_lot_incident_group_lines_final_v4(group))
            lines.append("")
    else:
        lines.append("No hi ha incidències prioritzades per lot en aquesta execució.")

    lines.extend(["", "## 5. Resultat detallat per check", ""])
    for section in report_model.get("detail_sections") or []:
        lines.append(f"### {section.get('check_id')} - {_fix_encoding(_display_title(section.get('title')))}")
        lines.append(f"- **Criticitat:** {_fix_encoding(section.get('criticality') or 'Baix')}")
        lines.append(f"- **Estat:** {str(section.get('status') or '').lower()}")
        lines.append(f"- **Temps d'execució:** {_humanize_duration_ms_v2(section.get('duration_ms') or 0)}")
        lines.append(f"- **Què detecta:** {_fix_encoding(section.get('overview') or '-')}")
        if section.get("why_it_matters"):
            lines.append(f"- **Per què és important:** {_fix_encoding(section.get('why_it_matters'))}")
        lines.append(f"- **Troballes:** {section.get('finding_count') or 0}")
        lines.append("")
        lines.append(_rows_to_markdown_table(section.get("columns") or [], section.get("rows") or [], limit=None))
        lines.append("")

    lines.extend(["## 6. Observacions finals", ""])
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        lines.append("### Bloquejos")
        for item in final_observations.get("blocking_errors") or []:
            lines.append(f"- **{item.get('check_id')}:** {_fix_encoding(item.get('error') or 'Error no detallat')}")
        lines.append("")
    if final_observations.get("warnings"):
        lines.append("### Advertiments")
        for item in final_observations.get("warnings") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")
    if final_observations.get("next_steps"):
        lines.append("### Següents passos")
        for item in final_observations.get("next_steps") or []:
            lines.append(f"- {_fix_encoding(item)}")
        lines.append("")

    if annex_entries:
        lines.extend(["## 7. Annex funcional dels checks", ""])
        for entry in annex_entries:
            lines.append(f"### {entry['check_id']} - {_fix_encoding(entry['title'])}")
            lines.append(f"- **Què detecta:** {_fix_encoding(entry['que_detecta'])}")
            lines.append(f"- **Per què és important:** {_fix_encoding(entry['per_que_es_important'])}")
            lines.append(f"- **Impacte sobre el lot:** {_fix_encoding(entry['impacte_sobre_lot'])}")
            lines.append(f"- **Com s'ha de revisar:** {_fix_encoding(entry['com_revisar'])}")
            lines.append(f"- **Com es pot corregir:** {_fix_encoding(entry['com_corregir'])}")
            lines.append(f"- **Limitacions o falsos positius:** {_fix_encoding(entry['limitacions'])}")
            lines.append(f"- **Dades que s'han de mostrar a la taula:** {', '.join(_fix_encoding(column) for column in entry['columnes_taula_recomanades']) or '-'}")
            lines.append(f"- **Validació posterior:** {_fix_encoding(entry['validacio_posterior'])}")
            lines.append("")
    return _fix_encoding("\n".join(lines))


def _post_crq_pdf_cover_final_v4(canvas, profile: str, generated_at: str, cover_path: Path | None, report_model: Dict[str, Any], time_filter: Dict[str, Any]) -> None:
    width, height = A4
    canvas.saveState()
    if cover_path and cover_path.exists():
        image_width = width - (2.4 * cm)
        image_height = height * 0.56
        image_x = 1.2 * cm
        image_y = height - image_height - 1.25 * cm
        canvas.drawImage(
            str(cover_path),
            image_x,
            image_y,
            width=image_width,
            height=image_height,
            preserveAspectRatio=True,
            anchor="n",
            mask="auto",
        )
    canvas.setFillColor(rl_colors.HexColor("#0f172a"))
    canvas.roundRect(1.2 * cm, 1.8 * cm, width - (2.4 * cm), 6.3 * cm, 12, fill=1, stroke=0)
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit-Regular" if "OracleAudit-Regular" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFillColor(rl_colors.white)
    canvas.setFont(title_font, 22)
    canvas.drawString(1.9 * cm, 7.3 * cm, "Informe d'auditoria post-CRQ")
    canvas.setFont(body_font, 11)
    cover_lines = [
        f"Perfil: {_fix_encoding(profile)}",
        f"Data de generació: {_fix_encoding(generated_at or '-')}",
        f"Finestra auditada: {_resolve_report_time_window_label_final_v3(time_filter)}",
        f"Període aplicat: {_fix_encoding(_display_period_label(time_filter))}",
        f"Resum global: {_report_operational_cover_summary_v4(report_model)}",
    ]
    for index, line in enumerate(cover_lines):
        canvas.drawString(1.9 * cm, 6.35 * cm - (index * 0.68 * cm), line)
    canvas.restoreState()


def _build_pdf_lot_incident_block_final_v4(group: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> List[Any]:
    rows = [
        ("Lot", _fix_encoding(group.get("lot") or "SENSE LOT")),
        ("Check", _fix_encoding(group.get("check") or "-")),
        ("Descripció del check", _fix_encoding(_display_title(group.get("title") or group.get("check") or "-"))),
        ("Severitat", _fix_encoding(group.get("severity") or "-")),
        ("Termini dies", f"{group.get('termini_dies') if group.get('termini_dies') is not None else '-'}"),
    ]
    blocks: List[Any] = [_build_labeled_pdf_table_v2(rows, total_width, styles), Spacer(1, 0.08 * cm)]
    blocks.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(group.get('impacte') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Acció recomanada:</b> {html.escape(_fix_encoding(group.get('accio_recomanada') or '-'))}", styles["body"]))
    blocks.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(group.get('validacio_posterior') or '-'))}", styles["body"]))
    blocks.append(Spacer(1, 0.08 * cm))
    for schema_group in group.get("schemas") or []:
        object_names = ", ".join(_fix_encoding(item.get("nom") or "-") for item in (schema_group.get("objectes") or []))
        blocks.append(Paragraph(f"<b>Esquema:</b> {html.escape(_fix_encoding(schema_group.get('nom') or '-'))}", styles["body"]))
        if object_names:
            blocks.append(Paragraph(f"<b>Objectes:</b> {html.escape(object_names)}", styles["body"]))
        blocks.append(Spacer(1, 0.06 * cm))
    blocks.append(Spacer(1, 0.16 * cm))
    return blocks


def _build_post_crq_pdf_from_report_model_final_v4(profile: str, report: Dict[str, Any]) -> bytes:
    context = report.get("context") or {}
    report_model = report.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report) if _should_include_annex(report) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = next((candidate for candidate in [Path(_project_root()) / "portada.png", Path(_project_root()) / "assets" / "portada.png"] if candidate.exists()), None)
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover_final_v4(canvas, profile, generated_at, cover_path, report_model, context.get("time_filter") or {})),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
    ])
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    story.append(Paragraph("1. Índex", styles["heading"]))
    for entry in _report_operational_index_entries_v4(bool(annex_entries)):
        story.append(Paragraph(html.escape(entry), styles["body"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("2. Paràmetres d'execució", styles["heading"]))
    story.append(_build_labeled_pdf_table_v2(_report_model_parameters_rows_v2(report), doc.width, styles))
    enabled_checks = _build_enabled_checks_text_v2(report_model)
    if enabled_checks:
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph("Checks activats", styles["check_heading"]))
        for line in enabled_checks.split(", "):
            story.append(Paragraph(html.escape(line), styles["body"]))

    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("3. Resum executiu per lots", styles["heading"]))
    story.append(Paragraph("Aquest apartat resumeix, per a cada lot, les incidències detectades, els esquemes i objectes impactats, la prioritat i la primera acció recomanada.", styles["body"]))
    lot_rows = _build_lot_summary_rows_v2(report_model)
    if lot_rows:
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes", "Check afectat", "Descripció del check", "Prioritat", "Acció inicial"], lot_rows, doc.width, styles))
    else:
        story.append(Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))

    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("4. Incidències prioritzades per lot", styles["heading"]))
    lot_groups = report_model.get("lot_incident_groups") or []
    if lot_groups:
        for group in lot_groups:
            story.extend(_build_pdf_lot_incident_block_final_v4(group, styles, doc.width))
    else:
        story.append(Paragraph("No hi ha incidències prioritzades per lot en aquesta execució.", styles["body"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("5. Resultat detallat per check", styles["heading"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        story.append(Paragraph(f"{html.escape(str(section.get('check_id') or ''))} - {html.escape(_fix_encoding(_display_title(section.get('title'))))}", styles["check_heading"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {html.escape(_fix_encoding(section.get('criticality') or 'Baix'))}", styles["body"]))
        story.append(Paragraph(f"<b>Temps d'execució:</b> {html.escape(_humanize_duration_ms_v2(section.get('duration_ms') or 0))}", styles["body"]))
        story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(section.get('overview') or '-'))}", styles["body"]))
        if section.get("why_it_matters"):
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(section.get('why_it_matters')))}", styles["body"]))
        story.append(Paragraph(f"<b>Troballes:</b> {html.escape(str(section.get('finding_count') or 0))}", styles["body"]))
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))

    story.append(PageBreak())
    story.append(Paragraph("6. Observacions finals", styles["heading"]))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["check_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{html.escape(str(item.get('check_id') or '-'))}: {html.escape(_fix_encoding(item.get('error') or 'Error no detallat'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["check_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["check_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(html.escape(_fix_encoding(item)), styles["body"]))

    if annex_entries:
        story.append(PageBreak())
        story.append(Paragraph("7. Annex funcional dels checks", styles["heading"]))
        for entry in annex_entries:
            story.append(Paragraph(f"{html.escape(str(entry.get('check_id', '')))} - {html.escape(_fix_encoding(entry.get('title', '')))}", styles["check_heading"]))
            story.append(Paragraph(f"<b>Què detecta:</b> {html.escape(_fix_encoding(entry['que_detecta']))}", styles["body"]))
            story.append(Paragraph(f"<b>Per què és important:</b> {html.escape(_fix_encoding(entry['per_que_es_important']))}", styles["body"]))
            story.append(Paragraph(f"<b>Impacte sobre el lot:</b> {html.escape(_fix_encoding(entry['impacte_sobre_lot']))}", styles["body"]))
            story.append(Paragraph(f"<b>Com s'ha de revisar:</b> {html.escape(_fix_encoding(entry['com_revisar']))}", styles["body"]))
            story.append(Paragraph(f"<b>Com es pot corregir:</b> {html.escape(_fix_encoding(entry['com_corregir']))}", styles["body"]))
            story.append(Paragraph(f"<b>Limitacions o falsos positius:</b> {html.escape(_fix_encoding(entry['limitacions']))}", styles["body"]))
            story.append(Paragraph(f"<b>Dades que s'han de mostrar a la taula:</b> {html.escape(', '.join(_fix_encoding(column) for column in entry['columnes_taula_recomanades']) or '-')}", styles["body"]))
            story.append(Paragraph(f"<b>Validació posterior:</b> {html.escape(_fix_encoding(entry['validacio_posterior']))}", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))

    doc.build(story)
    return buffer.getvalue()


def _report_operational_index_entries_v5(include_annex: bool) -> List[str]:
    entries = [
        "1. Portada",
        "2. Índex",
        "3. Paràmetres d'execució",
        "4. Resum executiu per lots",
        "5. Incidències prioritzades per lot",
        "6. Resultat detallat per check",
        "7. Observacions finals",
    ]
    if include_annex:
        entries.append("8. Annex funcional dels checks")
    return entries


def _report_parameter_rows_v5(report: Dict[str, Any]) -> List[tuple[str, str]]:
    rows = []
    for label, value in _report_model_parameters_rows_v2(report):
        normalized_label = _fix_encoding(label)
        if normalized_label.lower().startswith("checks activats"):
            continue
        if _visible_report_value(value):
            rows.append((normalized_label, _fix_encoding(value)))
    return rows


def _report_lot_counts_rows_v5(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in report_model.get("lot_summary") or []:
        rows.append(
            {
                "Lot": item.get("lot") or "SENSE LOT",
                "Crítiques": item.get("critical") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
            }
        )
    return rows


def _report_check_lot_matrix_rows_v5(report_model: Dict[str, Any]) -> tuple[List[str], List[Dict[str, Any]]]:
    lot_summary = report_model.get("lot_summary") or []
    lots = [item.get("lot") or "SENSE LOT" for item in lot_summary]
    rows: List[Dict[str, Any]] = []
    for enabled_check in report_model.get("enabled_checks") or []:
        row = {"Check afectat": enabled_check.get("check_id") or "-"}
        affected_lots = {item.get("lot") or "SENSE LOT" for item in lot_summary if (enabled_check.get("check_id") or "-") in (item.get("checks") or [])}
        for lot in lots:
            row[lot] = "X" if lot in affected_lots else ""
        rows.append(row)
    return ["Check afectat", *lots], rows


def _post_crq_pdf_header_footer_final_v5(
    canvas,
    doc,
    profile: str,
    generated_at: str,
    footer_text: str,
    logo_path: Optional[Path],
    show_header: bool = True,
) -> None:
    canvas.saveState()
    width, height = doc.pagesize
    is_landscape = width > height
    page_margin = 0.7 * cm if is_landscape else doc.leftMargin
    left_margin = page_margin
    right_edge = width - page_margin
    top_y = height - 0.95 * cm
    footer_y = 0.75 * cm

    if show_header:
        canvas.setStrokeColor(PDF_BRAND_LINE)
        canvas.line(left_margin, top_y - 0.92 * cm, right_edge, top_y - 0.92 * cm)
        if logo_path and logo_path.exists():
            canvas.drawImage(
                str(logo_path),
                left_margin,
                top_y - 0.62 * cm,
                width=4.8 * cm,
                height=0.78 * cm,
                preserveAspectRatio=True,
                mask="auto",
            )

        bold_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
        regular_font = "OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
        canvas.setFont(bold_font, 9)
        canvas.setFillColor(PDF_BRAND_NAVY)
        canvas.drawRightString(right_edge, top_y, f"Auditoria Oracle {_fix_encoding(profile or '-')}")
        canvas.setFont(regular_font, 7.8)
        canvas.setFillColor(PDF_MUTED_TEXT)
        canvas.drawRightString(right_edge, top_y - 0.32 * cm, "Departament d'Educació i Formació Professional")
        canvas.drawRightString(right_edge, top_y - 0.62 * cm, f"Perfil: {_fix_encoding(profile)} · {_fix_encoding(generated_at)}")

    canvas.setStrokeColor(PDF_BRAND_LINE)
    canvas.line(left_margin, footer_y + 0.22 * cm, right_edge, footer_y + 0.22 * cm)
    canvas.setFont("OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 7.5)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(left_margin, footer_y, "Informe tècnic institucional")
    canvas.drawRightString(right_edge, footer_y, f"Pàgina {canvas.getPageNumber()} | {footer_text}")
    canvas.restoreState()








def _build_lot_headline_v6(group: Dict[str, Any], report_model: Dict[str, Any]) -> str:
    lot_name = str(group.get("lot") or "SENSE LOT")
    lot_summary = next((item for item in (report_model.get("lot_summary") or []) if (item.get("lot") or "SENSE LOT") == lot_name), {})
    critical = int(lot_summary.get("critical") or 0)
    medium = int(lot_summary.get("medium") or 0)
    low = int(lot_summary.get("low") or 0)
    return f"El lot {lot_name} presenta {critical} incidències crítiques, {medium} incidències mitjanes i {low} incidències baixes."


def _incident_object_table_row_v7(_schema_group: Dict[str, Any], objecte: Dict[str, Any]) -> Dict[str, Any]:
    object_name = (
        objecte.get("OBJECTE")
        or objecte.get("nom")
        or objecte.get("objecte")
        or objecte.get("OBJECT_NAME")
        or "-"
    )
    object_type = (
        objecte.get("TIPUS")
        or objecte.get("tipus")
        or objecte.get("OBJECT_TYPE")
        or "-"
    )
    technical_value = (
        objecte.get("DADA TÈCNICA")
        or objecte.get("DADA T?CNICA")
        or objecte.get("dada_tecnica")
        or objecte.get("OBSERVACIÓ")
        or objecte.get("OBSERVACI?")
        or objecte.get("observacio")
        or "-"
    )
    return {
        "OBJECTE": object_name,
        "TIPUS": object_type,
        "DADA TÈCNICA": technical_value,
    }


def _build_incident_objects_table_rows_v6(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for schema_group in group.get("schemas") or []:
        for objecte in schema_group.get("objectes") or []:
            rows.append(_incident_object_table_row_v7(schema_group, objecte))
    return rows


def generate_post_crq_zip_by_lots(profile: str, global_report: Dict[str, Any]) -> bytes:
    """
    Genera un fitxer ZIP que conté un PDF resum general i un PDF individual per cada lot.
    Aquesta funció reutilitza la lògica de generació de PDF existent filtrant el model global.
    """
    from src.api.post_crq_experimental_pdf import filter_post_crq_report_for_lot

    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Generar el PDF general (Resum consolidat)
        general_pdf_bytes = build_post_crq_pdf_report(profile, global_report)
        zf.writestr("00_resum_general.pdf", general_pdf_bytes)
        
        # 2. Identificar els lots únics del resum executiu
        # Reutilitzem el report_model si existeix, altrament els resultats detallats
        report_model = global_report.get("report_model") or {}
        lot_summary = report_model.get("lot_summary") or []
        
        lots = []
        if lot_summary:
            lots = [str(item.get("lot") or "SENSE_LOT") for item in lot_summary]
        else:
            # Si no hi ha lot_summary, intentem extreure lots dels resultats detallats
            all_lots = set()
            for check_result in global_report.get("results_by_check") or []:
                for row in check_result.get("rows") or []:
                    lot_val = row.get("Lot") or row.get("LOT")
                    if lot_val:
                        all_lots.add(str(lot_val))
            lots = sorted(list(all_lots))

        # 3. Generar un PDF per cada lot
        for i, lot_name in enumerate(lots, start=1):
            # Filtrem el model global per a aquest lot concret
            # Reutilitzem la funció de filtratge experimental que ja existeix
            lot_report = filter_post_crq_report_for_lot(global_report, lot_name)
            
            # Generem el PDF amb el model filtrat
            lot_pdf_bytes = build_post_crq_pdf_report(profile, lot_report)
            
            # Nom del fitxer amb indexador per mantenir l'ordre al ZIP
            safe_lot_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", lot_name)
            file_name = f"{i:02d}_lot_{safe_lot_name}.pdf"
            zf.writestr(file_name, lot_pdf_bytes)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def _post_crq_count_label(count: Any, singular: str, plural: str) -> str:
    try:
        normalized = int(count or 0)
    except (TypeError, ValueError):
        normalized = 0
    return f"{normalized} {singular if normalized == 1 else plural}"


def _post_crq_append_sentence(base_text: Any, extra_text: Any, prefix: str) -> str:
    base = _normalize_text(base_text)
    extra = _normalize_text(extra_text)
    if not extra:
        return base or "-"
    if not base:
        return f"{prefix}{extra}"
    return f"{base} {prefix}{extra}"


def _build_annex_entries_v2(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    catalog = load_check_explanation_catalog()
    executed_checks = _sort_check_dicts(report.get("executed_checks") or [])
    entries: List[Dict[str, Any]] = []
    for item in executed_checks:
        check_id = str(item.get("check_id") or "").strip()
        if not check_id:
            continue
        guidance = catalog.get(check_id, {})
        table_fields_list = [_fix_encoding(col) for col in (guidance.get("columnes_taula_recomanades") or [])]
        com_revisar = _fix_encoding(guidance.get("com_revisar") or "Revisar la incidència amb el detall tècnic del check.")
        validacio = _fix_encoding(guidance.get("validacio_posterior") or "Reexecutar el check després de la correcció.")
        limitacions = _fix_encoding(guidance.get("limitacions") or "Sense limitacions documentades.")

        entries.append(
            {
                "check_id": check_id,
                "title": _fix_encoding(_display_title(item.get("title") or guidance.get("title") or check_id)),
                "severitat": _fix_encoding(item.get("severitat") or item.get("criticitat") or "N/A"),
                "que_detecta": _fix_encoding(guidance.get("que_detecta") or "Sense explicació funcional disponible."),
                "per_que_es_important": _fix_encoding(guidance.get("per_que_es_important") or "Sense context d'impacte disponible."),
                "impacte_sobre_lot": _fix_encoding(guidance.get("impacte_sobre_lot") or "Impacte sobre el lot pendent de concretar."),
                "com_revisar": com_revisar,
                "com_corregir": _fix_encoding(guidance.get("com_corregir") or "Aplicar la correcció estructural recomanada."),
                "limitacions": limitacions,
                "columnes_taula_recomanades": table_fields_list,
                "validacio_posterior": validacio,
            }
        )
    return entries


def _report_operational_cover_summary_v4(report_model: Dict[str, Any]) -> str:
    lot_summary = report_model.get("lot_summary") or []
    lots_with_findings = len(lot_summary)
    critical_lots = sum(1 for item in lot_summary if (item.get("critical") or 0) > 0)
    return (
        f"{_post_crq_count_label(lots_with_findings, 'lot amb incidència', 'lots amb incidències')}; "
        f"{_post_crq_count_label(critical_lots, 'lot amb incidència crítica', 'lots amb incidències crítiques')}"
    )


def _markdown_lot_incident_group_lines_v2(group: Dict[str, Any]) -> List[str]:
    lines = [
        f"### Lot {group.get('lot') or 'SENSE LOT'} — {group.get('check') or '-'}",
        "",
        f"- **Descripció del check:** {_fix_encoding(_display_title(group.get('title') or group.get('check') or '-'))}",
        f"- **Severitat:** {_fix_encoding(group.get('severity') or '-')}",
        f"- **Termini orientatiu:** {group.get('termini_dies') if group.get('termini_dies') is not None else '-'} dies",
        "",
        f"**Impacte sobre el lot:** {_fix_encoding(group.get('impacte') or '-')}",
        "",
        f"**Acció recomanada:** {_fix_encoding(group.get('accio_recomanada') or '-')}",
        "",
        f"**Validació posterior:** {_fix_encoding(group.get('validacio_posterior') or '-')}",
    ]
    limitacions = _normalize_text(group.get("limitacions"))
    if limitacions:
        lines.extend(["", f"**Limitacions i matisos:** {_fix_encoding(limitacions)}"])
    lines.extend(["", "**Esquemes afectats:**"])
    for schema_group in group.get("schemas") or []:
        lines.append(f"- **{_fix_encoding(schema_group.get('nom') or '-')}** ({schema_group.get('object_count') or 0} objectes)")
        object_rows = []
        for objecte in schema_group.get("objectes") or []:
            object_rows.append(
                {key: _fix_encoding(value) for key, value in _incident_object_table_row_v7(schema_group, objecte).items()}
            )
        if object_rows:
            lines.append("")
            lines.append(_rows_to_markdown_table(["OBJECTE", "TIPUS", "DADA TÈCNICA"], object_rows, limit=None))
            lines.append("")
    return lines


def _build_lot_headline_v6(group: Dict[str, Any], report_model: Dict[str, Any]) -> str:
    lot_name = str(group.get("lot") or "SENSE LOT")
    lot_summary = next((item for item in (report_model.get("lot_summary") or []) if (item.get("lot") or "SENSE LOT") == lot_name), {})
    critical = int(lot_summary.get("critical") or 0)
    medium = int(lot_summary.get("medium") or 0)
    low = int(lot_summary.get("low") or 0)
    return (
        f"El lot {lot_name} presenta "
        f"{_post_crq_count_label(critical, 'incidència crítica', 'incidències crítiques')}, "
        f"{_post_crq_count_label(medium, 'incidència mitjana', 'incidències mitjanes')} i "
        f"{_post_crq_count_label(low, 'incidència baixa', 'incidències baixes')}."
    )


def _build_pdf_lot_incident_block_v7(
    group: Dict[str, Any],
    report_model: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
    total_width: float,
    *,
    lot_index: int,
    severity_index: int,
    incident_index: int,
) -> List[Any]:
    severity_text = _fix_encoding(group.get("severity") or "-")
    deadline_text = _orientative_deadline_text(group.get("termini_dies"), group.get("severity"))

    def _section_heading(label: str, code: str) -> Paragraph:
        return safe_pdf_markup_paragraph(
            f'<a name="{_lot_incident_section_anchor_name(lot_index, severity_index, incident_index, code)}"/>{safe_pdf_text(label)}',
            styles["subsection_heading"],
            fallback_text=label,
        )

    def _section_block(label: str, code: str, body_value: Any, body_style_key: str = "body") -> KeepTogether:
        return KeepTogether(
            [
                _section_heading(label, code),
                safe_pdf_paragraph(body_value or "-", styles[body_style_key]),
            ]
        )

    blocks: List[Any] = [
        safe_pdf_markup_paragraph(
            (
                f"<b>Check:</b> {safe_pdf_text(group.get('check') or '-')} | "
                f"<b>Severitat:</b> {safe_pdf_text(severity_text)} | "
                f"<b>Termini orientatiu:</b> {safe_pdf_text(deadline_text)}"
            ),
            styles["meta"],
            fallback_text=f"Check: {group.get('check') or '-'} | Severitat: {severity_text} | Termini orientatiu: {deadline_text}",
        ),
        Spacer(1, 0.08 * cm),
        _section_block("a) Què s'ha detectat", "a", group.get("description") or "-"),
        Spacer(1, 0.05 * cm),
        _section_block("b) Impacte", "b", group.get("impacte") or "-"),
        Spacer(1, 0.05 * cm),
        _section_heading("c) Esquemes afectats", "c"),
    ]
    for schema_group in group.get("schemas") or []:
        blocks.append(safe_pdf_bullet_paragraph(f"{_fix_encoding(schema_group.get('nom') or '-')} ({schema_group.get('object_count') or 0} objectes)", styles["body"]))
    rows = _build_incident_objects_table_rows_v6(group)
    if rows:
        blocks.extend([
            Spacer(1, 0.12 * cm),
            _section_heading("d) Objectes afectats", "d"),
            _build_post_crq_table(list(rows[0].keys()), rows, total_width, styles, table_kind="object_table"),
        ])
    blocks.extend([
        Spacer(1, 0.14 * cm),
        _section_block("e) Acció requerida", "e", group.get("accio_recomanada") or "-"),
        Spacer(1, 0.05 * cm),
        _section_block("f) Validació posterior", "f", group.get("validacio_posterior") or "-"),
    ])
    if _normalize_text(group.get("limitacions")):
        blocks.extend([
            Spacer(1, 0.05 * cm),
            _section_block("g) Limitacions i matisos", "g", group.get("limitacions") or "-"),
        ])
    blocks.append(Spacer(1, 0.2 * cm))
    return blocks


_build_post_crq_pdf_from_report_model_final_v7_base = _build_post_crq_pdf_from_report_model_final_v7


def _build_post_crq_pdf_from_report_model_final_v7(profile: str, report: Dict[str, Any]) -> bytes:
    report_data = copy.deepcopy(report)
    catalog = load_check_explanation_catalog()
    report_model = report_data.get("report_model") or {}

    for group in report_model.get("lot_incident_groups") or []:
        check_id = str(group.get("check") or "").strip()
        guidance = catalog.get(check_id, {})
        if guidance and not _normalize_text(group.get("limitacions")):
            group["limitacions"] = _fix_encoding(guidance.get("limitacions") or "")

    return _build_post_crq_pdf_from_report_model_final_v7_base(profile, report_data)


def _post_crq_pdf_cover_final_v7(canvas, profile: str, generated_at: str, cover_path: Path | None, report_model: Dict[str, Any], time_filter: Dict[str, Any]) -> None:
    width, height = A4
    canvas.saveState()
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFillColor(rl_colors.white)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.rect(0, height - (7.8 * cm), width, 7.8 * cm, fill=1, stroke=0)
    canvas.setFillColor(PDF_BRAND_BLUE)
    canvas.rect(0, height - (7.8 * cm), width, 0.42 * cm, fill=1, stroke=0)

    if cover_path and cover_path.exists():
        canvas.saveState()
        canvas.setFillAlpha(0.12)
        canvas.drawImage(
            str(cover_path),
            width - (8.0 * cm),
            height - (6.6 * cm),
            width=6.6 * cm,
            height=4.9 * cm,
            preserveAspectRatio=True,
            anchor="n",
            mask="auto",
        )
        canvas.restoreState()

    panel_x = 1.35 * cm
    panel_y = 6.95 * cm
    panel_width = width - (2.7 * cm)
    panel_height = 10.35 * cm
    canvas.setFillColor(rl_colors.white)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 16, fill=1, stroke=0)
    canvas.setStrokeColor(PDF_BRAND_LINE)
    canvas.setLineWidth(0.9)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 16, fill=0, stroke=1)

    canvas.setFillColor(PDF_BRAND_BLUE)
    canvas.setFont(title_font, 10.2)
    canvas.drawString(panel_x + 0.9 * cm, panel_y + panel_height - 1.15 * cm, "AUDITORIA ORACLE · VALIDACIÓ POST-CRQ")
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.setFont(title_font, 23)
    canvas.drawString(panel_x + 0.9 * cm, panel_y + panel_height - 2.1 * cm, "Informe d'auditoria post-CRQ")
    _draw_canvas_wrapped_text(
        canvas,
        "Informe institucional de validació tècnica per lots, amb incidències prioritzades i detall operatiu dels checks executats.",
        panel_x + 0.9 * cm,
        panel_y + panel_height - 2.9 * cm,
        panel_width - (1.8 * cm),
        body_font,
        11.0,
        0.52 * cm,
        PDF_MUTED_TEXT,
    )

    meta_y = panel_y + 5.3 * cm
    left_x = panel_x + 0.9 * cm
    right_x = panel_x + (panel_width / 2) + 0.15 * cm
    meta_width = (panel_width / 2) - 1.05 * cm
    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, meta_y, "Perfil")
    canvas.drawString(right_x, meta_y, "Data de generació")
    canvas.setFont(body_font, 10.2)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(left_x, meta_y - 0.38 * cm, _fix_encoding(profile or "-"))
    canvas.drawString(right_x, meta_y - 0.38 * cm, _fix_encoding(generated_at or "-"))

    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, meta_y - 0.95 * cm, "Finestra auditada")
    canvas.drawString(right_x, meta_y - 0.95 * cm, "Període aplicat")
    _draw_canvas_wrapped_text(
        canvas,
        _resolve_report_time_window_label_final_v3(time_filter),
        left_x,
        meta_y - 1.33 * cm,
        meta_width,
        body_font,
        10.0,
        0.47 * cm,
        PDF_MUTED_TEXT,
    )
    _draw_canvas_wrapped_text(
        canvas,
        _fix_encoding(_display_period_label(time_filter)),
        right_x,
        meta_y - 1.33 * cm,
        meta_width,
        body_font,
        10.0,
        0.47 * cm,
        PDF_MUTED_TEXT,
    )

    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, panel_y + 3.15 * cm, "Resum global")
    _draw_canvas_wrapped_text(
        canvas,
        _report_operational_cover_summary_v4(report_model),
        left_x,
        panel_y + 2.78 * cm,
        panel_width - (1.8 * cm),
        body_font,
        10.2,
        0.5 * cm,
        PDF_MUTED_TEXT,
    )

    metric_y = panel_y + 0.92 * cm
    metric_width = (panel_width - (1.8 * cm) - (3 * 0.34 * cm)) / 4
    for index, (label, value) in enumerate(_report_operational_cover_metrics_v7(report_model)):
        current_x = left_x + index * (metric_width + 0.34 * cm)
        canvas.setFillColor(PDF_SOFT_ALT if index % 2 == 0 else PDF_SOFT_FILL)
        canvas.roundRect(current_x, metric_y, metric_width, 1.72 * cm, 10, fill=1, stroke=0)
        canvas.setStrokeColor(PDF_BRAND_LINE)
        canvas.setLineWidth(0.45)
        canvas.roundRect(current_x, metric_y, metric_width, 1.72 * cm, 10, fill=0, stroke=1)
        canvas.setFillColor(PDF_BRAND_NAVY)
        canvas.setFont(title_font, 16)
        canvas.drawString(current_x + 0.22 * cm, metric_y + 1.0 * cm, value)
        _draw_canvas_wrapped_text(
            canvas,
            label,
            current_x + 0.22 * cm,
            metric_y + 0.72 * cm,
            metric_width - 0.34 * cm,
            body_font,
            8.6,
            0.38 * cm,
            PDF_MUTED_TEXT,
        )

    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.rect(0, 0.84 * cm, width, 0.18 * cm, fill=1, stroke=0)
    canvas.setFont(body_font, 8.2)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(1.35 * cm, 0.38 * cm, "Departament d'Educació i Formació Professional · Informe generat automàticament")
    canvas.restoreState()


def _build_post_crq_pdf_from_report_model_final_v7(profile: str, report: Dict[str, Any]) -> bytes:
    report_data = _prepare_post_crq_report_for_final_v7(report)
    context = report_data.get("context") or {}
    report_model = report_data.get("report_model") or {}
    annex_entries = _build_annex_entries_v2(report_data) if _should_include_annex(report_data) else []
    _register_post_crq_pdf_fonts()
    generated_at = str((report_model.get("execution_parameters") or {}).get("generated_at") or context.get("generated_at") or "")
    cover_path = _resolve_post_crq_cover_path()
    logo_path = next((candidate for candidate in [Path(_project_root()) / "logo" / "Logo-Departament-Educacio.png"] if candidate.exists()), None)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.9 * cm, bottomMargin=1.4 * cm)
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_pagesize = landscape(A4)
    landscape_margin = 0.85 * cm
    landscape_frame = Frame(landscape_margin, landscape_margin, landscape_pagesize[0] - (2 * landscape_margin), landscape_pagesize[1] - (2 * landscape_margin), id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_cover_final_v7(canvas, profile, generated_at, cover_path, report_model, context.get("time_filter") or {})),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer_final_v5(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_pagesize, onPage=lambda canvas, current_doc: _post_crq_pdf_header_footer_final_v5(canvas, current_doc, profile, generated_at, "GESIN @ 2026", logo_path, show_header=True)),
    ])
    styles = _build_post_crq_paragraph_styles()
    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    usable_width = doc.width if hasattr(doc, "width") else (A4[0] - doc.leftMargin - doc.rightMargin)
    toc_entries = _build_post_crq_dynamic_toc_entries(report_model, bool(annex_entries))
    story.append(_centered_heading_block("Índex", "index", styles, usable_width))
    story.append(_build_post_crq_toc_block(toc_entries, styles, usable_width))

    enabled_checks = _sort_check_dicts(report_model.get("enabled_checks") or [])
    detail_anchorable_checks = {
        str(section.get("check_id") or "").strip()
        for section in (report_model.get("detail_sections") or [])
        if str(section.get("check_id") or "").strip()
    }
    if enabled_checks:
        story.append(Spacer(1, 0.55 * cm))
        story.append(
            _build_check_index_block(
                enabled_checks,
                styles,
                usable_width,
                anchor_builder=lambda check_id: _detail_anchor_name(check_id) if str(check_id or "").strip() in detail_anchorable_checks else None,
            )
        )

    story.append(PageBreak())
    story.append(_linked_heading("1. Context de l'auditoria", "context", styles))
    parameter_rows = [(label, value) for label, value in _report_parameter_rows_v5(report_data) if label != "Checks activats"]
    story.append(_build_labeled_pdf_table_v2([(safe_pdf_text(label), safe_pdf_text(value)) for label, value in parameter_rows], usable_width, styles, table_kind="label_table_large"))

    story.append(Spacer(1, 0.28 * cm))
    story.append(_linked_heading("2. Resum executiu post-CRQ", "resum", styles))
    story.append(safe_pdf_paragraph("Aquest apartat resumeix, per a cada lot, el volum d'incidències detectades i la seva prioritat per iniciar la correcció.", styles["lead"]))
    lot_rows = _report_lot_counts_rows_v5(report_model)
    if lot_rows:
        story.append(_build_post_crq_table(["Lot", "Crítiques", "Mitjanes", "Baixes"], lot_rows, usable_width, styles, table_kind="summary_table"))
    else:
        story.append(safe_pdf_paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"]))

    story.append(PageBreak())
    story.append(_linked_heading("3. Incidències prioritzades per criticitat i lot", "incidencies", styles))
    lot_blocks = _group_lot_incidents_by_lot_v7(report_model)
    if not lot_blocks:
        story.append(safe_pdf_paragraph("No hi ha incidències prioritzades per lots en aquesta execució.", styles["body"]))
    for lot_index, (lot_name, severity_blocks) in enumerate(lot_blocks, start=1):
        if lot_index > 1:
            story.append(PageBreak())
        lot_heading = f"3.{lot_index} LOT {_fix_encoding(lot_name)}"
        story.append(
            safe_pdf_markup_paragraph(
                f'<a name="{_lot_anchor_name(lot_index)}"/>{safe_pdf_text(lot_heading)}',
                styles["check_heading"],
                fallback_text=lot_heading,
            )
        )
        story.append(Spacer(1, 0.08 * cm))
        story.append(safe_pdf_paragraph(_build_lot_headline_v6({"lot": lot_name}, report_model), styles["lead"]))
        story.append(Spacer(1, 0.12 * cm))
        ordered_severity_blocks = sorted(severity_blocks, key=lambda item: _criticality_rank(item[0]), reverse=True)
        for severity_index, (severity_key, _, groups) in enumerate(ordered_severity_blocks, start=1):
            section_title = {
                "CRITIC": "Incidències crítiques",
                "MITJA": "Incidències mitjanes",
                "BAIX": "Incidències baixes",
            }.get(severity_key, "Incidències")
            severity_heading = f"3.{lot_index}.{severity_index} {section_title}"
            severity_color = _severity_badge_hex(severity_key)
            story.append(
                safe_pdf_markup_paragraph(
                    f'<a name="{_lot_severity_anchor_name(lot_index, severity_index)}"/><font color="{severity_color}">{safe_pdf_text(severity_heading)}</font>',
                    styles["severity_heading"],
                    fallback_text=severity_heading,
                )
            )
            story.append(Spacer(1, 0.06 * cm))
            for incident_index, group in enumerate(groups, start=1):
                incident_heading = (
                    f"3.{lot_index}.{severity_index}.{_lettered_index(incident_index)}.- "
                    f"{_fix_encoding(_display_title(group.get('title') or group.get('check') or '-'))}"
                )
                story.append(
                    safe_pdf_markup_paragraph(
                        f'<a name="{_lot_incident_anchor_name(lot_index, severity_index, incident_index)}"/>{safe_pdf_text(incident_heading)}',
                        styles["incident_heading"],
                        fallback_text=incident_heading,
                    )
                )
                story.extend(
                    _build_pdf_lot_incident_block_v7(
                        group,
                        report_model,
                        styles,
                        usable_width,
                        lot_index=lot_index,
                        severity_index=severity_index,
                        incident_index=incident_index,
                    )
                )
            story.append(Spacer(1, 0.1 * cm))

    story.append(Spacer(1, 0.26 * cm))
    story.append(_linked_heading("4. Resultat detallat per check", "detall", styles))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        detail_check_id = str(section.get("check_id") or "").strip()
        detail_title = _fix_encoding(_display_title(section.get("title") or detail_check_id))
        story.append(
            safe_pdf_markup_paragraph(
                f'<a name="{_detail_anchor_name(detail_check_id)}"/><b>{safe_pdf_text(detail_check_id)}</b> — {safe_pdf_text(detail_title)}',
                styles["check_heading"],
                fallback_text=f"{detail_check_id} - {detail_title}",
            )
        )
        story.append(safe_pdf_label_value_paragraph("Temps d'execució", _humanize_duration_ms_v2(section.get("duration_ms") or 0), styles["body"]))

        active_cols = section.get("columns") or []
        active_rows = section.get("rows") or []
        if detail_check_id.upper() == "CHECK_11":
            exclude_keywords = ["IA", "EXPLICACIO", "RECOMANACIO", "CLASSIFICACIO", "CONFIANCA", "ESTAT_ANALISI", "SEVERITAT", "CRITICITAT"]
            keep_indices = []
            for index, column in enumerate(active_cols):
                column_upper = str(column).upper()
                if not any(keyword in column_upper for keyword in exclude_keywords):
                    keep_indices.append(index)
            active_cols = [active_cols[index] for index in keep_indices]
            filtered_rows = []
            for row in active_rows:
                if isinstance(row, (list, tuple)):
                    filtered_rows.append([row[index] for index in keep_indices if index < len(row)])
                else:
                    filtered_rows.append(row)
            active_rows = filtered_rows

        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(_build_post_crq_table(active_cols, active_rows, current_width, styles, table_kind="detail_table"))
        story.append(NextPageTemplate("portrait"))

    story.append(PageBreak())
    story.append(_linked_heading("5. Observacions finals", "observacions", styles))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["subsection_heading"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(safe_pdf_paragraph(f"{item.get('check_id') or '-'}: {item.get('error') or 'Error no detallat'}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["subsection_heading"]))
        for item in final_observations.get("warnings") or []:
            story.append(safe_pdf_bullet_paragraph(item, styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["subsection_heading"]))
        for item in final_observations.get("next_steps") or []:
            story.append(safe_pdf_bullet_paragraph(item, styles["body"]))

    if annex_entries:
        story.append(PageBreak())
        story.append(_linked_heading("6. Annex A — anàlisi funcional de cada check", "annex", styles))
        story.append(Spacer(1, 0.2 * cm))
        for entry_index, entry in enumerate(annex_entries, start=1):
            if entry_index > 1:
                story.append(PageBreak())
            table_fields = ", ".join(entry.get("columnes_taula_recomanades") or [])
            story.append(
                safe_pdf_markup_paragraph(
                    _md_to_pdf_tags(f"<b>{_safe_xml(entry['check_id'])} — {_safe_xml(entry['title'])}</b>"),
                    styles["card_title"],
                    fallback_text=f"{entry['check_id']} — {entry['title']}",
                )
            )
            annex_items = [
                ("Què detecta", entry.get("que_detecta") or "-"),
                ("Per què és important", entry.get("per_que_es_important") or "-"),
                ("Impacte sobre el lot", entry.get("impacte_sobre_lot") or "-"),
                ("Com revisar", entry.get("com_revisar") or "-"),
                ("Com corregir", entry.get("com_corregir") or "-"),
                ("Limitacions i matisos", entry.get("limitacions") or "-"),
                ("Dades recomanades a la taula", table_fields or "-"),
                ("Validació posterior", entry.get("validacio_posterior") or "-"),
            ]

            for label, value in annex_items:
                story.append(
                    safe_pdf_markup_paragraph(
                        _md_to_pdf_tags(
                            f"<font color='{PDF_BRAND_NAVY.hexval()}'><b>{_safe_xml(label)}:</b></font> {_safe_xml(value)}"
                        ),
                        styles["annex_body"],
                        fallback_text=f"{label}: {value}",
                    )
                )

    doc.build(story)
    return buffer.getvalue()


def _post_crq_has_check(report_model: Dict[str, Any], check_ids: set[str]) -> bool:
    group_checks = {
        str(item.get("check") or "").strip().upper()
        for item in (report_model.get("lot_incident_groups") or [])
        if str(item.get("check") or "").strip()
    }
    return bool(group_checks & check_ids)


def _normalize_post_crq_text_key(value: Any) -> str:
    return _normalize_text(value).casefold()


def _is_generic_post_crq_warning(value: Any) -> bool:
    normalized = _normalize_post_crq_text_key(value)
    generic_fragments = (
        "no s'ha detectat cap bloqueig",
        "acumulació de males pràctiques",
        "acumulacio de males practiques",
    )
    return not normalized or any(fragment in normalized for fragment in generic_fragments)


def _build_contextual_post_crq_warnings(report_model: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    lot_summary = report_model.get("lot_summary") or []
    ranked_lots = sorted(
        (
            {
                "lot": str(item.get("lot") or "SENSE LOT"),
                "critical": int(item.get("critical") or 0),
                "medium": int(item.get("medium") or 0),
                "low": int(item.get("low") or 0),
                "affected_objects": int(item.get("affected_objects") or 0),
                "checks": [str(check).strip().upper() for check in (item.get("checks") or []) if str(check).strip()],
            }
            for item in lot_summary
        ),
        key=lambda item: (
            item["critical"],
            item["medium"],
            item["low"],
            item["affected_objects"],
        ),
        reverse=True,
    )
    dominant_lot = ranked_lots[0] if ranked_lots else None
    if dominant_lot and (dominant_lot["critical"] or dominant_lot["medium"] or dominant_lot["low"]):
        total_findings = dominant_lot["critical"] + dominant_lot["medium"] + dominant_lot["low"]
        warnings.append(
            f"El lot {dominant_lot['lot']} concentra {total_findings} incidències i {dominant_lot['affected_objects']} objectes afectats; convé prioritzar-lo perquè acumula el gruix del risc pendent."
        )
    if _post_crq_has_check(report_model, {"CHECK_01", "CHECK_04", "CHECK_05"}):
        warnings.append(
            "Es mantenen incidències que poden afectar la integritat i la referencialitat de les dades; convé resoldre-les abans de donar per tancada la validació del canvi."
        )
    if _post_crq_has_check(report_model, {"CHECK_07"}):
        warnings.append(
            "Hi ha objectes invàlids recents que requereixen recompilació i comprovació dirigida segons el tipus d'objecte, perquè l'impacte no és equivalent en PL/SQL, vistes o materialized views."
        )
    if _post_crq_has_check(report_model, {"CHECK_02", "CHECK_03", "CHECK_06", "CHECK_08", "CHECK_10", "CHECK_11", "CHECK_12"}):
        warnings.append(
            "També es mantenen riscos de rendiment, mantenibilitat o traçabilitat que no bloquegen necessàriament el desplegament, però sí que poden degradar l'operació o el diagnòstic posterior."
        )
    if _post_crq_has_check(report_model, {"CHECK_11"}):
        warnings.append(
            "El CHECK_11 continua requerint una lectura prudent: la implementació efectiva del control és més estreta que la descripció funcional històrica i qualsevol conclusió fora del patró LOOP/FOR + DML s'ha de validar manualment."
        )
    if _post_crq_has_check(report_model, {"CHECK_08", "CHECK_12"}):
        warnings.append(
            "Hi ha controls que demanen contrast funcional addicional abans de decidir la correcció definitiva: `CHECK_08` per validar el domini real de les dades i `CHECK_12` per confirmar si el volum i la freqüència justifiquen una refactorització bulk."
        )
    return warnings


def _build_contextual_post_crq_next_steps(report_model: Dict[str, Any]) -> List[str]:
    steps: List[str] = []
    lot_summary = report_model.get("lot_summary") or []
    ranked_lots = sorted(
        (
            {
                "lot": str(item.get("lot") or "SENSE LOT"),
                "critical": int(item.get("critical") or 0),
                "medium": int(item.get("medium") or 0),
                "low": int(item.get("low") or 0),
                "affected_objects": int(item.get("affected_objects") or 0),
            }
            for item in lot_summary
        ),
        key=lambda item: (
            item["critical"],
            item["medium"],
            item["low"],
            item["affected_objects"],
        ),
        reverse=True,
    )
    dominant_lot = ranked_lots[0] if ranked_lots else None
    if dominant_lot and (dominant_lot["critical"] or dominant_lot["medium"] or dominant_lot["low"]):
        steps.append(
            f"Concentrar primer la regularització al lot {dominant_lot['lot']}, perquè és el que acumula més incidències i més objectes afectats en aquesta execució."
        )
    if _post_crq_has_check(report_model, {"CHECK_01", "CHECK_04", "CHECK_05"}):
        steps.append(
            "Prioritzar primer les incidències d'integritat i referencialitat que poden permetre dades inconsistents, duplicades o òrfenes abans del següent pas d'entorn."
        )
    if _post_crq_has_check(report_model, {"CHECK_07"}):
        steps.append(
            "Regularitzar després els objectes invàlids i confirmar-ne la compilació, execució o refresh segons el tipus d'objecte afectat."
        )
    if _post_crq_has_check(report_model, {"CHECK_02", "CHECK_03", "CHECK_06", "CHECK_08", "CHECK_10", "CHECK_11", "CHECK_12"}):
        steps.append(
            "Planificar tot seguit la correcció dels riscos de rendiment, traçabilitat i mantenibilitat, i reexecutar només els checks afectats amb validació funcional o tècnica proporcional al risc."
        )
    if _post_crq_has_check(report_model, {"CHECK_11"}):
        steps.append(
            "Completar una validació manual específica de les troballes de `CHECK_11` per distingir els casos realment fila a fila dels falsos positius per proximitat i per no atribuir al control patrons que la SQL actual no cobreix."
        )
    if _post_crq_has_check(report_model, {"CHECK_08"}):
        steps.append(
            "Contrastar amb l'equip funcional les columnes detectades a `CHECK_08` abans de restringir-ne la definició, especialment si intervenen en integracions, càlculs o interfícies externes."
        )
    if _post_crq_has_check(report_model, {"CHECK_12"}):
        steps.append(
            "Valorar els candidats de `CHECK_12` amb volum, freqüència i finestra operativa reals abans d'abordar una refactorització `BULK COLLECT`/`FORALL`."
        )
    if not steps:
        steps.append("Reexecutar els checks afectats després de la correcció i completar la validació funcional abans del següent pas d'entorn.")
    return steps


def _normalize_post_crq_final_observations_v2(report_model: Dict[str, Any]) -> Dict[str, Any]:
    final_observations = copy.deepcopy(report_model.get("final_observations") or {})
    blocking_errors = []
    for item in final_observations.get("blocking_errors") or []:
        blocking_errors.append(
            {
                "check_id": _fix_encoding(item.get("check_id") or "-"),
                "error": _fix_encoding(item.get("error") or "Error no detallat."),
            }
        )

    original_warnings = [_fix_encoding(item) for item in (final_observations.get("warnings") or []) if _normalize_text(item)]
    preserved_warnings = [item for item in original_warnings if not _is_generic_post_crq_warning(item)]
    contextual_warnings = _build_contextual_post_crq_warnings(report_model)
    warnings = contextual_warnings + [item for item in preserved_warnings if item not in contextual_warnings]
    next_steps = _build_contextual_post_crq_next_steps(report_model)

    return {
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "next_steps": next_steps,
    }


def _post_crq_should_replace_group_text(current_value: Any, *, minimum_length: int, generic_fragments: tuple[str, ...]) -> bool:
    normalized = _normalize_text(current_value)
    if not normalized:
        return True
    if len(normalized) < minimum_length:
        return True
    lowered = normalized.casefold()
    return any(fragment in lowered for fragment in generic_fragments)


def _prepare_post_crq_report_for_final_v7(report: Dict[str, Any]) -> Dict[str, Any]:
    report_data = copy.deepcopy(report)
    catalog = load_check_explanation_catalog()
    report_model = report_data.get("report_model") or {}
    target_checks = {"CHECK_01", "CHECK_02", "CHECK_03", "CHECK_06", "CHECK_07", "CHECK_08", "CHECK_10", "CHECK_11", "CHECK_12"}

    for item in report_data.get("executed_checks") or []:
        check_id = str(item.get("check_id") or "").strip().upper()
        guidance = catalog.get(check_id, {})
        if guidance.get("title"):
            item["title"] = _fix_encoding(guidance["title"])

    for item in report_data.get("results_by_check") or []:
        check_id = str(item.get("check_id") or "").strip().upper()
        guidance = catalog.get(check_id, {})
        if guidance.get("title"):
            item["title"] = _fix_encoding(guidance["title"])

    for item in report_model.get("enabled_checks") or []:
        check_id = str(item.get("check_id") or "").strip().upper()
        guidance = catalog.get(check_id, {})
        if guidance.get("title"):
            item["title"] = _fix_encoding(guidance["title"])

    for section in report_model.get("detail_sections") or []:
        check_id = str(section.get("check_id") or "").strip().upper()
        guidance = catalog.get(check_id, {})
        if guidance.get("title"):
            section["title"] = _fix_encoding(guidance["title"])
        if target_checks and guidance.get("que_detecta") and _post_crq_should_replace_group_text(
            section.get("overview"),
            minimum_length=90,
            generic_fragments=("descripció extensa", "pot afectar", "males pràctiques"),
        ):
            section["overview"] = _fix_encoding(guidance.get("que_detecta") or section.get("overview") or "-")

    for group in report_model.get("lot_incident_groups") or []:
        check_id = str(group.get("check") or "").strip().upper()
        guidance = catalog.get(check_id, {})
        if not guidance:
            continue
        if guidance.get("title"):
            group["title"] = _fix_encoding(guidance.get("title"))
        if check_id in target_checks and _post_crq_should_replace_group_text(
            group.get("description"),
            minimum_length=90,
            generic_fragments=("pot afectar", "pot comprometre l'estabilitat operativa"),
        ):
            group["description"] = _fix_encoding(guidance.get("que_detecta") or group.get("description") or "-")
        if check_id in target_checks and _post_crq_should_replace_group_text(
            group.get("impacte"),
            minimum_length=85,
            generic_fragments=("pot afectar", "pot comprometre l'estabilitat operativa", "pot retardar el lliurament"),
        ):
            group["impacte"] = _fix_encoding(guidance.get("impacte_sobre_lot") or group.get("impacte") or "-")
        if check_id in target_checks and _post_crq_should_replace_group_text(
            group.get("accio_recomanada"),
            minimum_length=80,
            generic_fragments=("cal reexecutar", "cal revisar", "corregir el codi"),
        ):
            group["accio_recomanada"] = _fix_encoding(guidance.get("com_corregir") or group.get("accio_recomanada") or "-")
        if check_id in target_checks and _post_crq_should_replace_group_text(
            group.get("validacio_posterior"),
            minimum_length=85,
            generic_fragments=("reexecutar el check", "reexecutar els checks"),
        ):
            group["validacio_posterior"] = _fix_encoding(guidance.get("validacio_posterior") or group.get("validacio_posterior") or "-")
        if not _normalize_text(group.get("limitacions")):
            group["limitacions"] = _fix_encoding(guidance.get("limitacions") or "")

    report_model["final_observations"] = _normalize_post_crq_final_observations_v2(report_model)
    report_data["report_model"] = report_model
    return report_data


def _post_crq_pdf_header_footer_final_v5(
    canvas,
    doc,
    profile: str,
    generated_at: str,
    footer_text: str,
    logo_path: Optional[Path],
    show_header: bool = True,
) -> None:
    canvas.saveState()
    width, height = doc.pagesize
    is_landscape = width > height
    page_margin = 0.7 * cm if is_landscape else doc.leftMargin
    left_margin = page_margin
    right_edge = width - page_margin
    top_y = height - 0.95 * cm
    footer_y = 0.75 * cm

    if show_header:
        canvas.setStrokeColor(PDF_BRAND_LINE)
        canvas.line(left_margin, top_y - 0.92 * cm, right_edge, top_y - 0.92 * cm)
        if logo_path and logo_path.exists():
            canvas.drawImage(
                str(logo_path),
                left_margin,
                top_y - 0.62 * cm,
                width=4.8 * cm,
                height=0.78 * cm,
                preserveAspectRatio=True,
                mask="auto",
            )

        bold_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
        regular_font = "OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
        canvas.setFont(bold_font, 9)
        canvas.setFillColor(PDF_BRAND_NAVY)
        canvas.drawRightString(right_edge, top_y, f"Auditoria Oracle {_fix_encoding(profile or '-')}")
        canvas.setFont(regular_font, 7.8)
        canvas.setFillColor(PDF_MUTED_TEXT)
        canvas.drawRightString(right_edge, top_y - 0.32 * cm, "Departament d'Educació i Formació Professional")
        canvas.drawRightString(right_edge, top_y - 0.62 * cm, f"Perfil: {_fix_encoding(profile)} · {_fix_encoding(generated_at)}")

    canvas.setStrokeColor(PDF_BRAND_LINE)
    canvas.line(left_margin, footer_y + 0.22 * cm, right_edge, footer_y + 0.22 * cm)
    canvas.setFont("OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 7.5)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(left_margin, footer_y, "Informe tècnic institucional")
    canvas.drawRightString(right_edge, footer_y, f"Pàgina {canvas.getPageNumber()} | {footer_text}")
    canvas.restoreState()


def _report_lot_counts_rows_v5(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in report_model.get("lot_summary") or []:
        rows.append(
            {
                "Lot": item.get("lot") or "SENSE LOT",
                "Crítiques": item.get("critical") or 0,
                "Mitjanes": item.get("medium") or 0,
                "Baixes": item.get("low") or 0,
            }
        )
    return rows


def _build_lot_headline_v6(group: Dict[str, Any], report_model: Dict[str, Any]) -> str:
    lot_name = str(group.get("lot") or "SENSE LOT")
    lot_summary = next((item for item in (report_model.get("lot_summary") or []) if (item.get("lot") or "SENSE LOT") == lot_name), {})
    critical = int(lot_summary.get("critical") or 0)
    medium = int(lot_summary.get("medium") or 0)
    low = int(lot_summary.get("low") or 0)
    return (
        f"El lot {lot_name} presenta "
        f"{_post_crq_count_label(critical, 'incidència crítica', 'incidències crítiques')}, "
        f"{_post_crq_count_label(medium, 'incidència mitjana', 'incidències mitjanes')} i "
        f"{_post_crq_count_label(low, 'incidència baixa', 'incidències baixes')}."
    )


def _incident_object_table_row_v7(_schema_group: Dict[str, Any], objecte: Dict[str, Any]) -> Dict[str, Any]:
    object_name = (
        objecte.get("OBJECTE")
        or objecte.get("nom")
        or objecte.get("objecte")
        or objecte.get("OBJECT_NAME")
        or "-"
    )
    object_type = (
        objecte.get("TIPUS")
        or objecte.get("tipus")
        or objecte.get("OBJECT_TYPE")
        or "-"
    )
    technical_value = (
        objecte.get("DADA TÈCNICA")
        or objecte.get("DADA T?CNICA")
        or objecte.get("DADA TÃˆCNICA")
        or objecte.get("dada_tecnica")
        or objecte.get("OBSERVACIÓ")
        or objecte.get("OBSERVACIÃ“")
        or objecte.get("OBSERVACI?")
        or objecte.get("observacio")
        or "-"
    )
    return {
        "OBJECTE": object_name,
        "TIPUS": object_type,
        "DADA TÈCNICA": technical_value,
    }


def _post_crq_pdf_cover_final_v7(canvas, profile: str, generated_at: str, cover_path: Path | None, report_model: Dict[str, Any], time_filter: Dict[str, Any]) -> None:
    width, height = A4
    canvas.saveState()
    title_font = "OracleAudit-Bold" if "OracleAudit-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    body_font = "OracleAudit" if "OracleAudit" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFillColor(rl_colors.white)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.rect(0, height - (7.8 * cm), width, 7.8 * cm, fill=1, stroke=0)
    canvas.setFillColor(PDF_BRAND_BLUE)
    canvas.rect(0, height - (7.8 * cm), width, 0.42 * cm, fill=1, stroke=0)

    if cover_path and cover_path.exists():
        canvas.saveState()
        canvas.setFillAlpha(0.12)
        canvas.drawImage(
            str(cover_path),
            width - (8.0 * cm),
            height - (6.6 * cm),
            width=6.6 * cm,
            height=4.9 * cm,
            preserveAspectRatio=True,
            anchor="n",
            mask="auto",
        )
        canvas.restoreState()

    panel_x = 1.35 * cm
    panel_y = 6.95 * cm
    panel_width = width - (2.7 * cm)
    panel_height = 10.35 * cm
    canvas.setFillColor(rl_colors.white)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 16, fill=1, stroke=0)
    canvas.setStrokeColor(PDF_BRAND_LINE)
    canvas.setLineWidth(0.9)
    canvas.roundRect(panel_x, panel_y, panel_width, panel_height, 16, fill=0, stroke=1)

    canvas.setFillColor(PDF_BRAND_BLUE)
    canvas.setFont(title_font, 10.2)
    canvas.drawString(panel_x + 0.9 * cm, panel_y + panel_height - 1.15 * cm, "AUDITORIA ORACLE · VALIDACIÓ POST-CRQ")
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.setFont(title_font, 23)
    canvas.drawString(panel_x + 0.9 * cm, panel_y + panel_height - 2.1 * cm, "Informe d'auditoria post-CRQ")
    _draw_canvas_wrapped_text(
        canvas,
        "Informe institucional de validació tècnica per lots, amb incidències prioritzades i detall operatiu dels checks executats.",
        panel_x + 0.9 * cm,
        panel_y + panel_height - 2.9 * cm,
        panel_width - (1.8 * cm),
        body_font,
        11.0,
        0.52 * cm,
        PDF_MUTED_TEXT,
    )

    meta_y = panel_y + 5.3 * cm
    left_x = panel_x + 0.9 * cm
    right_x = panel_x + (panel_width / 2) + 0.15 * cm
    meta_width = (panel_width / 2) - 1.05 * cm
    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, meta_y, "Perfil")
    canvas.drawString(right_x, meta_y, "Data de generació")
    canvas.setFont(body_font, 10.2)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(left_x, meta_y - 0.38 * cm, _fix_encoding(profile or "-"))
    canvas.drawString(right_x, meta_y - 0.38 * cm, _fix_encoding(generated_at or "-"))

    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, meta_y - 0.95 * cm, "Finestra auditada")
    canvas.drawString(right_x, meta_y - 0.95 * cm, "Període aplicat")
    _draw_canvas_wrapped_text(
        canvas,
        _resolve_report_time_window_label_final_v3(time_filter),
        left_x,
        meta_y - 1.33 * cm,
        meta_width,
        body_font,
        10.0,
        0.47 * cm,
        PDF_MUTED_TEXT,
    )
    _draw_canvas_wrapped_text(
        canvas,
        _fix_encoding(_display_period_label(time_filter)),
        right_x,
        meta_y - 1.33 * cm,
        meta_width,
        body_font,
        10.0,
        0.47 * cm,
        PDF_MUTED_TEXT,
    )

    canvas.setFont(title_font, 9.4)
    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.drawString(left_x, panel_y + 3.15 * cm, "Resum global")
    _draw_canvas_wrapped_text(
        canvas,
        _report_operational_cover_summary_v4(report_model),
        left_x,
        panel_y + 2.78 * cm,
        panel_width - (1.8 * cm),
        body_font,
        10.2,
        0.5 * cm,
        PDF_MUTED_TEXT,
    )

    metric_y = panel_y + 0.92 * cm
    metric_width = (panel_width - (1.8 * cm) - (3 * 0.34 * cm)) / 4
    for index, (label, value) in enumerate(_report_operational_cover_metrics_v7(report_model)):
        current_x = left_x + index * (metric_width + 0.34 * cm)
        canvas.setFillColor(PDF_SOFT_ALT if index % 2 == 0 else PDF_SOFT_FILL)
        canvas.roundRect(current_x, metric_y, metric_width, 1.72 * cm, 10, fill=1, stroke=0)
        canvas.setStrokeColor(PDF_BRAND_LINE)
        canvas.setLineWidth(0.45)
        canvas.roundRect(current_x, metric_y, metric_width, 1.72 * cm, 10, fill=0, stroke=1)
        canvas.setFillColor(PDF_BRAND_NAVY)
        canvas.setFont(title_font, 16)
        canvas.drawString(current_x + 0.22 * cm, metric_y + 1.0 * cm, value)
        _draw_canvas_wrapped_text(
            canvas,
            label,
            current_x + 0.22 * cm,
            metric_y + 0.72 * cm,
            metric_width - 0.34 * cm,
            body_font,
            8.6,
            0.38 * cm,
            PDF_MUTED_TEXT,
        )

    canvas.setFillColor(PDF_BRAND_NAVY)
    canvas.rect(0, 0.84 * cm, width, 0.18 * cm, fill=1, stroke=0)
    canvas.setFont(body_font, 8.2)
    canvas.setFillColor(PDF_MUTED_TEXT)
    canvas.drawString(1.35 * cm, 0.38 * cm, "Departament d'Educació i Formació Professional · Informe generat automàticament")
    canvas.restoreState()












