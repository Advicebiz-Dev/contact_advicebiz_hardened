# Contact | AdviceBiz - Dados de Acesso Hardened

Módulo autónomo para Odoo 19. Não depende dos módulos originais `tko_contact_advicebiz` nem `tko_security_password`.

## Segurança e UX

- Plataforma / Login / Password por contacto.
- Password cifrada em repouso com Fernet (`ADVICEBIZ_ACCESS_DATA_FERNET_KEY`).
- O valor em claro só é devolvido após clique no olho + reautenticação manual com a password Odoo.
- Passwords existentes são read-only na lista: a alteração é feita por diálogo explícito com confirmação de Plataforma/Login.
- Botão de copiar só aparece depois de uma revelação autenticada com sucesso.
- Auditoria em secção exclusiva do chatter do contacto, sem lançar mensagens no chatter normal.
- Permissões independentes para visualizar, criar, editar e apagar.


## Permissões estritas (19.0.3.7.0)
- **Escrever/Criar** permite apenas criar novos registos.
- **Editar** é obrigatório para qualquer alteração posterior, incluindo pelo criador.
- Ser Administrador/Definições (`base.group_system`) não dá bypass às permissões funcionais.
- Apenas operações internas executadas explicitamente em `sudo` podem ultrapassar a matriz.

## 19.0.3.8.0
- As permissões Escrever/Editar/Apagar aplicam-se ao registo completo, não apenas à Password.
- Plataforma e Login ficam bloqueados na interface quando o utilizador não tem Editar; o backend continua a validar todas as alterações.
- Plataforma, Login e Password são obrigatórios em novos registos e não podem ser esvaziados em registos existentes.


## 19.0.3.13.0 — Permissões apenas da Password
- O contacto e a aba **Dados de Acesso** ficam acessíveis mesmo sem qualquer permissão da matriz.
- A aba mantém o nome técnico `advicebiz_access_data_page` para compatibilidade com a view Studio e com `x_studio_dados_de_acesso`.
- **Visualizar** controla apenas revelar/copiar a Password.
- **Escrever** controla apenas a definição da Password inicial num novo registo.
- **Editar** controla apenas a alteração de uma Password existente.
- **Apagar** controla a eliminação do registo que contém a Password.
- Plataforma e Login já não são bloqueados pela matriz de permissões da Password.


## Migração automática dos Dados de Acesso do Studio

Ao instalar/atualizar esta versão, o módulo deteta a estrutura histórica do Studio
`res.partner.x_studio_dados_de_acesso` / `x_res_partner_line_261c0` e importa, sem
apagar a origem, os registos completos para `tko.contact.access.data`:

- `x_res_partner_id` -> Contacto
- `x_studio_plataforma` -> Plataforma (nome do registo em `x_plataformas`)
- `x_studio_login` -> Login
- `x_studio_password` -> Password, cifrada imediatamente com Fernet

`x_name`, `x_studio_notas` e `x_studio_sequence` são preservados em campos
legados internos, não apresentados na grelha. A migração usa o ID Studio como
chave de origem e pode voltar a correr sem duplicar registos. Linhas Studio
incompletas (sem Plataforma, Login ou Password) não são alteradas nem inventadas;
permanecem apenas no Studio para tratamento manual.

A origem Studio nunca é apagada automaticamente. Depois de validada a migração,
deve ser planeada separadamente a limpeza do campo Studio de password, porque o
valor histórico continua armazenado pela customização Studio até essa limpeza.

## 19.0.3.17.0 — Chatter dividido e campos adicionais

- O chatter do contacto tem **Mensagens** (Odoo nativo) e **Histórico de Acessos**.
  O histórico é só leitura, com paginação e atualização manual; não apresenta
  nem guarda passwords em texto claro.
- Todos os novos eventos de criação, alteração, eliminação e visualização de
  passwords são guardados no modelo `tko.contact.access.audit`, sem `message_post`.
- Na atualização, as notas antigas identificadas **com segurança** pelos títulos
  usados neste módulo são copiadas para o novo histórico; a sua mensagem
  `mail.message` original é preservada mas desligada da conversa do contacto.
  Notas ambíguas não são movidas. É indispensável fazer backup antes do upgrade.
- A aba Dados de Acesso tem agora **Plataforma** (Many2one configurável) e
  **Observações** (Text). Os textos anteriores em `site` são preservados;
  os nomes únicos existentes preenchem automaticamente o catálogo de plataformas.
  As notas antigas Studio preenchem Observações apenas quando ainda estiver vazio.
- Mantida a coluna legada `site` para compatibilidade; não se altera o mecanismo
  de encriptação Fernet nem os controlos de reautenticação.
- A listagem de auditoria só é servida após verificar permissões de leitura
  do contacto, e apenas a utilizadores internos; o modelo não concede ACL
  de leitura direta ao utilizador.

**Atenção:** o frontend Odoo 19 depende da estrutura do `mail.Chatter` da build
instalada. Validar em DEV com `?debug=assets` antes de atualizar PRE/PROD.

## 19.0.3.17.1 — Correção dos botões do chatter

- Corrigidos os handlers dos separadores **Mensagens** e **Histórico de Acessos**
  para serem associados pelo Owl à instância do componente.
- Evita o erro `Cannot read properties of undefined (reading 'advicebizIsPartnerChatter')`
  ao abrir o Histórico de Acessos.
- Nenhuma alteração aos modelos, às passwords, às permissões ou ao armazenamento da auditoria.
- Atualizar o módulo e forçar a renovação dos assets do navegador depois da instalação.

## 19.0.3.17.2 — Disposição dos separadores e das colunas

- Os separadores **Mensagens** e **Histórico de Acessos** ficam antes dos botões
  **Enviar mensagem**, **Registar uma Nota** e **Atividade** no chatter do contacto.
- Na lista **Dados de Acesso**, a coluna **Observações** surge imediatamente
  a seguir à coluna **Password**.
- Sem alterações à cifragem, auditoria, controlo de acesso ou à lógica JavaScript.

## 19.0.3.17.3 — Remoção de confirmações de identidade redundantes

- Deixa de criar o evento genérico **Acesso aos Dados de Acesso**
  (identidade confirmada) após reautenticação. A sessão de autorização
  de uso único, por 60 segundos, mantém-se inalterada.
- O separador Histórico de Acessos deixa de exibir os eventos anteriores
  com ação `unlock`, mantendo os dados existentes na base de dados.
- As visualizações efetivas de passwords continuam a ser auditadas, assim
  como criações, alterações e eliminações de Dados de Acesso.
- Atualizar **ambos** os módulos, `contact_advicebiz_hardened` e
  `security_password_hardened`, e reiniciar o Odoo.

## 19.0.3.17.4 — Eliminação controlada de plataformas

- Administradores (grupo Definições, `base.group_system`) podem eliminar
  plataformas no menu **Contactos > Plataformas dos Dados de Acesso**.
- Se houver qualquer Dado de Acesso associado, incluindo registos legados
  ainda sem `platform_id`, a eliminação é bloqueada no servidor com a mensagem:
  `Não é possível eliminar "Nome da Plataforma". Existem dados associados a esta plataforma`.
- A validação inclui registos inativos e impede a eliminação de um conjunto
  de plataformas quando pelo menos uma está em uso.
- Os restantes utilizadores não recebem a permissão de eliminação.
- Não foram alterados o histórico de auditoria, as passwords ou as regras
  de visualização.
