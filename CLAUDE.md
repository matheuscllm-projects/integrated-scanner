<!-- FLEET:ESTILO-RESPOSTA v1 (2026-09-14) — cópia-mestra: scanners-commons/08-ESTILO-RESPOSTA.md. Editar LÁ e replicar; não divergir nesta cópia. -->
> **Estilo de resposta obrigatório (operador, 2026-09-14): CONCISO — teto de 200 palavras.**
> Toda resposta no chat, nesta ordem: **1) Objetivo** — 1 linha do que foi pedido · **2) O que foi feito** — bullets curtos, cada um com o *porquê* da decisão · **3) Dependências/pendências** — o que falta, o que bloqueia, de quem depende (`nenhuma` quando não houver).
> O teto conta **só prosa**. **Fora do teto** (nunca resumir, cortar nem "amostrar" pra caber): a tabela de entrega gerada pela ferramenta do repo (colada VERBATIM), blocos de comando/código, saída de teste colada como prova e artefato canônico do repo (brief, relatório, análise).
> Sem preâmbulo, sem repetir o pedido, sem recapitular o que já foi dito. Não cabe em 200 palavras? Entregue o essencial dentro do teto e ofereça o detalhe ("quer o detalhe de X?") — nunca estoure em silêncio.

# Scanner integrado — manual de operação

Regras de entrega e publicação: [DELIVERY_CHAT.md](DELIVERY_CHAT.md).
O integrado chama os scanners MYP, CardTrader, COMC e Liga. MYP e CardTrader
são as fontes padrão. Ele organiza preços e alertas; a decisão de compra é do operador.

## Instalação

Python 3.12, ambiente virtual e `pip install -r requirements.txt`.
Cada fonte deve estar em um clone irmão deste repositório, ou abaixo do diretório
definido em `SCANNERS_BASE`. No PC do operador, o layout legado é
`C:\Users\mathe\{integrated-scanner,myp-arbitrage-scanner,card-trader-scanner,scanner-comc}`.
Liga aceita `liga-pokemon-scanner` ou `liga-cards-scanner`.
O integrado prefere o `.venv` de cada fonte; sem ele, usa seu próprio Python.
Nesse caso, instalar também as dependências das fontes no mesmo ambiente.
CardTrader exige `CT_JWT`, em seu `.env` ou no ambiente; `POKEMONTCG_API_KEY` é opcional.
Nunca versionar segredos. No Windows, a dependência CT inclui `portalocker[win32]`.

## Rodar uma coleta nova

```powershell
python run_integrated.py --profile group2 --sources myp,ct
python run_integrated.py --sets PAF,PAR --ct-provider tcgcsv
python run_integrated.py --sets PAF --myp-max-products 5 --timeout 600
```

O último comando é um **diagnóstico limitado**, identificado no título e na API.
`--myp-max-products` limita cada edição MYP; não limita o catálogo CardTrader.
`quick` mantém o escopo histórico; `full` pode levar horas.
`group2` cobre as 14 coleções escolhidas pelo operador: Paldean Fates,
Paradox Rift, Obsidian Flames, 151, Paldea Evolved, Black Bolt, White Flare,
Crown Zenith, Silver Tempest, Lost Origin, Astral Radiance, Brilliant Stars,
Fusion Strike e Evolving Skies. Substrings MYP podem corresponder a mais de
uma entrada de edição; os filtros EN/NM continuam responsabilidade da fonte.
O registry tem 25 entradas; `/sets` mostra a cobertura por fonte.
CT `obf`, `pal`, `blk`, `wht`, `brs`, `fst`, `evs` foram verificados na API
`/expansions` em 06/09/2026. Fontes sem mapeamento são puladas explicitamente.

CardTrader usa **TCGCSV por padrão**, configurável com `--ct-provider`.
MYP aceita `--myp-provider auto|tcgcsv|pokemontcg`. TCGCSV é referência de dump,
não cotação em tempo real; a entrega não inventa a data de atualização do dump.
Cada execução CT usa um diretório de estado novo e `--no-cache`.
Cada execução MYP usa saída nova; não retoma checkpoints de solicitações anteriores.
O integrado passa `--delay 3.0` ao MYP para reduzir a frequência de consultas;
`--myp-delay <segundos>` permite configurar um intervalo positivo e finito.
`Retry-After` continua sendo respeitado. O orçamento MYP para um escopo finito
é o maior entre duas horas e 30 minutos por filtro de edição: Grupo 2 recebe
sete horas. Isso é limite de execução, não previsão de duração. `--timeout`
explícito prevalece, inclusive quando o operador precisa de um limite maior.
O MYP atualizado salva progresso a cada dez produtos e ao receber falha persistente,
respeita `Retry-After` e gera XLSX parcial com código 2. Retomada nativa com
`--resume` deve ser explícita, na mesma solicitação e saída, nunca preço de outro scan.

