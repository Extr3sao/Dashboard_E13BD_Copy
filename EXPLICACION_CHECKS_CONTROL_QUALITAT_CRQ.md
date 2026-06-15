# Catàleg operatiu de checks post-CRQ

## Origen de les consultes
- Fitxer de referència: `auditoria_post_crq.md`
- Aquest catàleg utilitza com a font de veritat la definició funcional i SQL dels checks post-CRQ.
- L'objectiu d'aquest document és ajudar els lots a entendre ràpidament què detecta cada control, quin risc té, com s'ha de revisar i com s'ha de validar la correcció.

## CHECK_01 — Taules recents sense clau primària
### Què detecta
Taules d'esquemes d'usuari modificades dins de l'interval analitzat que no disposen d'una clau primària activa.
### Per què és important
L'absència d'una clau primària dificulta garantir la unicitat de les dades, complica la integritat referencial i pot degradar consultes i processos de manteniment.
### Impacte sobre el lot
Pot provocar errors funcionals, duplicats o regressions de rendiment en entorns superiors si el canvi es promou sense corregir. També pot complicar mecanismes d'integració, replicació o reconciliació que pressuposen una clau primària estable per identificar cada registre.
### Com s'ha de revisar
1. Executar el check i identificar les taules afectades.
2. Verificar si el model de dades requereix una clau primària real.
3. Confirmar si existeix una restricció equivalent o una justificació funcional documentada.
4. Revisar l'impacte sobre processos que depenen de la unicitat.
### Com es pot corregir
Crear la clau primària corresponent amb `ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY (...)`. Si excepcionalment no és viable, documentar la justificació i aplicar l'alternativa funcional aprovada.
### Limitacions o falsos positius
Pot marcar taules en revisió funcional o objectes temporals. En taules de càrrega, staging o treball intermedi, la manca de clau primària pot requerir una validació funcional específica abans de considerar-la una incidència estructural real. També cal revisar amb atenció els casos amb restriccions deshabilitades o substitucions parcials per índexs únics.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Objecte
### Validació posterior
Reexecutar el check i confirmar que la taula ja no apareix. Si s'ha creat la clau primària, verificar també que la definició queda activa i validada.

## CHECK_02 — Taules recents sense índexs
### Què detecta
Taules modificades recentment que no tenen cap índex definit a `DBA_INDEXES` i que, a més, no queden excloses pels filtres del control (`temporary = 'N'`, `iot_type IS NULL`, noms `TMP`/`APEX` i `num_rows <> 0`). El check acredita l'absència total d'índexs sobre la taula; no determina per si sol quins accessos reals necessiten indexació.
### Per què és important
Una taula sense índex pot obligar Oracle a fer escaneigs complets i degradar el rendiment de consultes, càrregues i validacions posteriors al desplegament.
### Impacte sobre el lot
Pot allargar validacions, degradar processos de càrrega o penalitzar consultes i joins només quan la taula tingui volum rellevant o participi en accessos recurrents. Si la taula és petita, transitòria o d'ús molt puntual, el risc real pot ser baix malgrat la troballa.
### Com s'ha de revisar
1. Prioritzar les taules amb més volum o amb evidència d'ús funcional real.
2. Confirmar si la taula és persistent o si forma part d'un flux temporal, de càrrega o de suport.
3. Revisar consultes, joins, validacions i operacions DML que hi accedeixen.
4. Verificar si el model ja es dona per cobert per altres mecanismes o si realment s'ha omès la indexació.
5. Contrastar el risc amb el volum esperat, la freqüència d'accés i els plans d'execució dels casos d'ús principals.
### Com es pot corregir
Definir només els índexs justificats pels patrons d'accés previstos i actualitzar les estadístiques si escau. No s'ha d'indexar automàticament qualsevol taula detectada sense contrastar abans el cost sobre escriptures i manteniment.
### Limitacions o falsos positius
La SQL no avalua patrons d'accés, joins, plans d'execució ni concurrència: només comprova que la taula no té cap índex registrat. Hi pot haver taules que, per disseny, no necessitin índexs o que encara siguin en una fase intermèdia de càrrega. El fet de no tenir cap índex no implica necessàriament una incidència greu si la taula és petita, d'ús molt puntual o forma part d'un flux temporal.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Objecte
### Validació posterior
Reexecutar el check després de la correcció i confirmar que les taules afectades ja no hi apareixen. A més, convé validar amb consultes representatives o amb plans d'execució que l'índex creat aporta benefici real i no introdueix un sobrecost innecessari en `INSERT`, `UPDATE` o `DELETE`.

