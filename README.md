# Quanto Vale BH — versão auditada

Aplicativo Streamlit para consulta e análise de transações imobiliárias declaradas à Prefeitura de Belo Horizonte.

## Funções

- Consulta de transações por endereço, bairro, tipo, padrão e período.
- Visualização de outras transações do mesmo endereço.
- Avaliação por comparáveis recentes.
- Estimativa híbrida de um valor antigo.
- Painel de evolução do mercado por valor de referência/m² cadastral.

## Valor de referência

Para os cálculos estatísticos:

`valor_referencia = max(valor_declarado, valor_base_calculo)`

O aplicativo não apresenta esse valor como preço real comprovado de venda. É uma regra analítica de referência.

## Área

Os cálculos usam a área construída cadastrada na base da PBH. Ela pode diferir da área privativa anunciada. O indicador é apresentado como valor por m² cadastral.

## Comparáveis recentes

- Janela máxima de 36 meses.
- Amostra mínima obrigatória conforme o nível de filtro.
- Prioridade para rua, área semelhante, padrão, idade e recência.
- Para apartamentos, valores de meses anteriores são normalizados temporalmente pelo FipeZAP BH antes da mediana.
- A transação usada como origem de uma avaliação é excluída da própria amostra de comparáveis.

## Estimativa híbrida de valor antigo

Para apartamentos, o aplicativo confronta referências complementares:

1. FipeZAP Belo Horizonte como âncora temporal.
2. Comparáveis recentes da PBH, normalizados temporalmente quando necessário.
3. Transações do mesmo endereço, quando disponíveis, normalizadas para a área cadastral analisada e trazidas ao período do FipeZAP.

A estimativa central é a mediana das referências disponíveis. A ferramenta é estatística e não substitui laudo técnico de avaliação.

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


## Link para Google Maps

Os cartões de imóveis agora incluem o botão **Abrir no Google Maps**.

O link usa uma pesquisa textual com o endereço-base, bairro, Belo Horizonte e MG. Foi incluído em:

- comparáveis recentes da avaliação;
- busca de transação antiga;
- comparáveis PBH da estimativa híbrida;
- transações do mesmo endereço usadas na estimativa híbrida;
- consulta de transações;
- tela de transações do mesmo endereço.

O aplicativo não trata o resultado do Google Maps como coordenada oficial ou localização exata; o usuário deve conferir o local aberto pelo serviço.