Liga só roda com `--collect-liga`, pois exige uma coleta nova com navegador.
Coleta falhou ou CSV não foi atualizado: não usar o CSV anterior.
COMC só aceita CSV/sidecar recém-produzido nas eras pedidas; exige os requisitos
de navegador do próprio repositório. Os testes ao vivo desta correção cobrem MYP/CT;
COMC/Liga precisam de validação específica no ambiente de navegador do operador.

## Formato MyP Cards

A tabela compacta apresenta número da linha, fonte, margem venda %, ROI aquisição %, compra R$,
referência US$/R$, diferença R$, carta com número, set, raridade, condição,
quantidade, flags e os dois links. O preço de referência é clicável.
Não substituir preço ou evidência ausente por zero, busca genérica ou outra carta.
Uma estimativa MYP aponta para a página MYP que a fornece.

Todas as linhas lidas permanecem na entrega, separadas em:
- Deals limpos com referência real;
- Validar manualmente;
- Fallback/estimativa;
- Rejeitados ou sem referência;
- Abaixo do corte, apenas diagnóstico.

O leitor MYP usa `All EN Cards`, evitando perder as linhas abaixo do corte.
Linha MYP com `Match Status` = `REVIEW` (MYP v5.20: variante/acabamento TCG sem
match único, referência da versão mais barata) vai para Validar manualmente.
CT preserva variante, idioma, condição, procedência, horário e validação.
Linhas CT não validadas não viram deals limpos por passar apenas no corte numérico.

**Margem e ROI (decisão do dono, padrão do ecossistema):** o integrado recalcula tudo dos
preços da linha, com UMA função (`normalize.sale_margin_pct`). **Margem sobre a venda =
`(referência − compra) / referência`** e é a única base do corte de 30% (coluna
"Margem venda %"). **ROI sobre a aquisição = `(referência − compra) / compra`** é uma
métrica SEPARADA (coluna "ROI aquisição %"), só informativa, nunca no corte: 30% de margem
sobre a venda equivale a 42,86% de ROI, e 30% de ROI equivale a só 23,08% de margem.
Ex.: compra 75, referência 100 → ROI 33,3%, margem 25%: NÃO passa o corte. Preço de compra
ou referência ausente/zero → sem número ("—") e bucket "Rejeitados / sem referência",
nunca margem calculada com zero. As fontes mantêm seus cortes próprios, registrados por
fonte no resumo ("corte de origem"): MYP e Liga 30% sobre a compra (= 23,1% sobre a venda);
CT 30% sobre a venda (`--threshold 0.30`, fração; igual ao do integrado); COMC
`MIN_DISCOUNT_PERCENT = 20`, inteiro, sobre a venda (o integrado passa `--min-discount 20`
explícito, pois a variável de ambiente do COMC poderia apertá-lo sem ele saber). Todos
são iguais ou mais frouxos que 30% sobre a venda, portanto nada que passa aqui é perdido
na fonte; o integrado reaplica o corte sobre a venda. CT também exporta
linhas abaixo do seu corte, que permanecem identificadas e sem validação automática.
Nenhuma taxa é embutida. Diferença bruta não é lucro líquido.
O USD original e o câmbio implícito do MYP/CT são preservados.
Para fontes sem FX próprio, há consulta nova ou `--fx` explícito; não há fallback numérico antigo.

## Comparação entre lojas

O parser aceita o formato real CT `Nome (código)` e rejeita pares contraditórios.
O casamento exige set, número e nomes compatíveis, condição e idioma.
Variantes conhecidas diferentes ficam separadas. Uma variante ausente só pode
se associar a um único candidato de variante conhecida e sempre exige `validar`;
nunca conecta duas variantes diferentes. Dados ausentes e alertas na fonte
impedem marcar uma loja como a mais barata sem revisão.
Inclui também preços coletados abaixo do corte para permitir comparar a mesma
carta quando uma fonte não atingiu o limiar. Não é uma consulta exaustiva de
todas as lojas; só compara as linhas recebidas. Ofertas explicitamente rejeitadas,
STALE, API_ERROR e PRICE_CHANGED ficam fora da escolha de menor preço.

## Falhas, API e releitura histórica