## CHECK_03 — Seqüències sense cache
### Què detecta
Seqüències modificades dins de la finestra auditada amb `NOCACHE` o amb un `CACHE_SIZE` inferior al llindar mínim aplicat pel control (`< 20`). La sortida també incorpora una recomanació de cache calculada de manera heurística a partir de `INCREMENT_BY`.
### Per què és important
Una seqüència sense `CACHE` o amb un valor massa baix incrementa la contenció sobre el diccionari i penalitza insercions concurrents. En entorns amb càrrega real, això pot traduir-se en més esperes internes associades a l'accés a la seqüència i en menys capacitat de resposta dels processos que fan servir `NEXTVAL` de manera intensiva.
### Impacte sobre el lot
Pot alentir insercions concurrents, càrregues batch o processos de generació massiva d'identificadors si les seqüències detectades entren en circuits amb volum real. L'impacte és principalment de rendiment i escalabilitat, no d'integritat funcional.
### Com s'ha de revisar
1. Identificar les seqüències detectades.
2. Relacionar-les amb les taules o processos que les consumeixen.
3. Estimar el volum real d'insercions i la concurrència esperada.
4. Verificar si existeix algun requisit que justifiqui restringir el `CACHE` i si la recomanació retornada (`50`, `100` o `20`) és coherent amb el patró d'ús.
### Com es pot corregir
Modificar la seqüència amb `ALTER SEQUENCE` i establir un valor de `CACHE` adequat al patró d'ús. El valor suggerit pel control s'ha d'interpretar com un punt de partida, no com una mida òptima universal.
### Limitacions o falsos positius
El control no consulta mètriques AWR ni volum real de `NEXTVAL`; la recomanació és heurística. Algunes seqüències de baixa freqüència, seqüències tècniques o casos amb requisits estrictes de numeració poden admetre un `CACHE` petit o fins i tot `NOCACHE` sense impacte rellevant.

> **Nota sobre la naturalesa heurística**: Les recomanacions de cache (50, 100, 20) que genera aquest control són orientatives, basades en el valor d'`INCREMENT_BY` i no en dades reals de càrrega (AWR). La consulta SQL retorna explícitament `'Heuristica'` com a `font_dades`. Per tant, els valors suggerits s'han de validar contra el volum real d'insercions i la concurrència esperada.

### Dades que s'han de mostrar a la taula
- Esquema
- Seqüència
- Cache actual
- Cache recomanada
- Data de modificació
### Validació posterior
Reexecutar el check, verificar a `DBA_SEQUENCES` que el nou valor de `CACHE_SIZE` s'ha aplicat correctament i, si la seqüència és sensible, contrastar-ne l'efecte amb proves d'inserció o mètriques de rendiment del procés afectat.

