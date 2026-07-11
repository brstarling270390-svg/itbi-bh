# Quanto Vale BH — revisão metodológica final

Aplicativo Streamlit para consultar transações imobiliárias declaradas à Prefeitura de Belo Horizonte.

## Regras desta versão

### Valor de referência

O aplicativo usa, para cálculos estatísticos:

`valor_referencia = max(valor_declarado, valor_base_calculo)`

O indicador por m² é calculado sobre a área construída cadastrada na base da PBH.

### Área

A interface deixa de chamar o campo simplesmente de "área do imóvel". A expressão usada é "área construída cadastrada na PBH" ou "área cadastral PBH".

O aplicativo alerta que essa área pode diferir da área privativa de anúncio e pode refletir proporcionalmente áreas comuns e garagem.

### Avaliação

- Comparáveis recentes.
- Atualização de valor antigo pela evolução de grupos comparáveis.
- Possibilidade de localizar uma transação antiga e atualizar automaticamente o imóvel para hoje.
- Botão "Avaliar este imóvel" na aba Transações, carregando área, padrão, ano e tipo diretamente da base.

### Transações

- Valor de referência.
- Valor por m² cadastral.
- Valor declarado e base PBH exibidos separadamente.
- Botão para ver outras transações do mesmo endereço.
- Botão para avaliar diretamente o imóvel selecionado.

A fonte dos dados é o Portal de Dados Abertos da Prefeitura de Belo Horizonte.
