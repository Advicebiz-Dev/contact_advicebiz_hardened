from lxml import html

from odoo import fields, models


class TkoContactAccessAudit(models.Model):
    _name = "tko.contact.access.audit"
    _description = "Histórico protegido dos Dados de Acesso"
    _order = "occurred_at desc, id desc"

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    access_data_id = fields.Many2one("tko.contact.access.data", ondelete="set null")
    platform = fields.Char(string="Plataforma", readonly=True)
    actor_id = fields.Many2one("res.users", string="Utilizador", readonly=True, ondelete="set null")
    action = fields.Selection([
        ("create", "Criação"), ("change", "Alteração"),
        ("delete", "Eliminação"), ("reveal", "Visualização de password"),
        ("unlock", "Desbloqueio"), ("legacy", "Evento histórico"),
    ], readonly=True, required=True)
    title = fields.Char(required=True, readonly=True)
    details = fields.Text(readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True, index=True)
    legacy_mail_message_id = fields.Many2one("mail.message", ondelete="set null", readonly=True)

    _unique_legacy_mail_message = models.Constraint(
        "unique(legacy_mail_message_id)", "Mensagem de auditoria já migrada."
    )

    def init(self):
        """Move clearly identified historic audit notes away from the contact.

        Preserve the original mail.message itself under the audit record (not
        deleted) and copy its metadata to an append-only event.  Ambiguous
        chatter entries are deliberately left alone.
        """
        cr = self.env.cr
        cr.execute("""
            SELECT m.id, m.res_id, m.author_id, m.body, m.date,
                   m.create_date
              FROM mail_message m
             WHERE m.model = 'res.partner'
               AND m.res_id IS NOT NULL
               AND m.message_type = 'comment'
               AND m.body IS NOT NULL
               AND (m.body ILIKE '%%Dado de Acesso%%'
                 OR m.body ILIKE '%%Palavra-passe visualizada%%'
                 OR m.body ILIKE '%%Protected item unlocked!%%')
        """)
        titles = {
            "Dado de Acesso criado": "create",
            "Dado de Acesso alterado": "change",
            "Dado de Acesso apagado": "delete",
            "Palavra-passe visualizada": "reveal",
            "Acesso aos Dados de Acesso": "unlock",
            "Protected item unlocked!": "unlock",
        }
        for message_id, partner_id, author_partner, body, date, create_date in cr.fetchall():
            try:
                root = html.fragment_fromstring(body or "", create_parent="div")
                strongs = root.xpath(".//strong")
                paragraphs = root.xpath(".//p")
                head = strongs[0].text_content().strip() if strongs else root.text_content().strip()
                details = "\n".join(
                    para.text_content().strip() for para in paragraphs[1:]
                    if para.text_content().strip()
                )
            except (TypeError, ValueError):
                continue
            title = next((key for key in titles if head == key), None)
            if not title:
                continue
            # Do not migrate arbitrary manual notes merely containing a word.
            if not strongs and title != "Protected item unlocked!":
                continue
            cr.execute("SELECT 1 FROM res_partner WHERE id = %s", (partner_id,))
            if not cr.fetchone():
                continue
            cr.execute("""
                SELECT u.id FROM res_users u WHERE u.partner_id = %s LIMIT 1
            """, (author_partner,))
            user_result = cr.fetchone()
            cr.execute("""
                INSERT INTO tko_contact_access_audit
                    (partner_id, actor_id, action, title, details, occurred_at,
                     legacy_mail_message_id, create_date, write_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT DO NOTHING RETURNING id
            """, (
                partner_id, user_result[0] if user_result else None,
                titles[title], title,
                details, date or create_date or fields.Datetime.now(),
                message_id,
            ))
            result = cr.fetchone()
            if result:
                cr.execute("""
                    UPDATE mail_message SET model = 'tko.contact.access.audit', res_id = %s
                    WHERE id = %s AND model = 'res.partner' AND res_id = %s
                """, (result[0], message_id, partner_id))