## CHECK_04 — Claus foranes sense índex de suport
### Què detecta
Claus foranes recents que no disposen d'un índex amb la **primera columna (columna líder)** de la FK com a primera columna de l'índex. El control verifica exclusivament la columna líder (`column_position = 1`), **no la cobertura completa** d'una FK composta amb múltiples columnes.
### Per què és important
L'absència d'aquest índex pot provocar bloquejos amplis, esperes innecessàries i degradació de les operacions `DELETE` o `UPDATE` sobre la taula pare.
### Impacte sobre el lot
Pot incrementar el risc de bloqueig i d'escaneigs innecessaris en operacions de manteniment sobre la taula pare. El risc és especialment rellevant quan el lot introdueix noves relacions o quan les taules filles participen en processos concurrents de volum.
### Com s'ha de revisar
1. Identificar la clau forana i la taula afectada.
2. Revisar les columnes de la constraint i els índexs existents sobre la taula filla.
3. Verificar si existeix algun índex amb la columna líder en primera posició i, si la FK és composta, si la resta de columnes també queden cobertes en l'ordre adequat.
4. Confirmar l'impacte sobre operacions de manteniment de la taula pare.
### Com es pot corregir
Crear o completar l'índex de suport tenint en compte la definició de la clau forana i el patró d'ús de la taula. Idealment l'índex ha de cobrir totes les columnes de la FK composta.
### Limitacions o falsos positius
El resultat no s'ha d'interpretar automàticament com a “FK sense índex complet”: només indica que no s'ha trobat suport sobre la columna líder en primera posició. En claus compostes cal revisió manual, perquè un índex parcial o amb un altre ordre de columnes pot no resoldre del tot el risc de bloqueig.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Taula
- Constraint FK
### Validació posterior
Reexecutar el check i validar amb proves funcionals o tècniques que les operacions sobre la taula pare no provoquen bloquejos amplis. Si la FK és composta, verificar també que l'índex creat o reaprofitat cobreix la definició completa prevista.

## CHECK_05 — Constraints recents deshabilitades
### Què detecta
Constraints de tipus `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` o `CHECK` associades a taules modificades dins de la finestra auditada i que es troben en estat `DISABLED`. El camp `VALIDATED` s'ofereix com a dada informativa addicional a la sortida, però **no s'utilitza com a filtre**.

> **Precisió sobre l'abast**: La SQL d'aquest check filtra exclusivament per `status = 'DISABLED'`. No detecta constraints amb `STATUS = 'ENABLED'` i `VALIDATED = 'NOT VALIDATED'`. Per cobrir aquesta casuística caldria ampliar la SQL amb un filtre addicional.

### Per què és important
Una constraint deshabilitada pot permetre dades inconsistents i deixar el model de dades en un estat incomplet respecte del canvi desplegat.
### Impacte sobre el lot
L'impacte depèn del tipus de constraint afectada: una `PRIMARY KEY` o `UNIQUE` pot permetre duplicats, una `FOREIGN KEY` pot obrir la porta a registres orfes i una `CHECK` pot deixar passar valors fora de domini. Si la desactivació no és temporal i controlada, el lot pot promoure un model inconsistent.
### Com s'ha de revisar
1. Identificar la constraint, la taula i el seu tipus.
2. Verificar l'estat exacte (`STATUS` i `VALIDATED`).
3. Confirmar si la desactivació forma part d'una finestra temporal controlada o si ha quedat pendent per error.
4. Revisar si ja hi ha dades que impedeixen tornar-la a validar.
### Com es pot corregir
Reactivar la constraint i, si cal, validar les dades existents abans d'executar `ENABLE VALIDATE` o l'operació equivalent que correspongui.
### Limitacions o falsos positius
Pot haver-hi casos temporals durant una càrrega o migració en què la constraint estigui deshabilitada de manera controlada; en aquests casos cal una justificació formal i un pas posterior de revalidació. El check actual **no detecta** constraints en estat `ENABLED` + `NOT VALIDATED`.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Taula
- Constraint
- Estat
- Estat de validació (informatiu)
### Validació posterior
Reexecutar el check i confirmar que la constraint deixa d'aparèixer com a `DISABLED`. Quan la restricció protegeixi dades existents, contrastar també que el rearmament s'ha fet amb l'estat de validació esperat i sense errors de dades pendents.

