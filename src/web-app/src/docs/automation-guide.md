# Guia detallada d'Automatitzacions

> **Per començar**  
> Si només vols deixar una automatització operativa, segueix aquest ordre: **Jobs**, **Lots i mapatge**, **Destinataris**, **Plantilles** i finalment **Històric**.

## Què és aquest mòdul

`Automatitzacions` concentra la configuració operativa dels jobs, la classificació per lot, els destinataris, les plantilles i el seguiment de cada execució.

La idea clau és aquesta:

- el **job** defineix quan i com s'executa l'auditoria
- la **classificació per lot** decideix què s'envia
- l'**històric** i els **reintents** deixen traçabilitat i recuperació operativa

## Pantalles internes

### Jobs

- crea i edita jobs
- defineix perfil, planificació, timeout i checks
- permet activar, desactivar o executar ara

### Lots i mapatge

- **Mapeig schema -> lot**: relaciona cada schema Oracle amb un lot funcional
- **Backfill assistit**: proposa altes al catàleg mestre a partir del mapping tècnic
- **Catàleg mestre**: manté els lots operatius

### Destinataris

- mostra les rutes per lot
- deixa revisar el resum TIC
- ajuda a validar si la distribució té configuració mínima abans d'executar

### Plantilles

Els noms visibles en català són:

| Nom visible | Clau interna | Ús |
|---|---|---|
| Lot amb troballes | `provider_with_findings` | Enviament normal d'un lot amb incidències |
| Resum TIC | `tic_summary` | Resum general per a l'Àrea TIC |
| Reenviament manual | `manual_resend` | Nou enviament des de la cua de reintents |
| Lot sense troballes | `provider_without_findings` | Missatge opcional quan el lot no té anomalies |
| Error de generació de l'informe | `job_generation_failure` | Avís quan el report no s'ha pogut generar |

### Històric

- mostra cada execució registrada
- permet veure el detall per lot
- serveix per descarregar informes i validar si hi ha hagut enviaments

### Reintents

- concentra enviaments pendents o fallits
- permet reenviar sense repetir tota l'auditoria

## Flux recomanat

```mermaid
flowchart LR
    A[Jobs] --> B[Lots i mapatge]
    B --> C[Destinataris]
    C --> D[Plantilles]
    D --> E[Execució]
    E --> F[Històric]
    F --> G[Reintents]
```

## Com es configuren les plantilles

Les variables més habituals són:

- `{job_name}`
- `{profile}`
- `{lot}`
- `{status}`
- `{findings}`
- `{execution_id}`
- `{observations}`
- `{summary}`
- `{technical_legend}`
- `{affected_queries}`
- `{affected_schemas}`

> **Important**  
> Edita les plantilles quan vulguis canviar el to del missatge o la informació que rep l'audiència. Si el problema és de classificació o de rutes, revisa abans `Lots i mapatge` o `Destinataris`.

## Com es llegeix l'històric

| Àrea | Què t'indica | Quan és útil |
|---|---|---|
| Estat del run | si el job ha acabat bé, amb error o parcialment | validació ràpida |
| Resum per lots | quants lots tenen troballes, quins no i quins queden en revisió | lectura operativa |
| Detall per lot | estat, troballes, informe generat i enviament | anàlisi fina |
| Exportacions | CSV o PDF del seguiment | suport, auditoria o anàlisi posterior |

## Com actuar quan falla un enviament

1. Mira l'**Històric** i obre el detall del run.
2. Confirma si el problema és del resultat, de la ruta o de l'entrega.
3. Si el run és correcte però l'entrega ha fallat, ves a **Reintents**.
4. Si falta relació schema -> lot, revisa **Lots i mapatge**.
5. Si falta destinatari, revisa **Destinataris**.

## Glossari curt

- **Job**: definició programada de com s'executa una auditoria.
- **Lot**: unitat funcional de distribució.
- **Schema**: usuari o espai Oracle que es mapeja a un lot.
- **Backfill**: assistent per proposar altes al catàleg mestre a partir de `schema_lots`.
- **Històric**: registre d'execucions i detall per lot.
- **Reintent**: nova entrega d'un enviament fallit, sense repetir tota l'auditoria.
