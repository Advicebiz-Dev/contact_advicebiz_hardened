from odoo import _, fields, models
from odoo.exceptions import UserError


class TkoContactAccessPlatform(models.Model):
    _name = "tko.contact.access.platform"
    _description = "Plataforma de acesso"
    _order = "name"

    name = fields.Char(string="Plataforma", required=True, index=True)
    active = fields.Boolean(default=True)

    _unique_platform_name = models.Constraint("unique(name)", "Esta plataforma já existe.")


    def unlink(self):
        """Only delete a platform when no credential record refers to it.

        The direct Many2one link is authoritative. Also check unlinked
        legacy rows still using the textual platform name: older Studio
        migrations can leave ``site`` populated before ``platform_id``
        has been filled in. ACLs restrict this operation to administrators.
        """
        AccessData = self.env["tko.contact.access.data"].sudo().with_context(
            active_test=False
        )
        for platform in self:
            linked_data = AccessData.search_count([
                "|",
                ("platform_id", "=", platform.id),
                "&",
                ("platform_id", "=", False),
                ("site", "=ilike", platform.name),
            ])
            if linked_data:
                raise UserError(
                    _('Não é possível eliminar "%s". Existem dados associados a esta plataforma')
                    % platform.name
                )
        return super().unlink()