## CHECK_06 — Índexs duplicats recents (mateixa columna líder)
### Què detecta
Parelles d'índexs sobre la mateixa taula que comparteixen la mateixa columna líder i on almenys un dels dos índexs s'ha modificat dins de la finestra auditada. El check detecta candidats a solapament funcional; no demostra per si sol que els índexs siguin equivalents ni prescindibles.
### Per què és important
Els índexs redundants incrementen el cost de les escriptures, consumeixen espai i poden complicar el manteniment i l'anàlisi dels plans d'execució.
### Impacte sobre el lot
Si la redundància és real, pot provocar més cost de DML, més espai ocupat i més complexitat de manteniment després del desplegament. Si els índexs tenen funcions diferents, l'impacte pot ser nul i la troballa queda en revisió.
### Com s'ha de revisar
1. Identificar la parella d'índexs detectada.
2. Comparar-ne la definició completa: tipus, unicitat, ordre de columnes, particionament i suport a constraints.
3. Revisar l'ús real i els plans d'execució associats.
4. Determinar si tots dos índexs cobreixen el mateix cas d'ús o si n'hi ha un de necessari per a una constraint o per a consultes específiques.
5. Només després d'aquesta anàlisi decidir si cal mantenir, fusionar o retirar algun dels índexs.
### Com es pot corregir
No s'ha d'eliminar directament cap índex només perquè comparteixi columna líder. Primer cal analitzar-ne la definició completa, l'ordre de columnes, el suport a constraints i els plans d'execució. Si es confirma la redundància funcional, aleshores es pot retirar o redissenyar l'estratègia d'indexació perquè cada índex respongui a una necessitat real.
### Limitacions o falsos positius
Compartir la mateixa columna líder no implica necessàriament redundància total; cal revisar les columnes addicionals, l'ordre complet de la definició, el tipus d'índex i els plans d'execució que suporta abans de concloure que es tracta d'un duplicat funcional.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Taula
- Índex 1
- Índex 2
### Validació posterior
Reexecutar el check i confirmar que la parella redundant ja no apareix. A més, cal comparar plans d'execució dels accessos rellevants abans i després del canvi, verificar que no s'ha deixat sense suport cap constraint i comprovar que el comportament DML no empitjora.

## CHECK_07 — Objectes recents invàlids
### Què detecta
Objectes Oracle modificats dins de la finestra auditada que es troben en estat `INVALID`, incloent-hi tipus habituals com `PACKAGE BODY`, `PROCEDURE`, `FUNCTION`, `TRIGGER`, `VIEW` o `MATERIALIZED VIEW`.
### Per què és important
Un objecte invàlid pot impedir l'execució de processos crítics i és un indicador directe d'errors de compilació o dependències trencades.
### Impacte sobre el lot
Pot bloquejar la validació del lot o generar errors immediats quan s'invoca l'objecte afectat. En `PACKAGE BODY`, `PROCEDURE` o `FUNCTION` això sol traduir-se en fallades d'execució; en `VIEW` o `MATERIALIZED VIEW`, en consultes errònies o refrescos fallits; en `TYPE`, en errors de compilació o ús sobre objectes dependents.
### Com s'ha de revisar
1. Identificar l'objecte, l'esquema i el tipus.
2. Comprovar si l'objecte és conseqüència directa d'un canvi del lot.
3. Revisar els errors de compilació a `USER_ERRORS` o `DBA_ERRORS`.
4. Analitzar possibles dependències afectades, canvis en objectes base o recompilacions pendents.
5. Ajustar la revisió al tipus d'objecte: compilació i dependències en PL/SQL, definició SQL i privilegis en `VIEW`, cicle de refresh i objectes base en `MATERIALIZED VIEW`, i tipus/atributs dependents en `TYPE`.
### Com es pot corregir
Recompilar l'objecte i corregir la causa arrel de la invalidesa abans de tornar a desplegar o promoure el canvi. Segons el cas, la causa pot ser un error de compilació, un canvi incompatible en una dependència, un objecte referenciat inexistent o un refresh incomplet d'una vista materialitzada.
### Limitacions o falsos positius
Durant determinades finestres tècniques es poden detectar invalideses transitòries, però s'han de tancar abans del pas a l'entorn següent.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Objecte
- Tipus d'objecte
### Validació posterior
Reexecutar el check, confirmar que l'objecte queda en estat `VALID` i executar una validació ajustada al tipus d'objecte: compilació i execució controlada per PL/SQL, consulta real sobre `VIEW`, comprovació de refresh per `MATERIALIZED VIEW` i verificació de dependències per `TYPE`.

