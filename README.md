# Quanto Vale BH — versão final v2

Aplicativo Streamlit para consultar transações imobiliárias declaradas à Prefeitura de Belo Horizonte.

## Ajustes desta revisão

- Corrige o campo de ano de construção, que agora pode ser digitado diretamente e também pode ficar vazio.
- Acrescenta rua como critério opcional na avaliação.
- Quando a rua é informada, o algoritmo tenta primeiro usar comparáveis da mesma rua.
- Se a amostra da rua for pequena, amplia para o bairro e ainda prioriza registros da rua no ranking.
- Mantém bairro, tipo, área, padrão de acabamento, ano e recência como critérios de comparabilidade.

A fonte dos dados é o Portal de Dados Abertos da Prefeitura de Belo Horizonte.
