# Como transformar o projeto em um endereço de internet

O aplicativo já está estruturado para implantação em uma hospedagem compatível com Streamlit.

## Opção recomendada para um protótipo

1. Criar uma conta no GitHub.
2. Criar um repositório e enviar os arquivos desta pasta, exceto a pasta `.venv` e eventuais arquivos baixados dentro de `data/raw`.
3. Acessar o Streamlit Community Cloud.
4. Conectar a conta do GitHub.
5. Selecionar o repositório e informar `app.py` como arquivo principal.
6. Implantar.

### Atenção ao armazenamento

O Streamlit Community Cloud pode apagar arquivos locais quando reinicia a aplicação. Nesse cenário, o aplicativo precisará reconstruir a base ou usar armazenamento persistente externo. Para uso frequente e público, a arquitetura mais adequada é:

- aplicativo Streamlit;
- banco PostgreSQL gerenciado;
- rotina mensal de atualização;
- autenticação, se desejada.

A versão entregue prioriza funcionamento local e prototipação, sem custo de hospedagem.