Cada fonte mantém erro, log e horário. Nenhuma falha cai no último XLSX antigo.
Status por fonte (o resumo e `run_status` da API repetem a frase `Código de saída N — ...`):
`ok` (arquivo válido com linhas com preço) · `ok (fonte sem linhas)` (arquivo válido e vazio:
a fonte não trouxe nada, não é falha) · `sem cobertura (...)` (há linhas, mas nenhuma com
referência e preço de compra, ou câmbio ausente: NÃO é ok) · `parcial (N de M linhas ...)`
(parte das linhas sem referência/compra ou fora do contrato) · `falhou`/`timeout`/`indisponível`.
Saída 0 = todas as fontes ativas ok (inclui "fonte sem linhas"); 2 = alguma fonte falhou,
ficou sem cobertura ou parcial, mas ao menos uma está ok; 1 = nenhuma fonte ok.
Nunca 0 com fonte falha ou sem cobertura. `GET /deals` responde 409 pedindo novo scan se o
store tiver outro `schema_version`, e informa `sem_margem` (linhas sem margem não passam
em filtro de margem e vão ao fim). Margem é exibida arredondada para BAIXO (29,96% nunca
vira 30,0%). Sem câmbio (`--skip-scan` sem `--fx`) o COMC fica "câmbio ausente", nunca
calculado com câmbio 0 nem cotação presumida.
A API reflete `done`, `partial` ou `failed`; `/status` informa modo e limite diagnóstico.

```powershell
python -m uvicorn api:app --host 127.0.0.1 --port 8077
```

`GET /health`, `/sets`, `/sources`, `/deals`, `/status` consultam a API.
`POST /scan` aceita sets, sources, min_margin, ct_provider, myp_provider e
myp_max_products e myp_delay_s. COMC exige allow_comc; Liga exige collect_liga.
O store mantém todos os baldes. Nenhuma publicação externa é feita pelo scanner.

**Arquivos de entrada são identificados pelo CONTEÚDO, nunca pelo nome.** Cada leitor exige
colunas/chaves obrigatórias: CT = scan cru (aba `Oportunidades`; colunas `Card Name`, `Set`,
`Scan R$ (raw)`, `TCG Market (BRL)`, `TCG Market (USD)`, `Link CardTrader`), MYP = `Card Name`,
`Edition`, `MYP EN NM (R$)`, `TCG Player (R$)`, `URL`; COMC = `card`, `set`, `comc_price`,
`tcg_reference`, `comc_url`; Liga = lista JSON com `card_name`, `set_name`, `price_liga_brl`,
`price_tcg_brl`, `liga_url`. Arquivo que não cumpre o contrato é REJEITADO com mensagem que
diz o que faltou (`SourceFormatError`; a fonte fica `falhou (normalização)` com a causa) e
nunca vira dado. Em especial, um relatório processado do postprocess do CT (aba `Deals`,
colunas `Preço CT (R$)`/`TCG (R$)`) jamais é lido como scan cru. Os localizadores
`latest_ct_output`/`latest_myp_output` também escolhem por conteúdo. Linha individual sem preço
de compra ou sem referência continua na tabela, marcada "sem referência", sem margem, e o
status da fonte conta quantas foram.

Reprocessamento técnico explícito, **sem tratar como coleta atual**:

```powershell
python run_integrated.py --skip-scan --sources ct --ct-output caminho/arquivo.xlsx
```

Para MYP use `--myp-output`; Liga aceita `--liga-report` proveniente de CSV real.
A releitura fica marcada como histórica, tem escopo desconhecido e store separado;
não substitui o store da coleta atual. Sem arquivo explícito, não procura o último.

## Desenvolvimento e verificação

Alterações entram por branch + PR, com testes antes do merge. O operador autorizou
merge nesta tarefa. `python -m pytest -q` roda as regressões offline.
CI verifica Linux e Windows com fixtures sintéticas; nunca publica preços ou logs
de mercado, artifacts de coleta, segredos ou resultados de scans no GitHub.
`outputs/` permanece ignorado. Handoffs antigos são contexto histórico;
este manual e DELIVERY_CHAT descrevem o comportamento vigente.

**Sem check-ins automáticos de PR** (operador, 2026-09-12): depois de abrir um PR, a sessão
reporta o link no chat e **para** — sem `subscribe_pr_activity`, sem check-in agendado
(`send_later`/Routine/cron), sem poll de CI/review. Assinatura de PR criada pelo harness deve
ser cancelada. Exceção única: pedido explícito do operador ("acompanha esse PR").