## CHECK_08 — Columnes NUMBER sense precisió ni escala
### Què detecta
Columnes definides com a `NUMBER` sense precisió ni escala explícites.
### Per què és important
Una definició massa oberta debilita el model de dades, dificulta la validació i pot permetre valors fora del rang funcional esperat. També introdueix ambigüitat semàntica: no queda clar si la columna representa un enter, un import decimal, un percentatge o un identificador tècnic.
### Impacte sobre el lot
Pot introduir fragilitat en el model, complicar les validacions de dades i augmentar el cost de manteniment quan calgui integrar, migrar o governar la informació emmagatzemada. També pot ocultar una manca de contracte de dades clar entre aplicacions, interfícies i processos de càrrega, afavorir conversions o arrodoniments inesperats a la capa d'aplicació i, en alguns casos, comportar un ús menys eficient de l'emmagatzematge del que seria possible amb un domini més acotat.
### Com s'ha de revisar
1. Identificar les columnes detectades.
2. Revisar-ne la finalitat funcional.
3. Determinar si han de ser enters o valors decimals amb una precisió concreta.
4. Validar l'impacte de restringir-ne la definició.
5. Confirmar si existeix una justificació funcional explícita per mantenir la columna oberta, especialment en objectes tècnics o dades intermèdies.
### Com es pot corregir
Modificar la columna amb la precisió i l'escala adequades, validant prèviament que les dades existents siguin compatibles amb el nou tipus. Si la columna participa en interfícies, APIs o càlculs, cal coordinar el canvi amb la capa d'aplicació per evitar conversions o arrodoniments inesperats.
### Limitacions o falsos positius
Hi pot haver casos excepcionals en què una definició oberta de `NUMBER` sigui deliberada i funcionalment justificada, especialment en objectes tècnics o columnes de suport. En aquests casos la revisió ha de distingir entre model funcional i artefacte intern.
### Dades que s'han de mostrar a la taula
- Esquema
- Taula
- Columna
- Posició
### Validació posterior
Reexecutar el check, confirmar que la columna ja no apareix amb precisió i escala buides i validar que les dades existents continuen encaixant amb el domini definit, sense regressions sobre interfícies, càrregues, càlculs dependents ni conversions o arrodoniments a la capa d'aplicació.

## CHECK_09 — Sinònims recents trencats
### Què detecta
Sinònims modificats recentment que apunten a objectes inexistents o no resolubles.
### Per què és important
Un sinònim trencat pot provocar errors d'execució immediats en codi, consultes o processos que en depenen.
### Impacte sobre el lot
Pot fer fallar validacions funcionals o tècniques i obligar a correccions urgents després del desplegament.
### Com s'ha de revisar
1. Identificar el sinònim i l'objecte de destí.
2. Verificar si l'objecte existeix i és accessible.
3. Confirmar si el canvi és temporal o si s'ha perdut una dependència real.
4. Revisar l'impacte sobre aplicacions o paquets que utilitzen el sinònim.
### Com es pot corregir
Corregir la definició del sinònim o recrear l'objecte de destí segons el disseny previst.
### Limitacions o falsos positius
Alguns sinònims poden formar part de canvis encara incomplets dins d'una mateixa finestra de desplegament; cal revisar el context abans de descartar-los.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Sinònim
- Objecte de destí
### Validació posterior
Reexecutar el check i executar les proves d'integració necessàries per confirmar que la resolució de noms és correcta.

