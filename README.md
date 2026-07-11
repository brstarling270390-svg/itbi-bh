# Quanto Vale BH — v3

Aplicativo Streamlit para transformar os dados públicos de ITBI da Prefeitura de Belo Horizonte em uma experiência orientada à pergunta: **quanto vale um imóvel parecido com este?**

## Fluxo principal

1. Informe bairro, tipo de imóvel e área.
2. Opcionalmente informe ano de construção e padrão de acabamento.
3. O app seleciona transações comparáveis em camadas de recência e tolerância de área.
4. Exibe faixa observada, referência central, mediana por m² e as transações mais semelhantes.

A faixa é uma referência estatística baseada em valores declarados ao ITBI. Não constitui laudo de avaliação.

## Publicar atualização

Substitua o conteúdo do repositório no GitHub pelos arquivos desta versão ou, no GitHub, use **Add file → Upload files**, envie os arquivos e confirme em **Commit changes**. O Streamlit Community Cloud normalmente refaz o deploy automaticamente após o commit.

## Versão 4

- Mantém a área de exploração das transações como navegação própria.
- Torna o padrão de acabamento um critério visível na avaliação.
- Prioriza comparáveis do mesmo padrão antes de ampliar a amostra.
- Exibe o padrão de acabamento nos cartões de transações.
- Permite filtrar a consulta por padrão de acabamento.
