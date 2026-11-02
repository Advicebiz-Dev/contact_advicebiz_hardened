# Contact AdviceBiz — Dados de Acesso Hardened

Módulo personalizado para Odoo 19.

## Funcionalidades

- Permite gerir Plataformas, Logins, Passwords e Observações por contacto.
- Armazena as passwords cifradas com Fernet.
- Exige reautenticação com a password do Odoo para revelar ou copiar passwords.
- Disponibiliza permissões independentes para Visualizar, Escrever, Editar e Apagar passwords.
- Regista criações, alterações, eliminações e visualizações no Histórico de Acessos.
- Mantém o histórico de auditoria separado das mensagens normais do chatter.
- Permite gerir plataformas e impede a eliminação das que tenham dados associados.

## Segurança e permissões

- **Visualizar:** revelar e copiar passwords.
- **Escrever:** definir passwords em novos registos.
- **Editar:** alterar passwords existentes.
- **Apagar:** eliminar registos de Dados de Acesso.
- As permissões aplicam-se às passwords, sem bloquear a edição de Plataforma e Login.
- Os administradores não ultrapassam automaticamente as permissões definidas.
- As passwords nunca são apresentadas em texto claro no histórico.

## Migração de dados

- Importa automaticamente os Dados de Acesso existentes no Studio.
- Cifra as passwords importadas.
- Preserva os registos originais e evita duplicações.
- Mantém os dados incompletos no Studio para tratamento manual.
- Preserva as observações e os dados históricos existentes.

**Nota:** As passwords antigas continuam armazenadas no Studio até à sua remoção manual.

## Versão 19.0.3.17.4

- Permite aos administradores eliminar plataformas sem dados associados.
- Impede a eliminação de plataformas em utilização, incluindo registos inativos.
- Corrige o funcionamento e a disposição dos separadores **Mensagens** e **Histórico de Acessos**.
- Posiciona Observações imediatamente após Password.
- Remove do histórico as confirmações de identidade redundantes, mantendo os registos relevantes.
- Mantém a cifragem, as permissões e a auditoria de acessos.

## Atualização

1. Efetuar backup da base de dados.
2. Substituir as pastas `contact_advicebiz_hardened` e `security_password_hardened`.
3. Reiniciar o Odoo.
4. Atualizar ambos os módulos.
5. Atualizar o navegador (`Ctrl + F5`).
6. Testar as permissões, a visualização de passwords, o histórico e a gestão de plataformas.

**Nota:** Requer a variável de ambiente `ADVICEBIZ_ACCESS_DATA_FERNET_KEY` configurada no servidor.