## CHECK_10 — WHEN OTHERS THEN NULL en codi recent
### Què detecta
Línies de codi font d'objectes PL/SQL modificats dins de la finestra auditada que contenen el patró `WHEN OTHERS THEN NULL`, detectat per expressió regular sobre `ALL_SOURCE`.
### Per què és important
Aquest patró amaga errors i dificulta el diagnòstic: la incidència es produeix igualment, però sense registre ni propagació adequada. Això complica la traçabilitat, la depuració i l'anàlisi de causes arrel.
### Impacte sobre el lot
Pot deixar errors operatius ocults en processos del lot, eliminar evidència útil per al diagnòstic i dificultar que suport i desenvolupament puguin reconstruir què ha fallat realment en producció.
### Com s'ha de revisar
1. Identificar els objectes afectats.
2. Localitzar el bloc d'excepció concret.
3. Analitzar quins errors s'estan ignorant i si existeix una justificació funcional real.
4. Revisar el comportament funcional associat.
### Com es pot corregir
Substituir el patró per gestió d'errors explícita, amb tractament, registre o propagació de l'excepció segons correspongui.
### Limitacions o falsos positius
La SQL actual no exclou línies comentades; per tant, comentaris que continguin el patró també poden aparèixer com a troballa. En casos molt excepcionals el patró pot formar part d'una decisió controlada, però cal documentar-la de manera explícita i demostrar que hi ha traçabilitat equivalent.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Objecte
### Validació posterior
Tornar a executar el check, confirmar que el patró ha desaparegut del codi actiu i validar amb proves funcionals o d'error controlat que l'excepció ara es registra o es propaga de la manera prevista, amb traça suficient per al diagnòstic.

## CHECK_11 — Problemes de codi en paquets, procediments i funcions
### Què detecta
Objectes PL/SQL modificats recentment de tipus `PROCEDURE`, `FUNCTION`, `PACKAGE BODY` o `TRIGGER` en què s'ha detectat una **proximitat heurística** entre una sentència d'inici de bucle (`LOOP`, `FOR ... IN`) i una operació DML (`INSERT INTO`, `UPDATE ... SET`, `DELETE FROM`, `SELECT ... INTO`) en un radi de menys de 25 línies de codi. El control exclou completament l'objecte si en qualsevol línia hi troba `BULK COLLECT` o `FORALL`.

> **Precisió sobre l'abast real**: La SQL d'aquest check **NOMÉS** implementa la detecció de proximitat LOOP + DML. **No detecta** els patrons següents (malgrat que el comentari SQL els esmenti): `COMMIT` dins de bucle, `DBMS_OUTPUT` residual en producció, ni `EXECUTE IMMEDIATE` amb concatenació. Aquests patrons requeririen regex addicionals a la definició SQL que actualment no existeixen.

> **Alineació funcional**: La descripció funcional antiga del check era més àmplia que la implementació efectiva. Si es vol atribuir cobertura a altres patrons diferents de LOOP/FOR + DML, això requereix validació manual o una ampliació explícita de la SQL.

### Per què és important
Un bucle amb DML sense optimització BULK pot provocar canvis de context excessius entre PL/SQL i SQL, amb degradació de rendiment proporcional al nombre de files.
### Impacte sobre el lot
Pot introduir regressions de rendiment en processos batch o nocturns si el DML està realment dins del bucle i el volum o la freqüència del procés són significatius. Si la proximitat detectada no correspon a un patró fila a fila real, la troballa no s'ha d'interpretar com a incidència confirmada.
### Com s'ha de revisar
1. Obrir cada objecte detectat.
2. Localitzar el bucle i l'operació DML reportada, comprovant la distància real entre línies marcades.
3. Verificar si el DML està realment dins del bucle o si la detecció per proximitat és un fals positiu.
4. Valorar si el procés és candidat a tractament `BULK COLLECT` + `FORALL` segons el volum real, la freqüència d'execució i si l'objecte ja conté optimitzacions bulk en un altre tram de codi.
5. Qualsevol conclusió sobre `COMMIT`, `DBMS_OUTPUT` o `EXECUTE IMMEDIATE` s'ha de tractar com a revisió manual, no com a cobertura garantida del control actual.
6. Si hi ha dubte sobre l'abast del patró, la troballa requereix validació manual abans de plantejar cap refactorització.
### Com es pot corregir
Només després de validar manualment el patró, refactoritzar el procés per treballar amb col·leccions i operacions bulk quan el volum, la freqüència i la criticitat del flux ho justifiquin.
### Limitacions o falsos positius
- **Falsos positius per proximitat**: El control considera sospitós qualsevol DML marcat a menys de 25 línies d'un inici de bucle, independentment de si el DML està realment dins del bucle o si entre mig hi ha lògica que canvia el context.
- **No detecta DBMS_OUTPUT, EXECUTE IMMEDIATE ni COMMIT en bucle**: La SQL actual no implementa regex per a aquests patrons.
- **Exclusió global per optimització bulk**: Si l'objecte conté qualsevol `BULK COLLECT` o `FORALL`, queda exclòs completament encara que en altres trams mantingui DML fila a fila.
- **Heurístic, no determinista**: La detecció per proximitat de línies és una aproximació, no una anàlisi de flux de control ni de dominis de volum.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Objecte
### Validació posterior
Reexecutar el check i completar proves funcionals i tècniques sobre l'objecte refactoritzat. Quan s'hagi introduït tractament bulk, cal contrastar també el comportament transaccional, el rendiment amb volum real o representatiu i confirmar manualment que el patró sospitós inicial ha quedat resolt sense alterar la lògica del procés.

