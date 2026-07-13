# Quanto Vale BH

Aplicativo Streamlit para estimar valores atuais de imóveis, consultar transações declaradas à Prefeitura de Belo Horizonte e acompanhar o mercado imobiliário por bairro.

## Funções principais

- Avaliação de imóvel a partir de uma transação localizada na base da PBH.
- Preenchimento manual como alternativa quando o imóvel não é localizado.
- Estimativa combinando FipeZAP BH, comparáveis PBH e transações do mesmo endereço, quando disponíveis.
- Consulta dos imóveis efetivamente usados como referência no cálculo.
- Pesquisa de outras transações e negócios do mesmo endereço.
- Link textual para abrir o endereço no Google Maps.
- Painel de mercado com leitura automática, evolução contra Belo Horizonte, faixas de preço, comparação e ranking de bairros e perfil dos imóveis negociados.

## Valor de referência

Para os cálculos estatísticos:

`valor_referencia = max(valor_declarado, valor_base_calculo)`

O aplicativo não apresenta esse valor como preço real comprovado de venda. É uma regra analítica de referência.

## Área

Os cálculos usam a área construída cadastrada na base da PBH. Ela pode diferir da área privativa anunciada. O indicador é apresentado como valor por m² cadastral.

## Avaliação

A forma recomendada é localizar uma transação do próprio imóvel. A área cadastral, padrão, ano, tipo e valor histórico são carregados diretamente da base.

Para apartamentos, o aplicativo confronta referências complementares:

1. FipeZAP Belo Horizonte como âncora temporal.
2. Comparáveis recentes da PBH, normalizados temporalmente quando necessário.
3. Transações do mesmo endereço, quando disponíveis, normalizadas para a área cadastral analisada e trazidas ao período atual.

A transação de origem e cópias equivalentes identificadas pela chave técnica são excluídas das referências da própria avaliação. A estimativa central é a mediana das referências disponíveis.

## Mercado

A aba Mercado apresenta:

- valor atual por m² com mediana móvel de três meses;
- variação em 12 meses e volume de negócios;
- leitura automática do comportamento do recorte selecionado;
- evolução do bairro comparada com Belo Horizonte;
- faixa central e distribuição dos valores negociados;
- comparação de até três bairros;
- rankings de valor por m², altas em 12 meses e volume de negócios;
- perfil das transações dos últimos 12 meses.

Os rankings aplicam amostras mínimas para reduzir distorções de bairros com poucos negócios.

## Atualização e integridade

- A carga valida a presença dos campos mínimos esperados da PBH.
- Linhas CSV malformadas provocam erro explícito; não são descartadas silenciosamente.
- Cargas com volume ou qualidade incompatíveis com a base esperada são rejeitadas, preservando o banco anterior.
- A substituição do banco e da série FipeZAP é feita por arquivo temporário e troca atômica.
- A atualização manual força o novo download dos recursos, inclusive quando a PBH corrige um arquivo já publicado.

## Fontes

- Portal de Dados Abertos da Prefeitura de Belo Horizonte — ITBI Relatórios.
- Fipe/FipeZAP — série histórica oficial do Índice FipeZAP residencial.

## Limitação da hospedagem atual

O Streamlit Community Cloud não garante persistência do armazenamento local. Se a instância for recriada, a base recente é recomposta automaticamente; a pesquisa histórica pode exigir nova carga do histórico completo desde 2008.

A ferramenta é estatística e não substitui laudo técnico de avaliação.