## CHECK_12 — Candidats a BULK COLLECT / càrrega massiva
### Què detecta
Objectes PL/SQL modificats recentment de tipus `PROCEDURE`, `FUNCTION` o `PACKAGE BODY` que no contenen `BULK COLLECT` ni `FORALL` i que, a més, presenten almenys un d'aquests patrons: `FETCH ... INTO` fila a fila o DML dins d'un bucle. El check identifica candidats a optimització; no conclou per si sol que qualsevol loop sigui incorrecte ni que el cas justifiqui refactorització immediata.
### Per què és important
Aquests patrons són una causa freqüent de rendiment deficient en processos de càrrega o tractament massiu de dades.
### Impacte sobre el lot
Pot allargar processos batch, generar colls d'ampolla i reduir la capacitat de resposta dels fluxos nocturns o massius quan el volum i la freqüència del procés facin rellevant el cost del tractament fila a fila.
### Com s'ha de revisar
1. Identificar si la troballa prové d'un `FETCH ... INTO` fila a fila o d'un DML dins de bucle.
2. Estimar la cardinalitat real del procés i la freqüència d'execució.
3. Valorar si el flux és realment candidat a tractament bulk o si el cost actual és assumible.
4. Comparar el cost actual amb una alternativa `BULK COLLECT` / `FORALL`.
5. Considerar també el cost de refactorització, el tractament d'excepcions bulk i la finestra operativa disponible.
### Com es pot corregir
Refactoritzar el procés per treballar amb col·leccions i operacions bulk només quan el volum, la freqüència i el cost actual del procés justifiquin el canvi. En alguns casos serà suficient documentar que el patró detectat no és prioritari o que la complexitat de refactorització supera el benefici esperat.

> **Nota de prudència**: No tot procés fila a fila justifica una refactorització BULK. La millora s'ha de prioritzar segons el **volum** de files tractades, la **freqüència** d'execució, la **finestra operativa disponible** i la **complexitat** de la refactorització (gestió d'excepcions bulk, `LIMIT`, `SAVE EXCEPTIONS`). Processos que tracten molt poques files o s'executen de manera esporàdica poden no obtenir-ne un benefici apreciable.

### Limitacions o falsos positius
La SQL no incorpora mètriques d'execució, volum real, temps de procés ni cost de refactorització: només classifica patrons de codi. En processos amb molt poques files o amb execució esporàdica, el tractament bulk pot no aportar un benefici apreciable.
### Dades que s'han de mostrar a la taula
- Lot
- Esquema
- Objecte
- TE_BULK
### Validació posterior
Reexecutar el check i confirmar que l'objecte deixa d'aparèixer o que el patró detectat ha canviat segons la correcció aplicada. A més, cal contrastar el rendiment, el comportament funcional i el cost transaccional amb un volum representatiu abans de donar per bona la refactorització.
